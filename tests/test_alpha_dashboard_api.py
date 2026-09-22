"""Alpha Experience API tests: synthetic signals and bounded loopback HTTP only."""

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from neuradock_agent.cli import main
from neuradock_agent.online import OnlineVisualLoadProcessor, _DashboardState, make_handler
from neuradock_agent.profile import PROFILE


def alpha_samples(amplitude=4.0, seconds=2.0):
    time_axis = np.arange(int(250 * seconds)) / 250
    signal = amplitude * np.sin(2 * np.pi * 10.0 * time_axis)
    return np.tile(signal, (7, 1))


class AlphaRelativeTests(unittest.TestCase):
    def test_window_warmup_and_first_two_clean_windows_have_no_feedback(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        processor.append(alpha_samples(seconds=1.0))
        warmup = processor.analyze_current()
        self.assertFalse(warmup["feedback_available"])
        self.assertEqual(warmup["feedback_reason"], "warming_up")
        for count in (1, 2):
            processor.append(alpha_samples())
            result = processor.analyze_current()
            self.assertIsNone(result["current"]["posterior_alpha_relative"])
            self.assertFalse(result["current"]["feedback_available"])
            self.assertEqual(result["current"]["feedback_reason"], "baseline_warming_up")
            self.assertEqual(result["baseline"]["history_count"], count)

    def test_ratio_matches_existing_suppression_and_power_multiplier(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        for amplitude in (2.0, 4.0, 8.0):
            processor.append(alpha_samples(amplitude))
            result = processor.analyze_current()
        current = result["current"]
        self.assertEqual(result["quality"]["status"], "pass")
        self.assertTrue(current["feedback_available"])
        self.assertEqual(current["feedback_reason"], "ready")
        self.assertAlmostEqual(
            current["posterior_alpha_relative"],
            10 ** (-current["alpha_suppression_from_baseline"]),
        )
        # Twice the amplitude means four times the power vs the median window.
        self.assertAlmostEqual(current["posterior_alpha_relative"], 4.0, places=7)
        self.assertEqual(result["baseline"]["reference"], "rolling_log_median")
        self.assertEqual(result["baseline"]["minimum_history_count"], 3)
        self.assertEqual(result["history"][-1], current)
        self.assertEqual(current["baseline_history_count"], 3)
        for point in result["history"][:-1]:
            self.assertIsNone(point["posterior_alpha_relative"])

    def test_quality_warning_does_not_update_baseline_or_allow_feedback(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        for _ in range(3):
            processor.append(alpha_samples())
            processor.analyze_current()
        clean_history = list(processor.history)
        # Muscle-band interference exercises the unchanged real QC algorithm.
        time_axis = np.arange(500) / 250
        noisy = alpha_samples() + np.tile(20 * np.sin(2 * np.pi * 30 * time_axis), (7, 1))
        processor.append(noisy)
        result = processor.analyze_current()
        self.assertEqual(result["quality"]["status"], "warning")
        self.assertEqual(processor.history, clean_history)
        self.assertEqual(result["current"]["feedback_reason"], "quality_warning")
        self.assertIsNone(result["current"]["posterior_alpha_relative"])
        self.assertFalse(result["history"][-1]["feedback_available"])

    def test_zero_power_is_not_a_valid_baseline_or_feedback_signal(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        for _ in range(4):
            processor.append(np.zeros((7, 500)))
            result = processor.analyze_current()
        self.assertEqual(result["baseline"]["history_count"], 0)
        self.assertIsNone(result["current"]["posterior_alpha_relative"])
        self.assertEqual(result["feedback_reason"], "invalid_alpha_power")
        json.dumps(result, allow_nan=False)

    def test_baseline_retains_last_600_clean_windows(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        processor.history = list(np.linspace(-1, 1, 600))
        previous = list(processor.history)
        processor.append(alpha_samples())
        result = processor.analyze_current()
        self.assertEqual(len(processor.history), 600)
        self.assertEqual(processor.history[:-1], previous[1:])
        self.assertEqual(result["baseline"]["rolling_log_alpha_median"], np.median(processor.history))

    def test_nonfinite_and_empty_samples_rejected(self):
        processor = OnlineVisualLoadProcessor(window_sec=2.0)
        for values in (np.full((7, 500), np.nan), np.full((7, 500), np.inf), np.empty((7, 0))):
            with self.assertRaises(ValueError):
                processor.append(values)


class AlphaSourceTests(unittest.TestCase):
    def test_waiting_state_has_explicit_profile_and_source(self):
        state = _DashboardState(None, window_sec=2.0, step_sec=1.0)
        result = state.current_status()
        self.assertEqual(result["source"], "manual_post")
        self.assertEqual(result["source_info"]["kind"], "manual_post")
        self.assertFalse(result["feedback_available"])
        self.assertEqual(result["feedback_reason"], "no_data")
        self.assertEqual(result["freshness"]["status"], "waiting_for_data")
        self.assertEqual(tuple(result["profile"]["channels"]), PROFILE.channels)
        self.assertEqual(result["profile"]["sampling_rate_hz"], 250)
        self.assertEqual(result["profile"]["amplitude_unit"], "uV")

    def test_file_names_never_determine_synthetic_provenance(self):
        with patch("neuradock_agent.online.read_neuradock_txt", return_value=SimpleNamespace(data=alpha_samples(seconds=12))):
            replay = _DashboardState(Path("synthetic_demo.txt"), 2.0, 1.0)
            synthetic = _DashboardState(Path("recording.txt"), 2.0, 1.0, source_kind="synthetic_demo")
        self.assertEqual(replay.current_status()["source_info"]["kind"], "recorded_replay")
        self.assertFalse(replay.current_status()["source_info"]["is_synthetic"])
        result = synthetic.next_demo()
        self.assertEqual(result["source_info"]["kind"], "synthetic_demo")
        self.assertTrue(result["source_info"]["is_synthetic"])
        self.assertEqual(result["source"], "demo_file")
        self.assertEqual(result["freshness"]["status"], "not_applicable")

    def test_live_source_label_and_stale_data_do_not_require_a_device(self):
        with patch("neuradock_agent.online.NeuraDockTCPStreamWorker") as worker:
            worker.return_value.status.return_value = {"connected": True}
            state = _DashboardState(None, 2.0, 1.0, device_ip="127.0.0.1", device_port=9600)
            worker.return_value.start.assert_called_once()
            self.assertEqual(state.current_status()["source_info"]["kind"], "live_device")
            self._assert_freshness_gating(state)
            state.close()

    def test_manual_data_expires_without_overwriting_historical_measurements(self):
        state = _DashboardState(None, 2.0, 1.0)
        self._assert_freshness_gating(state)
        state.reset()
        self.assertEqual(state.current_status()["freshness"]["status"], "waiting_for_data")

    def test_disconnect_blocks_fresh_feedback_without_rewriting_history(self):
        with patch("neuradock_agent.online.NeuraDockTCPStreamWorker") as worker:
            worker.return_value.status.return_value = {"connected": True}
            state = _DashboardState(None, 2.0, 1.0, device_ip="127.0.0.1", device_port=9600)
            with patch("neuradock_agent.online.time.monotonic", return_value=100.0):
                for _ in range(3):
                    state.append_online_samples(alpha_samples())
                self.assertTrue(state.current_status()["feedback_available"])
                worker.return_value.status.return_value = {"connected": False}
                result = state.current_status()
            self.assertEqual(result["freshness"]["status"], "fresh")
            self.assertFalse(result["feedback_available"])
            self.assertEqual(result["feedback_reason"], "device_disconnected")
            self.assertEqual(result["current"]["feedback_reason"], "device_disconnected")
            self.assertIsNone(result["current"]["posterior_alpha_relative"])
            self.assertTrue(result["history"][-1]["feedback_available"])
            self.assertTrue(state.latest_result["current"]["feedback_available"])
            state.close()

    def _assert_freshness_gating(self, state):
        with patch("neuradock_agent.online.time.monotonic", return_value=100.0):
            for _ in range(3):
                state.append_online_samples(alpha_samples())
        with patch("neuradock_agent.online.time.monotonic", return_value=102.0):
            fresh = state.current_status()
        self.assertTrue(fresh["current"]["feedback_available"])
        self.assertEqual(fresh["freshness"]["status"], "fresh")
        with patch("neuradock_agent.online.time.monotonic", return_value=104.0):
            stale = state.current_status()
        self.assertEqual(stale["freshness"]["status"], "stale")
        self.assertEqual(stale["current"]["feedback_reason"], "stale_data")
        self.assertIsNone(stale["current"]["posterior_alpha_relative"])
        self.assertFalse(stale["feedback_available"])
        self.assertTrue(stale["history"][-1]["feedback_available"])
        self.assertTrue(state.latest_result["current"]["feedback_available"])

    def test_source_transitions_reset_baseline(self):
        with patch("neuradock_agent.online.read_neuradock_txt", return_value=SimpleNamespace(data=alpha_samples(seconds=12))):
            state = _DashboardState(Path("demo.txt"), 2.0, 1.0, source_kind="synthetic_demo")
        for _ in range(4):
            state.next_demo()
        self.assertEqual(len(state.processor.history), 3)
        state.append_online_samples(alpha_samples(), source_kind="manual_post")
        result = state.current_status()
        self.assertEqual(result["source_info"]["kind"], "manual_post")
        self.assertEqual(result["baseline"]["history_count"], 1)
        self.assertFalse(result["feedback_available"])
        result = state.next_demo()
        self.assertEqual(result["source_info"]["kind"], "synthetic_demo")
        self.assertEqual(result["status"], "warming_up")

    def test_mismatched_source_configuration_rejected_before_connection(self):
        with self.assertRaises(ValueError):
            _DashboardState(None, 2.0, 1.0, source_kind="synthetic_demo")
        with self.assertRaises(ValueError):
            _DashboardState(None, 2.0, 1.0, device_ip="127.0.0.1")

    def test_invalid_manual_input_does_not_change_replay_source_or_history(self):
        with patch("neuradock_agent.online.read_neuradock_txt", return_value=SimpleNamespace(data=alpha_samples(seconds=12))):
            state = _DashboardState(Path("demo.txt"), 2.0, 1.0, source_kind="synthetic_demo")
        for _ in range(4):
            state.next_demo()
        with self.assertRaises(ValueError):
            state.append_online_samples(np.full((7, 10), np.nan), source_kind="manual_post")
        self.assertEqual(state.current_status()["source_info"]["kind"], "synthetic_demo")
        self.assertEqual(len(state.processor.history), 3)

    def test_cli_passes_explicit_synthetic_or_recorded_source(self):
        with patch("neuradock_agent.cli.generate_visual_load_demo_file", return_value=Path("generated.txt")), patch("neuradock_agent.cli.serve_online_dashboard") as serve:
            self.assertEqual(main(["serve"]), 0)
            self.assertEqual(serve.call_args.kwargs["source_kind"], "synthetic_demo")
            self.assertEqual(main(["serve", "--demo-file", "synthetic_visual_load_replay.txt"]), 0)
            self.assertEqual(serve.call_args.kwargs["source_kind"], "recorded_replay")


class AlphaDashboardHttpTests(unittest.TestCase):
    def setUp(self):
        self.state = _DashboardState(None, 2.0, 1.0)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.state.close()

    def request(self, path, method="GET", payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request(method, path, body=json.dumps(payload) if payload is not None else None, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_legacy_api_fields_remain_available_with_new_feedback_fields(self):
        for _ in range(3):
            status, _, body = self.request("/api/analyze", "POST", {"samples": alpha_samples().tolist()})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["status"], "ok")
        for key in ("preprocessing", "quality", "current", "baseline", "channels", "history", "interpretation_limits"):
            self.assertIn(key, result)
        for key in ("sample_index", "time_sec", "quality_status", "visual_load_index", "alpha_state", "posterior_log_alpha_power", "alpha_suppression_from_baseline", "alpha_peak_hz", "alpha_asymmetry_right_minus_left"):
            self.assertIn(key, result["current"])
        self.assertTrue(result["current"]["feedback_available"])
        status, headers, body = self.request("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(json.loads(body)["source_info"]["kind"], "manual_post")

    def test_static_asset_types_and_traversal_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "alpha.js").write_text("console.log('test');", encoding="utf-8")
            (assets / "alpha.css").write_text("body {}", encoding="utf-8")
            (assets / "private.py").write_text("secret", encoding="utf-8")
            (root / "secret.js").write_text("secret", encoding="utf-8")
            (root / "dashboard.html").write_text("alpha experience", encoding="utf-8")
            (root / "advanced.html").write_text("legacy dashboard", encoding="utf-8")
            with patch("neuradock_agent.online.WEB_ROOT", root):
                for path, content_type in (("/assets/alpha.js?v=1", "application/javascript; charset=utf-8"), ("/assets/alpha.css", "text/css; charset=utf-8")):
                    status, headers, _ = self.request(path)
                    self.assertEqual(status, 200)
                    self.assertEqual(headers["Content-Type"], content_type)
                    self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                for path in ("/assets/../secret.js", "/assets/%2e%2e/secret.js", "/assets/..%5csecret.js", "/assets/%2fsecret.js", "/assets/private.py", "/assets/missing.js"):
                    self.assertEqual(self.request(path)[0], 404, path)
                self.assertEqual(self.request("/")[2], b"alpha experience")
                self.assertEqual(self.request("/advanced")[2], b"legacy dashboard")

    def test_invalid_manual_payload_is_a_json_error(self):
        status, _, body = self.request("/api/analyze", "POST", [])
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))


if __name__ == "__main__":
    unittest.main()
