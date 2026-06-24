import json
import tempfile
import unittest
import urllib.error
from io import BytesIO, StringIO
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from neuradock_agent.cli import _print_llm_menu
from neuradock_agent.agent import AgentInputs, execute_request
from neuradock_agent.context_pack import load_context_pack
from neuradock_agent.demo import generate_visual_load_demo_file
from neuradock_agent.io import read_neuradock_txt
from neuradock_agent.llm import LLMPlan, chat_with_llm, plan_with_llm
from neuradock_agent.llm_config import (
    LLMConfig,
    load_llm_config,
    prompt_for_llm_config,
)
from neuradock_agent.llm_interpretation import (
    _response_language_instruction,
    build_interpretation_summary,
    interpret_run_with_llm,
)
from neuradock_agent.workflows import (
    run_psd_bandpower,
    run_visual_cognitive_load,
)


class LLMModeTests(unittest.TestCase):
    def test_context_pack_contains_formal_hardware_and_quality_policy(self):
        planning = load_context_pack("planning")
        interpretation = load_context_pack(
            "interpretation",
            workflow="visual_cognitive_load",
        )

        self.assertEqual(planning.version, "2026.6.24")
        self.assertIn(
            "0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2",
            planning.content,
        )
        self.assertIn("absolute outlier threshold is 100", planning.content)
        self.assertIn(
            "cases/visual-cognitive-load-quality-limited.md",
            interpretation.files,
        )
        normalized = " ".join(interpretation.content.split())
        self.assertIn("Continue to explain", normalized)

    def test_low_quality_summary_requires_prominent_warning(self):
        compact = build_interpretation_summary(
            {
                "workflow": "signal_quality",
                "status": "warning",
                "recording": {"duration_sec": 10.0},
                "retention_rate": 0.62,
                "warnings": ["Low retention."],
            }
        )

        self.assertTrue(compact["quality"]["quality_warning_required"])

    def test_comparison_summary_excludes_window_arrays(self):
        condition = {
            "workflow": "visual_cognitive_load",
            "status": "pass",
            "quality": {
                "status": "pass",
                "retention_rate": 1.0,
                "warnings": [],
            },
            "parameters": {},
            "classification": {},
            "summary": {
                "window_count": 3,
                "valid_window_count": 3,
                "excluded_window_count": 0,
                "label_ranges": [],
            },
            "windows": [
                {
                    "valid": True,
                    "load_percentile": 50,
                    "posterior_log_alpha_power": 1.0,
                    "alpha_peak_hz": 10.0,
                    "alpha_asymmetry_right_minus_left": 0.0,
                }
            ],
            "warnings": [],
            "interpretation_limits": [],
        }
        compact = build_interpretation_summary(
            {
                "workflow": "visual_cognitive_load_comparison",
                "status": "pass",
                "condition_labels": ["Rest", "Task"],
                "conditions": {"rest": condition, "task": condition},
                "descriptive_contrast": {
                    "posterior_log_alpha_power": {
                        "task_minus_rest": -0.1
                    }
                },
                "warnings": [],
                "interpretation_limits": [],
            }
        )
        serialized = json.dumps(compact)

        self.assertNotIn('"windows"', serialized)
        self.assertFalse(compact["raw_eeg_included"])

    def test_interpretation_language_is_derived_from_original_request(self):
        self.assertIn(
            "entire interpretation in English",
            _response_language_instruction("visual cognitive load"),
        )
        self.assertIn(
            "entire interpretation in Simplified Chinese",
            _response_language_instruction("解释视觉认知负荷"),
        )

    def test_planner_receives_reviewed_context(self):
        config = LLMConfig("secret", "https://example.test/v1", "test-model")
        with patch(
            "neuradock_agent.llm.chat_with_llm",
            return_value='{"intent":"signal_quality","reason":"quality request"}',
        ) as chat:
            plan = plan_with_llm("check quality", config)

        self.assertEqual(plan.intent, "signal_quality")
        messages = chat.call_args.args[1]
        system = messages[0]["content"]
        self.assertIn("NeuraDock System Context", system)
        self.assertIn("Workflow Planning Instruction", system)
        self.assertIn("100 microvolts", system)

    def test_temperature_one_provider_error_is_retried_automatically(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "completed"}}]}
                ).encode("utf-8")

        error = urllib.error.HTTPError(
            "https://example.test/v1/chat/completions",
            400,
            "Bad Request",
            {},
            BytesIO(
                b'{"error":{"message":"invalid temperature: only 1 is allowed '
                b'for this model"}}'
            ),
        )
        config = LLMConfig("secret", "https://example.test/v1", "kimi-k2.6")

        with patch(
            "neuradock_agent.llm.urllib.request.urlopen",
            side_effect=[error, FakeResponse()],
        ) as urlopen:
            content = chat_with_llm(
                config,
                [{"role": "user", "content": "hello"}],
                temperature=0,
            )

        self.assertEqual(content, "completed")
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(
            [call.kwargs["timeout"] for call in urlopen.call_args_list],
            [120, 120],
        )
        bodies = [
            json.loads(call.args[0].data.decode("utf-8"))
            for call in urlopen.call_args_list
        ]
        self.assertEqual([body["temperature"] for body in bodies], [0, 1])

    def test_transient_network_error_is_retried_automatically(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "completed"}}]}
                ).encode("utf-8")

        error = urllib.error.URLError(
            ConnectionResetError(10054, "Connection reset by peer")
        )
        config = LLMConfig("secret", "https://example.test/v1", "test-model")

        with (
            patch(
                "neuradock_agent.llm.urllib.request.urlopen",
                side_effect=[error, FakeResponse()],
            ) as urlopen,
            patch("neuradock_agent.llm.time.sleep") as sleep,
        ):
            content = chat_with_llm(
                config,
                [{"role": "user", "content": "hello"}],
            )

        self.assertEqual(content, "completed")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_persistent_network_error_reports_retry_count(self):
        error = urllib.error.URLError(
            ConnectionResetError(10054, "Connection reset by peer")
        )
        config = LLMConfig("secret", "https://example.test/v1", "test-model")

        with (
            patch(
                "neuradock_agent.llm.urllib.request.urlopen",
                side_effect=error,
            ) as urlopen,
            patch("neuradock_agent.llm.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(
                ConnectionError,
                "connection failed after 3 attempts",
            ):
                chat_with_llm(
                    config,
                    [{"role": "user", "content": "hello"}],
                )

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.5, 1.0],
        )

    def test_llm_menu_is_english_and_lists_supported_actions(self):
        output = StringIO()
        with redirect_stdout(output):
            _print_llm_menu("test-model")

        text = output.getvalue()
        self.assertIn("What can I do for you?", text)
        self.assertIn("1. Check EEG signal quality", text)
        self.assertIn("5. Run the no-hardware demonstration", text)
        self.assertIn("Current model: test-model", text)

    def test_first_time_configuration_is_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llm_config.json"
            answers = iter(["https://example.test/v1", "provider-model"])
            messages = []

            config = prompt_for_llm_config(
                path=path,
                input_fn=lambda prompt: next(answers),
                secret_fn=lambda prompt: "secret-key",
                print_fn=messages.append,
            )

            self.assertEqual(config.model, "provider-model")
            self.assertEqual(load_llm_config(path), config)
            self.assertTrue(path.exists())
            self.assertNotIn("secret-key", "\n".join(messages))
            self.assertNotIn("secret-key", repr(config))

    def test_compact_summary_excludes_raw_arrays_and_window_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_path = generate_visual_load_demo_file(
                root / "inputs", duration_sec=18
            )
            recording = read_neuradock_txt(recording_path)
            visual_run = run_visual_cognitive_load(recording, root / "visual")
            psd_run = run_psd_bandpower(recording, root / "psd")

            for run in (visual_run, psd_run):
                payload = json.loads(run.results_path.read_text(encoding="utf-8"))
                compact = build_interpretation_summary(payload)
                serialized = json.dumps(compact)
                self.assertNotIn('"windows"', serialized)
                self.assertNotIn('"psd_by_channel"', serialized)
                self.assertNotIn('"frequency_hz"', serialized)
                self.assertNotIn('"data"', serialized)
                self.assertNotIn('"label_zh"', serialized)
                self.assertFalse(compact["raw_eeg_included"])

    def test_interpretation_failure_keeps_local_results_and_writes_failure_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_path = generate_visual_load_demo_file(
                root / "inputs", duration_sec=18
            )
            run = run_visual_cognitive_load(
                read_neuradock_txt(recording_path), root / "runs"
            )
            config = LLMConfig(
                "super-secret-key", "https://example.test/v1", "test-model"
            )

            with patch(
                "neuradock_agent.llm_interpretation.chat_with_llm",
                side_effect=ConnectionError("service unavailable"),
            ):
                path, metadata = interpret_run_with_llm(
                    run, "解释视觉认知负荷", config
                )

            self.assertTrue(run.results_path.exists())
            self.assertTrue(run.report_path.exists())
            self.assertTrue(path.exists())
            self.assertEqual(metadata["status"], "failed")
            text = path.read_text(encoding="utf-8")
            self.assertIn("local `report.md` and `results.json` remain complete", text)
            self.assertIn("Raw EEG sent to model: **no**", text)

    def test_llm_agent_plans_runs_interprets_and_records_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_path = generate_visual_load_demo_file(
                root / "inputs", duration_sec=18
            )
            config = LLMConfig(
                "super-secret-key", "https://example.test/v1", "test-model"
            )
            plan = LLMPlan(
                "visual_cognitive_load",
                "The user requested the visual cognition index.",
                config.model,
            )
            with (
                patch("neuradock_agent.agent.plan_with_llm", return_value=plan),
                patch(
                    "neuradock_agent.llm_interpretation.chat_with_llm",
                    return_value="## Main finding\nRelative load increased later.",
                ) as interpretation_chat,
            ):
                run = execute_request(
                    "分析并解释视觉认知负荷",
                    AgentInputs(file=recording_path),
                    root / "runs",
                    use_llm=True,
                    llm_config=config,
                )

            trace = json.loads(
                (run.run_dir / "agent_trace.json").read_text(encoding="utf-8")
            )
            trace_text = (run.run_dir / "agent_trace.json").read_text(
                encoding="utf-8"
            )
            self.assertEqual(trace["intent"], "visual_cognitive_load")
            self.assertEqual(trace["planner_status"], "success")
            self.assertEqual(
                trace["planner_prompt_version"],
                "neuradock-workflow-planner-v2",
            )
            self.assertIsNotNone(trace["planner_called_at"])
            self.assertFalse(trace["raw_eeg_sent_to_planner"])
            self.assertFalse(trace["interpretation"]["raw_eeg_sent"])
            self.assertEqual(trace["interpretation"]["status"], "success")
            self.assertEqual(trace["context"]["planner"]["version"], "2026.6.24")
            self.assertEqual(
                trace["context"]["interpretation"]["version"],
                "2026.6.24",
            )
            self.assertEqual(len(trace["context"]["planner"]["sha256"]), 64)
            self.assertIn(
                "cases/visual-cognitive-load-quality-limited.md",
                trace["context"]["interpretation"]["files"],
            )
            interpretation_system = interpretation_chat.call_args.args[1][0][
                "content"
            ]
            self.assertIn("Current Implementation Map", interpretation_system)
            self.assertIn("quality_warning_required", interpretation_system)
            self.assertIn(
                "entire interpretation in Simplified Chinese",
                interpretation_system,
            )
            self.assertEqual(
                trace["interpretation"]["response_language_instruction"],
                (
                    "The original request is in Chinese. Write the entire "
                    "interpretation in Simplified Chinese."
                ),
            )
            self.assertNotIn("super-secret-key", trace_text)
            self.assertTrue((run.run_dir / "llm_interpretation.md").exists())

    def test_planner_failure_falls_back_to_local_router(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording_path = generate_visual_load_demo_file(
                root / "inputs", duration_sec=12
            )
            config = LLMConfig("key", "https://example.test/v1", "test-model")
            with (
                patch(
                    "neuradock_agent.agent.plan_with_llm",
                    side_effect=ConnectionError("planner unavailable"),
                ),
                patch(
                    "neuradock_agent.llm_interpretation.chat_with_llm",
                    side_effect=ConnectionError("interpreter unavailable"),
                ),
            ):
                run = execute_request(
                    "检查信号质量",
                    AgentInputs(file=recording_path),
                    root / "runs",
                    use_llm=True,
                    llm_config=config,
                )

            trace = json.loads(
                (run.run_dir / "agent_trace.json").read_text(encoding="utf-8")
            )
            self.assertEqual(trace["planner_status"], "fallback")
            self.assertEqual(trace["intent"], "signal_quality")
            self.assertTrue(run.results_path.exists())
            self.assertTrue(run.report_path.exists())
            self.assertEqual(trace["interpretation"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
