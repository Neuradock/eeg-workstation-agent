import unittest
import http.client
import socket
import threading
import time
from http.server import ThreadingHTTPServer

import numpy as np

from neuradock_agent.online import OnlineVisualLoadProcessor, _DashboardState, make_handler


class OnlineProcessorTests(unittest.TestCase):
    def test_online_processor_returns_quality_gated_alpha_metrics(self):
        fs = 250
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        time = np.arange(fs * 2) / fs
        base = 8.0 * np.sin(2.0 * np.pi * 10.0 * time)
        samples = np.vstack(
            [
                base + 0.2 * index * np.sin(2.0 * np.pi * 6.0 * time)
                for index in range(7)
            ]
        )

        processor.append(samples)
        first = processor.analyze_current()
        processor.append(samples * 0.6)
        second = processor.analyze_current()
        processor.append(samples * 0.4)
        third = processor.analyze_current()

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(third["status"], "ok")
        self.assertIn("preprocessing", third)
        self.assertIn("quality", third)
        self.assertIn("visual_load_index", third["current"])
        self.assertIn("alpha_peak_hz", third["current"])
        self.assertGreaterEqual(third["current"]["visual_load_index"], 0.0)
        self.assertLessEqual(third["current"]["visual_load_index"], 100.0)

    def test_dashboard_state_can_consume_neuradock_tcp_stream(self):
        fs = 250
        time_axis = np.arange(600) / fs
        samples = np.vstack(
            [
                8.0 * np.sin(2.0 * np.pi * (10.0 + 0.05 * channel) * time_axis)
                for channel in range(7)
            ]
        )

        def packet_line(line_index):
            fields = [f"{line_index / fs:.6f}", "0"]
            start = line_index * 5
            for offset in range(5):
                sample = samples[:, start + offset]
                fields.extend(f"{value:.8f}" for value in sample)
                fields.append("0")
            return ",".join(fields) + "\n"

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        ip, port = server.getsockname()

        def serve_once():
            conn, _addr = server.accept()
            with conn:
                conn.recv(16)
                for index in range(samples.shape[1] // 5):
                    conn.sendall(packet_line(index).encode("utf-8"))
            server.close()

        thread = threading.Thread(target=serve_once, daemon=True)
        thread.start()
        state = _DashboardState(
            demo_file=None,
            window_sec=2.0,
            step_sec=1.0,
            device_ip=ip,
            device_port=port,
        )
        try:
            result = {}
            for _ in range(40):
                result = state.current_status()
                if result.get("status") == "ok":
                    break
                time.sleep(0.1)

            self.assertEqual(result.get("source"), "neuradock_tcp")
            self.assertEqual(result.get("status"), "ok")
            self.assertIn("visual_load_index", result["current"])
            self.assertIn("stream", result)
            self.assertGreaterEqual(result["stream"]["samples_received"], 500)
        finally:
            state.close()

    def test_dashboard_api_sends_cors_headers(self):
        state = _DashboardState(demo_file=None, window_sec=2.0, step_sec=1.0)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        _host, port = server.server_address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/api/health")
            response = conn.getresponse()
            response.read()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
            self.assertIn("GET", response.getheader("Access-Control-Allow-Methods"))
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("OPTIONS", "/api/status")
            response = conn.getresponse()
            response.read()
            self.assertEqual(response.status, 204)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
            self.assertIn("Content-Type", response.getheader("Access-Control-Allow-Headers"))
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            state.close()


if __name__ == "__main__":
    unittest.main()
