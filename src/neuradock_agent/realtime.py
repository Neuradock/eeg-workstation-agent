"""Live NeuraDock TCP capture and device-doctor workflow."""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Dict, List, Tuple, Union

import numpy as np

from .analysis import quality_analysis
from .artifacts import (
    create_run_dir,
    write_input_manifest,
    write_json,
    write_workflow_manifest,
)
from .io import packet_fields_to_samples, read_neuradock_txt, write_neuradock_bluetooth_txt
from .models import RunArtifacts
from .plots import plot_quality
from .profile import PROFILE
from .reports import BOUNDARY


PathLike = Union[str, Path]


def capture_tcp(
    ip: str,
    port: int,
    windows: int = 3,
    window_sec: float = 1.0,
    timeout_sec: float = 5.0,
) -> Tuple[np.ndarray, Dict[str, object]]:
    target_samples = int(round(windows * window_sec * PROFILE.sampling_rate_hz))
    samples: List[np.ndarray] = []
    buffer = ""
    bytes_received = 0
    lines_parsed = 0
    lines_skipped = 0
    start = time.time()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_sec)
    try:
        sock.connect((ip, int(port)))
        if PROFILE.tcp_start_command:
            sock.sendall(PROFILE.tcp_start_command)
        while sum(packet.shape[0] for packet in samples) < target_samples:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("NeuraDock stream closed before capture completed.")
            bytes_received += len(chunk)
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
                    samples.append(packet)
                    lines_parsed += 1
                except (ValueError, TypeError):
                    lines_skipped += 1
    finally:
        sock.close()

    elapsed = max(time.time() - start, 1e-9)
    matrix = np.vstack(samples)[:target_samples]
    observed_rate = matrix.shape[0] / elapsed
    metrics = {
        "ip": ip,
        "port": int(port),
        "elapsed_sec": elapsed,
        "samples_captured": int(matrix.shape[0]),
        "bytes_received": bytes_received,
        "lines_parsed": lines_parsed,
        "lines_skipped": lines_skipped,
        "skipped_line_ratio": lines_skipped / max(lines_parsed + lines_skipped, 1),
        "observed_delivery_rate_samples_per_sec": observed_rate,
        "target_sampling_rate_hz": PROFILE.sampling_rate_hz,
        "note": (
            "Observed delivery rate includes connection and buffering delay; "
            "timestamps or longer captures are needed for strict clock validation."
        ),
    }
    return matrix.T, metrics


def run_device_doctor(
    ip: str,
    port: int,
    windows: int = 3,
    output_root: PathLike = "runs",
) -> RunArtifacts:
    run_dir = create_run_dir(output_root, "device_doctor")
    input_dir = run_dir / "captured_input"
    data, stream = capture_tcp(ip, port, windows=windows)
    capture_path = write_neuradock_bluetooth_txt(
        input_dir / "neuradock_device_doctor_capture.txt",
        data,
        marker="device_doctor",
    )
    recording = read_neuradock_txt(capture_path)
    write_input_manifest(run_dir, [recording])
    write_workflow_manifest(
        run_dir,
        "device_doctor",
        {"ip": ip, "port": int(port), "windows": int(windows)},
    )
    quality = quality_analysis(recording)
    rate_error = (
        100.0
        * (stream["observed_delivery_rate_samples_per_sec"] - PROFILE.sampling_rate_hz)
        / PROFILE.sampling_rate_hz
    )
    doctor_warnings = list(quality.result["warnings"])
    if stream["skipped_line_ratio"] > 0.01:
        doctor_warnings.append(
            f"Skipped packet-line ratio is {stream['skipped_line_ratio']:.1%}."
        )
    if abs(rate_error) > 20:
        doctor_warnings.append(
            "Observed delivery rate differs substantially from 250 samples/s. "
            "Repeat with a longer capture before diagnosing device clock drift."
        )
    payload = {
        "workflow": "device_doctor",
        "status": "pass" if not doctor_warnings else "warning",
        "stream": {**stream, "delivery_rate_error_pct": rate_error},
        "signal_quality": quality.result,
        "warnings": doctor_warnings,
    }
    figure = plot_quality(quality, run_dir / "figures" / "device_doctor_quality.png")
    results_path = write_json(run_dir / "results.json", payload)
    report_lines = [
        "# NeuraDock Device Doctor",
        "",
        f"- Endpoint: `{ip}:{port}`",
        f"- Samples captured: {stream['samples_captured']}",
        f"- Packet lines parsed: {stream['lines_parsed']}",
        f"- Packet lines skipped: {stream['lines_skipped']}",
        f"- Observed delivery rate: {stream['observed_delivery_rate_samples_per_sec']:.1f} samples/s",
        f"- Signal samples retained: {quality.result['retention_rate']:.1%}",
        f"- Status: **{payload['status']}**",
        "",
        "## Warnings",
        "",
        *([f"- {item}" for item in doctor_warnings] or ["- No device-doctor warnings."]),
        "",
        "The captured stream was saved in NeuraDock text format so this run can be "
        "inspected later without reconnecting the device.",
        "",
        f"> {BOUNDARY}",
    ]
    report_path = run_dir / "report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    reproduce_path = run_dir / "reproduce.py"
    reproduce_path.write_text(
        "from pathlib import Path\n"
        "from neuradock_agent.io import read_neuradock_txt\n"
        "from neuradock_agent.workflows import run_signal_quality\n\n"
        "CAPTURE = Path(__file__).resolve().parent / "
        "'captured_input/neuradock_device_doctor_capture.txt'\n"
        "run = run_signal_quality(read_neuradock_txt(CAPTURE), "
        "output_root=Path(__file__).resolve().parent / 'reproduced_runs')\n"
        "print(run.report_path)\n",
        encoding="utf-8",
    )
    return RunArtifacts(run_dir, results_path, report_path, (figure,))
