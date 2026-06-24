"""Serve the Adaptive UI demo and provide or proxy GET /api/status."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent


class DemoStatusSource:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.history = []

    def status(self) -> Dict[str, object]:
        elapsed = time.time() - self.started_at
        cycle = elapsed % 24.0
        if 18.0 <= cycle < 22.0:
            quality = "warning"
            load = 84.0 + 5.0 * math.sin(cycle * 1.7)
        elif 12.0 <= cycle < 18.0:
            quality = "pass"
            load = 76.0 + 10.0 * math.sin(cycle * 0.9)
        elif 6.0 <= cycle < 12.0:
            quality = "pass"
            load = 52.0 + 8.0 * math.sin(cycle * 0.65)
        else:
            quality = "pass"
            load = 28.0 + 6.0 * math.sin(cycle * 0.85)

        load = float(max(0.0, min(100.0, load)))
        if quality != "pass":
            symbol = "SIGNAL_QUALITY_WARNING"
        elif load > 70.0:
            symbol = "VISUAL_LOAD_HIGH"
        elif load < 35.0:
            symbol = "VISUAL_LOAD_LOW"
        else:
            symbol = "VISUAL_LOAD_STABLE"
        point = {
            "sample_index": int(elapsed * 250),
            "time_sec": float(elapsed),
            "quality_status": quality,
            "visual_load_index": load,
            "visual_cognitive_symbol": symbol,
            "alpha_state": "weak_alpha" if load > 70 else "baseline_alpha",
            "posterior_log_alpha_power": -5.0 - load / 120.0,
            "alpha_suppression_from_baseline": load / 100.0,
            "alpha_peak_hz": 10.0 + load / 90.0,
            "alpha_asymmetry_right_minus_left": 0.08 * math.sin(cycle / 3.0),
        }
        self.history.append(point)
        self.history = self.history[-120:]
        bad_channels = ["O1", "PO3"] if quality != "pass" else []
        return {
            "status": "ok",
            "source": "adaptive_ui_demo_simulator",
            "quality": {
                "status": quality,
                "bad_channel_candidates": bad_channels,
                "channel_issue_fraction": 0.28 if bad_channels else 0.0,
                "line_noise_channels": [],
                "emg_channels": bad_channels,
                "extreme_amplitude_channels": [],
            },
            "current": point,
            "stream": {
                "connected": True,
                "status": "simulated",
                "samples_received": int(elapsed * 250),
            },
            "history": self.history,
        }


def _cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def _send_json(
    handler: BaseHTTPRequestHandler,
    payload: Dict[str, object],
    status: int = HTTPStatus.OK,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    _cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _proxy_status(api_base: str, timeout: float) -> Tuple[int, bytes, str]:
    url = f"{api_base.rstrip('/')}/api/status"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "application/json")
        return int(response.status), response.read(), content_type


def make_handler(
    demo_source: DemoStatusSource,
    api_base: Optional[str] = None,
    upstream_timeout: float = 2.0,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NeuraDockAdaptiveUIDemo/20260624"

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            _cors_headers(self)
            self.end_headers()

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/api/status":
                self._send_status()
                return
            self._send_static(route)

        def _send_status(self) -> None:
            if api_base:
                try:
                    status, body, content_type = _proxy_status(api_base, upstream_timeout)
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    _cors_headers(self)
                    self.end_headers()
                    self.wfile.write(body)
                    return
                except (OSError, urllib.error.URLError) as exc:
                    _send_json(
                        self,
                        {
                            "status": "upstream_error",
                            "source": "adaptive_ui_demo_proxy",
                            "error": str(exc),
                            "quality": {"status": "warning"},
                            "current": {},
                            "history": [],
                        },
                        status=HTTPStatus.BAD_GATEWAY,
                    )
                    return
            _send_json(self, demo_source.status())

        def _send_static(self, route: str) -> None:
            if route == "/":
                target = ROOT / "index.html"
            else:
                target = (ROOT / route.lstrip("/")).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            _cors_headers(self)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Adaptive UI demo server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument(
        "--api-base",
        help="Optional NeuraDock API base URL to proxy, for example http://127.0.0.1:8765.",
    )
    args = parser.parse_args()

    handler = make_handler(DemoStatusSource(), api_base=args.api_base)
    server = ThreadingHTTPServer((args.host, int(args.port)), handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Adaptive UI demo: {url}")
    if args.api_base:
        print(f"Proxying GET /api/status from {args.api_base.rstrip('/')}/api/status")
    else:
        print("Using built-in simulated GET /api/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAdaptive UI demo stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
