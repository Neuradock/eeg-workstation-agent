"""Online visual cognitive-load API and dashboard server."""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import numpy as np

from .io import packet_fields_to_samples, read_neuradock_txt
from .profile import PROFILE
from .signal_compat import butter, filtfilt, iirnotch, sosfiltfilt, welch


POSTERIOR_CHANNELS = ("O1", "O2", "Oz", "PO3", "PO4")
LEFT_CHANNELS = ("O1", "PO3")
RIGHT_CHANNELS = ("O2", "PO4")
MIN_BASELINE_WINDOWS = 3
WEB_ROOT = Path(__file__).resolve().parent / "web"
SOURCE_LABELS = {
    "synthetic_demo": "Synthetic Demo",
    "recorded_replay": "Recorded Replay",
    "live_device": "Live Device",
    "manual_post": "Manual Input",
}
ASSET_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def _channel_indices(names: Tuple[str, ...]) -> List[int]:
    index = {name: position for position, name in enumerate(PROFILE.channels)}
    return [index[name] for name in names]


def _integrate(freqs: np.ndarray, psd: np.ndarray, low: float, high: float) -> np.ndarray:
    mask = (freqs >= low) & (freqs <= high)
    if np.count_nonzero(mask) < 2:
        return np.zeros(psd.shape[:-1], dtype=float)
    if hasattr(np, "trapezoid"):
        return np.trapezoid(psd[..., mask], freqs[mask], axis=-1)
    return np.trapz(psd[..., mask], freqs[mask], axis=-1)


def _orient_samples(samples: object) -> np.ndarray:
    matrix = np.asarray(samples, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("samples must be a 2D array.")
    if matrix.shape[0] == PROFILE.channel_count:
        oriented = matrix
    elif matrix.shape[1] == PROFILE.channel_count:
        oriented = matrix.T
    else:
        raise ValueError(
            "samples must have 7 channels as either rows or columns; "
            f"received shape {matrix.shape}."
        )
    if oriented.shape[1] == 0:
        raise ValueError("samples must contain at least one sample.")
    if not np.all(np.isfinite(oriented)):
        raise ValueError("samples contain NaN or infinite values.")
    return oriented


class OnlineVisualLoadProcessor:
    """Rolling online preprocessing and posterior Alpha cognitive-load estimate."""

    def __init__(
        self,
        fs: int = PROFILE.sampling_rate_hz,
        window_sec: float = 4.0,
        max_buffer_sec: float = 90.0,
    ) -> None:
        self.fs = int(fs)
        self.window_samples = int(round(window_sec * fs))
        self.max_buffer_samples = int(round(max_buffer_sec * fs))
        self.buffer = np.empty((PROFILE.channel_count, 0), dtype=float)
        self.history: List[float] = []
        self.points: List[Dict[str, object]] = []
        self.total_samples_seen = 0

    def reset(self) -> None:
        self.buffer = np.empty((PROFILE.channel_count, 0), dtype=float)
        self.history.clear()
        self.points.clear()
        self.total_samples_seen = 0

    def append(self, samples: object) -> None:
        matrix = _orient_samples(samples)
        self.total_samples_seen += matrix.shape[1]
        self.buffer = np.concatenate([self.buffer, matrix], axis=1)
        if self.buffer.shape[1] > self.max_buffer_samples:
            self.buffer = self.buffer[:, -self.max_buffer_samples :]

    def _preprocess_window(self, window: np.ndarray) -> np.ndarray:
        centered = window - np.median(window, axis=1, keepdims=True)
        sos = butter(4, [1.0, 45.0], btype="bandpass", fs=self.fs, output="sos")
        filtered = sosfiltfilt(sos, centered, axis=1)
        b_notch, a_notch = iirnotch(PROFILE.line_frequency_hz, 30.0, fs=self.fs)
        return filtfilt(b_notch, a_notch, filtered, axis=1)

    def _quality_gate(self, filtered: np.ndarray) -> Dict[str, object]:
        freqs, psd = welch(
            filtered,
            fs=self.fs,
            nperseg=min(filtered.shape[1], self.fs * 2),
            axis=1,
        )
        line_power = _integrate(freqs, psd, 49.0, 51.0)
        emg_power = _integrate(freqs, psd, 20.0, 40.0)
        outlier_count = np.sum(
            np.abs(filtered) >= PROFILE.quality.outlier_absolute_amplitude,
            axis=1,
        )
        line_bad = line_power > PROFILE.quality.line_noise_power
        emg_bad = emg_power > PROFILE.quality.emg_power
        outlier_bad = (
            outlier_count
            > PROFILE.quality.outlier_count_per_second
            * max(1.0, filtered.shape[1] / self.fs)
        )
        issue_mask = line_bad | emg_bad | outlier_bad
        bad_channels = [
            channel for channel, bad in zip(PROFILE.channels, issue_mask) if bool(bad)
        ]
        issue_fraction = float(np.mean(issue_mask))
        status = "pass" if issue_fraction <= PROFILE.quality.bad_channel_segment_ratio else "warning"
        return {
            "status": status,
            "bad_channel_candidates": bad_channels,
            "channel_issue_fraction": issue_fraction,
            "line_noise_channels": [
                channel for channel, bad in zip(PROFILE.channels, line_bad) if bool(bad)
            ],
            "emg_channels": [
                channel for channel, bad in zip(PROFILE.channels, emg_bad) if bool(bad)
            ],
            "extreme_amplitude_channels": [
                channel for channel, bad in zip(PROFILE.channels, outlier_bad) if bool(bad)
            ],
        }

    def _channel_metrics(
        self,
        filtered: np.ndarray,
        quality: Dict[str, object],
    ) -> List[Dict[str, object]]:
        line_noise = set(quality.get("line_noise_channels", []))
        emg = set(quality.get("emg_channels", []))
        extreme = set(quality.get("extreme_amplitude_channels", []))
        flagged = set(quality.get("bad_channel_candidates", []))
        rms = np.sqrt(np.mean(np.square(filtered), axis=1))
        peak_to_peak = np.ptp(filtered, axis=1)
        metrics: List[Dict[str, object]] = []
        for index, channel in enumerate(PROFILE.channels):
            reasons: List[str] = []
            if channel in line_noise:
                reasons.append("line_noise")
            if channel in emg:
                reasons.append("emg")
            if channel in extreme:
                reasons.append("extreme_amplitude")
            metrics.append(
                {
                    "name": channel,
                    "status": "flagged" if channel in flagged else "pass",
                    "rms_uv": float(rms[index]),
                    "peak_to_peak_uv": float(peak_to_peak[index]),
                    "reasons": reasons,
                }
            )
        return metrics

    def analyze_current(self) -> Dict[str, object]:
        if self.buffer.shape[1] < self.window_samples:
            return {
                "status": "warming_up",
                "feedback_available": False,
                "feedback_reason": "warming_up",
                "samples_in_buffer": int(self.buffer.shape[1]),
                "required_samples": int(self.window_samples),
                "history": self.points[-240:],
            }
        window = self.buffer[:, -self.window_samples :]
        filtered = self._preprocess_window(window)
        quality = self._quality_gate(filtered)
        channel_metrics = self._channel_metrics(filtered, quality)

        posterior = _channel_indices(POSTERIOR_CHANNELS)
        left = _channel_indices(LEFT_CHANNELS)
        right = _channel_indices(RIGHT_CHANNELS)
        freqs, psd = welch(
            filtered,
            fs=self.fs,
            nperseg=min(filtered.shape[1], self.window_samples),
            axis=1,
        )
        alpha_power = _integrate(freqs, psd, 8.0, 13.0)
        posterior_alpha = float(np.mean(alpha_power[posterior]))
        left_alpha = float(np.mean(alpha_power[left]))
        right_alpha = float(np.mean(alpha_power[right]))
        posterior_psd = np.mean(psd[posterior], axis=0)
        alpha_mask = (freqs >= 8.0) & (freqs <= 13.0)
        alpha_peak_hz = float(freqs[alpha_mask][np.argmax(posterior_psd[alpha_mask])])
        asymmetry = (right_alpha - left_alpha) / (right_alpha + left_alpha + 1e-12)
        log_alpha = float(np.log10(posterior_alpha + 1e-12))

        valid_alpha = bool(np.isfinite(posterior_alpha) and posterior_alpha > 0.0)
        if quality["status"] == "pass" and valid_alpha:
            self.history.append(log_alpha)
            self.history = self.history[-600:]
        if len(self.history) >= MIN_BASELINE_WINDOWS:
            baseline = float(np.median(self.history))
            low, high = np.quantile(np.asarray(self.history, dtype=float), [1 / 3, 2 / 3])
            suppression = baseline - log_alpha
            if log_alpha <= low:
                alpha_state = "weak_alpha"
            elif log_alpha >= high:
                alpha_state = "strong_alpha"
            else:
                alpha_state = "baseline_alpha"
            rank = float(np.mean(np.asarray(self.history, dtype=float) <= log_alpha))
            load_index = 100.0 * (1.0 - rank)
        else:
            baseline = log_alpha
            suppression = 0.0
            alpha_state = "initializing"
            load_index = 50.0

        # This is a power multiplier against the existing rolling log-median,
        # not Alpha/total power and not a relaxation or clinical score.
        relative_alpha = None
        if quality["status"] != "pass":
            feedback_reason = "quality_warning"
        elif not valid_alpha:
            feedback_reason = "invalid_alpha_power"
        elif len(self.history) < MIN_BASELINE_WINDOWS:
            feedback_reason = "baseline_warming_up"
        else:
            with np.errstate(over="ignore", under="ignore", invalid="ignore"):
                candidate = float(np.power(10.0, -suppression))
            if np.isfinite(candidate) and candidate > 0.0:
                relative_alpha = candidate
                feedback_reason = "ready"
            else:
                feedback_reason = "invalid_alpha_power"

        point = {
            "sample_index": int(self.total_samples_seen),
            "time_sec": float(self.total_samples_seen / self.fs),
            "quality_status": quality["status"],
            "visual_load_index": float(np.clip(load_index, 0.0, 100.0)),
            "alpha_state": alpha_state,
            "posterior_log_alpha_power": log_alpha,
            "alpha_suppression_from_baseline": float(suppression),
            "alpha_peak_hz": alpha_peak_hz,
            "alpha_asymmetry_right_minus_left": float(asymmetry),
            "posterior_alpha_relative": relative_alpha,
            "feedback_available": relative_alpha is not None,
            "feedback_reason": feedback_reason,
            "baseline_history_count": len(self.history),
        }
        self.points.append(point)
        self.points = self.points[-240:]
        return {
            "status": "ok",
            "feedback_available": point["feedback_available"],
            "feedback_reason": feedback_reason,
            "preprocessing": {
                "mode": "online_window_preprocessing",
                "bandpass_hz": [1.0, 45.0],
                "notch_hz": PROFILE.line_frequency_hz,
                "window_sec": self.window_samples / self.fs,
                "sampling_rate_hz": self.fs,
                "quality_gate": "line_noise_emg_extreme_amplitude",
            },
            "quality": quality,
            "current": point,
            "baseline": {
                "rolling_log_alpha_median": baseline,
                "history_count": len(self.history),
                "minimum_history_count": MIN_BASELINE_WINDOWS,
                "max_history_count": 600,
                "reference": "rolling_log_median",
            },
            "channels": channel_metrics,
            "history": self.points[-240:],
            "interpretation_limits": [
                "The online index is relative to the rolling Alpha baseline.",
                "It is not a clinical, attention, fatigue, or performance diagnosis.",
                "Quality warnings reduce confidence in the current estimate.",
            ],
        }


class _DashboardState:
    def __init__(
        self,
        demo_file: Optional[Path],
        window_sec: float,
        step_sec: float,
        device_ip: Optional[str] = None,
        device_port: Optional[int] = None,
        source_kind: Optional[str] = None,
    ) -> None:
        has_device = device_ip is not None or device_port is not None
        if has_device and (device_ip is None or device_port is None):
            raise ValueError("Both device_ip and device_port are required.")
        if has_device and demo_file is not None:
            raise ValueError("Choose a device or a replay file, not both.")
        default_kind = (
            "live_device" if has_device
            else "recorded_replay" if demo_file is not None
            else "manual_post"
        )
        self.source_kind = source_kind or default_kind
        allowed_kinds = (
            {"live_device"} if has_device
            else {"synthetic_demo", "recorded_replay"} if demo_file is not None
            else {"manual_post"}
        )
        if self.source_kind not in allowed_kinds:
            raise ValueError("source_kind does not match the configured input.")
        self.configured_source_kind = self.source_kind
        self.processor = OnlineVisualLoadProcessor(window_sec=window_sec)
        self.lock = threading.Lock()
        self.step_samples = int(round(step_sec * PROFILE.sampling_rate_hz))
        self.demo_data: Optional[np.ndarray] = None
        self.demo_source: Optional[str] = None
        self.cursor = 0
        self.last_input_monotonic: Optional[float] = None
        self.stale_after_sec = max(3.0, 3.0 * step_sec)
        self.stream: Optional[NeuraDockTCPStreamWorker] = None
        self.latest_result: Dict[str, object] = {
            "status": "waiting_for_data",
            "feedback_available": False,
            "feedback_reason": "no_data",
            "history": [],
        }
        if demo_file is not None:
            self.demo_data = read_neuradock_txt(demo_file).data
            self.demo_source = demo_file.name
        if device_ip is not None and device_port is not None:
            self.stream = NeuraDockTCPStreamWorker(
                device_ip,
                int(device_port),
                self,
            )
            self.stream.start()

    def _select_source(self, source_kind: str) -> None:
        # A manual POST can coexist with the legacy routes. Never mix its
        # calibration history with a replay or live-device source.
        if self.source_kind != source_kind:
            self.processor.reset()
            self.source_kind = source_kind
            self.last_input_monotonic = None

    def append_online_samples(
        self, samples: np.ndarray, source_kind: Optional[str] = None
    ) -> None:
        # Reject invalid input before changing provenance or resetting history.
        matrix = _orient_samples(samples)
        with self.lock:
            self._select_source(source_kind or self.configured_source_kind)
            self.processor.append(matrix)
            self.latest_result = self.processor.analyze_current()
            self.last_input_monotonic = time.monotonic()

    def next_demo(self) -> Dict[str, object]:
        if self.demo_data is None:
            raise ValueError("No demo file was configured for this server.")
        with self.lock:
            self._select_source(self.configured_source_kind)
            stop = min(self.cursor + self.step_samples, self.demo_data.shape[1])
            chunk = self.demo_data[:, self.cursor:stop]
            if chunk.shape[1] == 0:
                self.cursor = 0
                self.processor.reset()
                stop = min(self.step_samples, self.demo_data.shape[1])
                chunk = self.demo_data[:, :stop]
            self.cursor = stop
            self.processor.append(chunk)
            response = self.processor.analyze_current()
            self.latest_result = response
            response["demo"] = {
                "source": self.demo_source or "configured_demo_file",
                "cursor_sample": int(self.cursor),
                "total_samples": int(self.demo_data.shape[1]),
                "looped": bool(self.cursor >= self.demo_data.shape[1]),
            }
        return self.current_status()

    def current_status(self) -> Dict[str, object]:
        with self.lock:
            response = dict(self.latest_result)
            source_kind = self.source_kind
            last_input = self.last_input_monotonic
        response["source_info"] = {
            "kind": source_kind,
            "label": SOURCE_LABELS[source_kind],
            "is_synthetic": source_kind == "synthetic_demo",
        }
        response["profile"] = PROFILE.to_dict()
        needs_freshness = source_kind in {"live_device", "manual_post"}
        age_sec = None if last_input is None else max(0.0, time.monotonic() - last_input)
        freshness_status = "not_applicable"
        if needs_freshness:
            freshness_status = (
                "waiting_for_data" if age_sec is None
                else "stale" if age_sec > self.stale_after_sec
                else "fresh"
            )
        response["freshness"] = {
            "status": freshness_status,
            "age_sec": age_sec if needs_freshness else None,
            "stale_after_sec": self.stale_after_sec if needs_freshness else None,
        }
        if self.stream is not None:
            response["stream"] = self.stream.status()
        feedback_block = None
        if source_kind == "live_device" and not response.get("stream", {}).get("connected"):
            feedback_block = "device_disconnected"
        elif freshness_status == "stale":
            feedback_block = "stale_data"
        if feedback_block is not None:
            response["feedback_available"] = False
            response["feedback_reason"] = feedback_block
            if "current" in response:
                current = dict(response["current"])
                current.update(
                    posterior_alpha_relative=None,
                    feedback_available=False,
                    feedback_reason=feedback_block,
                )
                response["current"] = current
        if source_kind == "live_device":
            response["source"] = "neuradock_tcp"
        elif source_kind in {"synthetic_demo", "recorded_replay"}:
            response["source"] = "demo_file"
        else:
            response["source"] = "manual_post"
        return response

    def reset(self) -> None:
        with self.lock:
            self.cursor = 0
            self.processor.reset()
            self.source_kind = self.configured_source_kind
            self.last_input_monotonic = None
            self.latest_result = {
                "status": "waiting_for_data",
                "feedback_available": False,
                "feedback_reason": "no_data",
                "history": [],
            }

    def close(self) -> None:
        if self.stream is not None:
            self.stream.stop()


class NeuraDockTCPStreamWorker:
    """Background TCP reader for the NeuraDock Bluetooth online stream."""

    def __init__(
        self,
        ip: str,
        port: int,
        state: _DashboardState,
        timeout_sec: float = 5.0,
    ) -> None:
        self.ip = ip
        self.port = int(port)
        self.state = state
        self.timeout_sec = timeout_sec
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._lock = threading.Lock()
        self._status: Dict[str, object] = {
            "mode": "neuradock_tcp",
            "ip": ip,
            "port": int(port),
            "connected": False,
            "status": "starting",
            "samples_received": 0,
            "lines_parsed": 0,
            "lines_skipped": 0,
            "last_error": None,
            "last_sample_time": None,
        }

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> Dict[str, object]:
        with self._lock:
            return dict(self._status)

    def _set_status(self, **items: object) -> None:
        with self._lock:
            self._status.update(items)

    def _run(self) -> None:
        pending_samples: List[np.ndarray] = []
        while not self._stop.is_set():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_sec)
            buffer = ""
            try:
                self._set_status(
                    status="connecting",
                    connected=False,
                    last_error=None,
                )
                sock.connect((self.ip, self.port))
                if PROFILE.tcp_start_command:
                    sock.sendall(PROFILE.tcp_start_command)
                self._set_status(status="streaming", connected=True)
                while not self._stop.is_set():
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("NeuraDock stream closed.")
                    buffer += chunk.decode("utf-8", errors="ignore")
                    lines = buffer.split("\n")
                    buffer = lines[-1]
                    for line in lines[:-1]:
                        if not line.strip():
                            continue
                        try:
                            packet, _marker, _timestamp = packet_fields_to_samples(
                                [part.strip() for part in line.strip().split(",")]
                            )
                            pending_samples.append(packet)
                            sample_count = int(packet.shape[0])
                            current = self.status()
                            self._set_status(
                                lines_parsed=int(current["lines_parsed"]) + 1,
                                samples_received=int(current["samples_received"])
                                + sample_count,
                                last_sample_time=time.time(),
                            )
                        except (TypeError, ValueError):
                            current = self.status()
                            self._set_status(
                                lines_skipped=int(current["lines_skipped"]) + 1
                            )
                            continue

                        total_pending = sum(item.shape[0] for item in pending_samples)
                        if total_pending >= PROFILE.sampling_rate_hz:
                            samples = np.vstack(pending_samples)
                            pending_samples.clear()
                            self.state.append_online_samples(samples)
            except (ConnectionError, OSError) as exc:
                self._set_status(
                    status="reconnecting",
                    connected=False,
                    last_error=str(exc),
                )
                if self._stop.wait(1.0):
                    break
            finally:
                sock.close()
        self._set_status(status="stopped", connected=False)


def _dashboard_html(advanced: bool = False) -> bytes:
    path = WEB_ROOT / ("advanced.html" if advanced else "dashboard.html")
    return path.read_bytes()


def _asset_file(route: str) -> Optional[Path]:
    """Resolve only public, supported assets, never arbitrary package files."""
    relative = unquote(route[len("/assets/"):]).replace("\\", "/")
    parts = relative.split("/")
    if not relative or any(part in {"", ".", ".."} for part in parts):
        return None
    root = (WEB_ROOT / "assets").resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.suffix.lower() not in ASSET_CONTENT_TYPES or not candidate.is_file():
        return None
    return candidate


def make_handler(state: _DashboardState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NeuraDockOnlineVisualLoad/20260624"

        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _send_json(self, payload: Dict[str, object], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            try:
                if route == "/":
                    self._send_file(_dashboard_html(), "text/html; charset=utf-8")
                elif route in {"/advanced", "/advanced/"}:
                    self._send_file(_dashboard_html(advanced=True), "text/html; charset=utf-8")
                elif route.startswith("/assets/"):
                    asset = _asset_file(route)
                    if asset is None:
                        self._send_json({"error": "not found"}, status=404)
                    else:
                        self._send_file(asset.read_bytes(), ASSET_CONTENT_TYPES[asset.suffix.lower()])
                elif route == "/api/health":
                    self._send_json(
                        {
                            "status": "ok",
                            "version": "20260624",
                            "device": PROFILE.device,
                            "sampling_rate_hz": PROFILE.sampling_rate_hz,
                        }
                    )
                elif route == "/api/status":
                    self._send_json(state.current_status())
                elif route == "/api/next":
                    if state.stream is not None:
                        self._send_json(state.current_status())
                    elif state.demo_data is not None:
                        self._send_json(state.next_demo())
                    else:
                        self._send_json(state.current_status())
                elif route == "/api/demo/next":
                    self._send_json(state.next_demo())
                elif route == "/api/demo/reset":
                    state.reset()
                    self._send_json({"status": "ok", "cursor_sample": 0})
                else:
                    self._send_json({"error": "not found"}, status=404)
            except (OSError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)

        def do_POST(self) -> None:
            route = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if route != "/api/analyze":
                    self._send_json({"error": "not found"}, status=404)
                    return
                if not isinstance(payload, dict):
                    raise ValueError("POST /api/analyze requires a JSON object.")
                if payload.get("reset"):
                    state.reset()
                samples = payload.get("samples")
                if samples is None:
                    raise ValueError("POST /api/analyze requires a samples array.")
                state.append_online_samples(samples, source_kind="manual_post")
                self._send_json(state.current_status())
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve_online_dashboard(
    host: str = "127.0.0.1",
    port: int = 8765,
    demo_file: Optional[Path] = None,
    device_ip: Optional[str] = None,
    device_port: Optional[int] = None,
    window_sec: float = 4.0,
    step_sec: float = 1.0,
    open_browser: bool = False,
    source_kind: Optional[str] = None,
) -> None:
    state = _DashboardState(
        demo_file,
        window_sec=window_sec,
        step_sec=step_sec,
        device_ip=device_ip,
        device_port=device_port,
        source_kind=source_kind,
    )
    server = ThreadingHTTPServer((host, int(port)), make_handler(state))
    url = f"http://{host}:{port}"
    print(f"NeuraDock online visual cognitive-load dashboard: {url}")
    if device_ip is not None and device_port is not None:
        print(f"Device stream: {device_ip}:{device_port}")
    print("API: GET /api/health, GET /api/status, GET /api/demo/next, POST /api/analyze")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
    finally:
        state.close()
        server.server_close()
