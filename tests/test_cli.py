import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from neuradock_agent.artifacts import write_batch_clean_npz
from neuradock_agent.cli import (
    _interactive,
    _parser,
    _print_llm_interpretation,
    _resolve_analyze_inputs,
    main,
)
from neuradock_agent.demo import generate_visual_load_demo_file


class AnalyzeCliTests(unittest.TestCase):
    def test_llm_interpretation_display_retries_transient_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "llm_interpretation.md"
            path.write_text("saved", encoding="utf-8")
            output = StringIO()
            with (
                patch.object(
                    Path,
                    "read_text",
                    side_effect=[
                        PermissionError(13, "temporarily locked"),
                        "# Interpretation\n\nRecovered.",
                    ],
                ) as read_text,
                patch("neuradock_agent.cli.time.sleep") as sleep,
                redirect_stdout(output),
            ):
                _print_llm_interpretation(SimpleNamespace(run_dir=root))

            self.assertEqual(read_text.call_count, 2)
            sleep.assert_called_once_with(0.1)
            self.assertIn("Recovered.", output.getvalue())

    def test_llm_interpretation_display_lock_does_not_fail_completed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "llm_interpretation.md"
            path.write_text("saved", encoding="utf-8")
            output = StringIO()
            with (
                patch.object(
                    Path,
                    "read_text",
                    side_effect=PermissionError(13, "still locked"),
                ) as read_text,
                patch("neuradock_agent.cli.time.sleep"),
                redirect_stdout(output),
            ):
                _print_llm_interpretation(SimpleNamespace(run_dir=root))

            self.assertEqual(read_text.call_count, 8)
            self.assertIn(
                "LLM interpretation was saved but could not be displayed immediately.",
                output.getvalue(),
            )
            self.assertIn(str(path), output.getvalue())

    def test_interactive_mode_command_enters_llm_mode(self):
        with (
            patch("builtins.input", return_value="/mode LLM"),
            patch("neuradock_agent.cli._llm_mode", return_value=0) as llm_mode,
        ):
            self.assertEqual(_interactive(), 0)
        llm_mode.assert_called_once_with()

    def test_removed_commands_and_visual_workflow_parser(self):
        parser = _parser()
        for command in ("compare", "alpha", "offline"):
            with self.assertRaises(SystemExit):
                parser.parse_args([command])
        args = parser.parse_args(
            [
                "analysis",
                "recording.txt",
                "--workflow",
                "visual",
                "cognition",
                "index",
                "--window-sec",
                "4",
                "--step-sec",
                "1",
            ]
        )
        self.assertEqual(args.command, "analysis")
        self.assertEqual(args.workflow, ["visual", "cognition", "index"])
        comparison = parser.parse_args(
            [
                "analysis",
                "rest.npy",
                "task.npy",
                "--workflow",
                "visual",
                "cognition",
                "comparison",
                "--exclude-rest-trials",
                "2,5",
                "--exclude-task-trials",
                "7-9",
            ]
        )
        self.assertEqual(
            comparison.workflow,
            ["visual", "cognition", "comparison"],
        )
        self.assertEqual(comparison.exclude_rest_trials, "2,5")
        online = parser.parse_args(
            [
                "online",
                "--ip",
                "192.168.4.1",
                "--port",
                "9600",
                "--dashboard-port",
                "8766",
                "--no-open",
            ]
        )
        self.assertEqual(online.command, "online")
        self.assertEqual(online.ip, "192.168.4.1")
        self.assertEqual(online.port, 9600)
        self.assertEqual(online.dashboard_port, 8766)
        self.assertTrue(online.no_open)

    def test_batch_npz_preserves_variable_length_clean_arrays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_clean = root / "first_clean.npz"
            second_clean = root / "second_clean.npz"
            np.savez_compressed(first_clean, data=np.ones((7, 250)))
            np.savez_compressed(second_clean, data=np.ones((7, 625)) * 2)

            batch_path = write_batch_clean_npz(
                root / "clean_eeg_data_batch.npz",
                [
                    (root / "first.txt", first_clean),
                    (root / "second.txt", second_clean),
                ],
            )

            with np.load(batch_path, allow_pickle=False) as batch:
                self.assertEqual(batch["sample_counts"].tolist(), [250, 625])
                self.assertEqual(batch["clean_data_000"].shape, (7, 250))
                self.assertEqual(batch["clean_data_001"].shape, (7, 625))
                np.testing.assert_allclose(batch["clean_data_000"], 1.0)
                np.testing.assert_allclose(batch["clean_data_001"], 2.0)

    def test_resolve_files_directory_and_glob_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.txt"
            second = root / "second.TXT"
            ignored = root / "notes.md"
            nested = root / "nested"
            nested.mkdir()
            nested_file = nested / "third.txt"
            for path in (first, second, ignored, nested_file):
                path.write_text("test", encoding="utf-8")

            direct = _resolve_analyze_inputs([str(first), str(first)])
            directory = _resolve_analyze_inputs([str(root)])
            recursive = _resolve_analyze_inputs([str(root)], recursive=True)
            pattern = _resolve_analyze_inputs([str(root / "*.txt")])

            self.assertEqual(direct, [first.resolve()])
            self.assertEqual(directory, [first.resolve(), second.resolve()])
            self.assertEqual(
                set(recursive),
                {first.resolve(), second.resolve(), nested_file.resolve()},
            )
            self.assertEqual(set(pattern), {first.resolve(), second.resolve()})

    def test_batch_quality_writes_only_requested_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=12,
                file_name="first.txt",
                seed=31,
            )
            generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=12,
                file_name="second.txt",
                seed=37,
            )
            (root / "inputs" / "README.txt").unlink()
            output_root = root / "runs"

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "analyze",
                        str(root / "inputs"),
                        "--workflow",
                        "quality",
                        "--output-root",
                        str(output_root),
                    ]
                )

            self.assertEqual(code, 0, stderr.getvalue())
            run_dirs = sorted(path for path in output_root.iterdir() if path.is_dir())
            self.assertEqual(len(run_dirs), 2)
            self.assertEqual(
                {path.name for path in output_root.iterdir() if path.is_file()},
                {"clean_eeg_data_batch.npz"},
            )
            for run_dir in run_dirs:
                self.assertTrue((run_dir / "clean_eeg_data.npz").exists())
                self.assertTrue((run_dir / "figures" / "signal_quality.png").exists())
                self.assertTrue((run_dir / "figures" / "clean_signal.png").exists())
                self.assertEqual(
                    {path.name for path in run_dir.iterdir()},
                    {"figures", "clean_eeg_data.npz", "report.md", "results.json"},
                )
            self.assertIn("Successful: 2", stdout.getvalue())
            self.assertIn("Failed    : 0", stdout.getvalue())
            self.assertIn("Batch data:", stdout.getvalue())
            with np.load(
                output_root / "clean_eeg_data_batch.npz",
                allow_pickle=False,
            ) as batch:
                self.assertEqual(batch["data_keys"].tolist(), [
                    "clean_data_000",
                    "clean_data_001",
                ])
                self.assertEqual(batch["source_files"].shape, (2,))
                self.assertEqual(batch["sample_counts"].shape, (2,))
                self.assertEqual(batch["clean_data_000"].shape[0], 7)
                self.assertEqual(batch["clean_data_001"].shape[0], 7)

    def test_batch_continues_after_invalid_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_path = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=12,
                file_name="first.txt",
                seed=31,
            )
            closed_path = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=12,
                file_name="second.txt",
                seed=37,
            )
            invalid_path = root / "inputs" / "README.txt"
            output_root = root / "runs"

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "analyze",
                        str(open_path),
                        str(invalid_path),
                        str(closed_path),
                        "--workflow",
                        "quality",
                        "--output-root",
                        str(output_root),
                    ]
                )

            self.assertEqual(code, 1)
            run_dirs = sorted(path for path in output_root.iterdir() if path.is_dir())
            self.assertEqual(len(run_dirs), 2)
            self.assertEqual(
                {path.name for path in output_root.iterdir() if path.is_file()},
                {"clean_eeg_data_batch.npz"},
            )
            self.assertIn("Successful: 2", stdout.getvalue())
            self.assertIn("Failed    : 1", stdout.getvalue())
            self.assertIn(str(invalid_path.resolve()), stderr.getvalue())
            with np.load(
                output_root / "clean_eeg_data_batch.npz",
                allow_pickle=False,
            ) as batch:
                self.assertEqual(batch["source_files"].shape, (2,))
                self.assertNotIn(str(invalid_path.resolve()), batch["source_files"].tolist())

    def test_visual_cognition_index_cli_writes_load_report_and_figure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recording = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=18,
            )
            output_root = root / "runs"

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "analysis",
                        str(recording),
                        "--workflow",
                        "visual",
                        "cognition",
                        "index",
                        "--window-sec",
                        "4",
                        "--step-sec",
                        "1",
                        "--output-root",
                        str(output_root),
                    ]
                )

            self.assertEqual(code, 0, stderr.getvalue())
            run_dirs = list(output_root.iterdir())
            self.assertEqual(len(run_dirs), 1)
            run_dir = run_dirs[0]
            self.assertTrue((run_dir / "results.json").exists())
            self.assertTrue((run_dir / "report.md").exists())
            self.assertTrue(
                (run_dir / "figures" / "visual_cognitive_load.png").exists()
            )


if __name__ == "__main__":
    unittest.main()
