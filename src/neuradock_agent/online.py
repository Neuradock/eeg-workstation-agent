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
from urllib.parse import urlparse

import numpy as np

from .io import packet_fields_to_samples, read_neuradock_txt
from .profile import PROFILE
from .signal_compat import butter, filtfilt, iirnotch, sosfiltfilt, welch


POSTERIOR_CHANNELS = ("O1", "O2", "Oz", "PO3", "PO4")
LEFT_CHANNELS = ("O1", "PO3")
RIGHT_CHANNELS = ("O2", "PO4")


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
        return matrix
    if matrix.shape[1] == PROFILE.channel_count:
        return matrix.T
    raise ValueError(
        "samples must have 7 channels as either rows or columns; "
        f"received shape {matrix.shape}."
    )


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
        if not np.all(np.isfinite(matrix)):
            raise ValueError("samples contain NaN or infinite values.")
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

        if quality["status"] == "pass":
            self.history.append(log_alpha)
            self.history = self.history[-600:]
        if len(self.history) >= 3:
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
        }
        self.points.append(point)
        self.points = self.points[-240:]
        return {
            "status": "ok",
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
    ) -> None:
        self.processor = OnlineVisualLoadProcessor(window_sec=window_sec)
        self.lock = threading.Lock()
        self.step_samples = int(round(step_sec * PROFILE.sampling_rate_hz))
        self.demo_data: Optional[np.ndarray] = None
        self.demo_source: Optional[str] = None
        self.cursor = 0
        self.stream: Optional[NeuraDockTCPStreamWorker] = None
        self.latest_result: Dict[str, object] = {
            "status": "waiting_for_data",
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

    def append_online_samples(self, samples: np.ndarray) -> None:
        with self.lock:
            self.processor.append(samples)
            self.latest_result = self.processor.analyze_current()

    def next_demo(self) -> Dict[str, object]:
        if self.demo_data is None:
            raise ValueError("No demo file was configured for this server.")
        with self.lock:
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
        response["source"] = "demo_file"
        return response

    def current_status(self) -> Dict[str, object]:
        with self.lock:
            response = dict(self.latest_result)
        if self.stream is not None:
            response["stream"] = self.stream.status()
            response["source"] = "neuradock_tcp"
        elif self.demo_data is not None:
            response["source"] = "demo_file"
        else:
            response["source"] = "manual_post"
        return response

    def reset(self) -> None:
        with self.lock:
            self.cursor = 0
            self.processor.reset()
            self.latest_result = {
                "status": "waiting_for_data",
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


def _dashboard_html() -> bytes:
    path = Path(__file__).resolve().parent / "web" / "dashboard.html"
    return path.read_bytes()


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

        def _send_html(self) -> None:
            body = _dashboard_html()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
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
                    self._send_html()
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
                if payload.get("reset"):
                    state.reset()
                samples = payload.get("samples")
                if samples is None:
                    raise ValueError("POST /api/analyze requires a samples array.")
                with state.lock:
                    state.processor.append(samples)
                    state.latest_result = state.processor.analyze_current()
                    self._send_json(state.latest_result)
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
) -> None:
    state = _DashboardState(
        demo_file,
        window_sec=window_sec,
        step_sec=step_sec,
        device_ip=device_ip,
        device_port=device_port,
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
