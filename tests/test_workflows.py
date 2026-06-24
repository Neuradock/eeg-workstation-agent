import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from neuradock_agent.demo import generate_visual_load_demo_file
from neuradock_agent.io import read_neuradock_txt
from neuradock_agent.models import Recording, TrialBatch
from neuradock_agent.quality_tools import run_preprocessing_quality
from neuradock_agent.workflows import (
    run_alpha_dynamics,
    run_psd_bandpower,
    run_signal_quality,
    run_visual_cognitive_load,
    run_visual_cognitive_load_comparison,
)


class WorkflowTests(unittest.TestCase):
    @staticmethod
    def _trial_batch(
        source: str,
        alpha_amplitude: float,
        trial_count: int = 8,
    ) -> TrialBatch:
        fs = 250
        samples = 1016
        time = np.arange(samples) / fs
        rng = np.random.default_rng(17)
        trials = []
        for trial_index in range(trial_count):
            channels = []
            for channel_index in range(7):
                signal = alpha_amplitude * np.sin(
                    2.0
                    * np.pi
                    * (10.0 + 0.05 * channel_index)
                    * time
                    + 0.1 * trial_index
                )
                channels.append(signal + rng.normal(0.0, 0.4, samples))
            trials.append(channels)
        return TrialBatch(
            data=np.asarray(trials),
            source=Path(source),
        )

    def test_quality_pipeline_rejects_an_emg_contaminated_segment(self):
        fs = 250
        time = np.arange(fs * 6) / fs
        data = np.vstack(
            [
                5.0 * np.sin(2.0 * np.pi * (9.0 + index * 0.2) * time)
                for index in range(7)
            ]
        )
        contaminated = (time >= 2.0) & (time < 3.0)
        data[0, contaminated] += 80.0 * np.sin(
            2.0 * np.pi * 30.0 * time[contaminated]
        )
        recording = Recording(
            data=data,
            source=Path("synthetic_emg_contamination.txt"),
            transport="synthetic",
        )

        bundle = run_preprocessing_quality(recording)

        self.assertGreaterEqual(bundle.result["rejected_segment_count"], 1)
        self.assertLess(bundle.result["retention_rate"], 1.0)
        self.assertLess(bundle.clean.shape[1], data.shape[1])

    def test_alpha_dynamics_uses_synthetic_alpha_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=36,
            )
            run = run_alpha_dynamics(
                read_neuradock_txt(source),
                output_root=root / "runs",
            )
            payload = json.loads(run.results_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["workflow"], "alpha_dynamics")
            self.assertGreater(payload["summary"]["state_counts"]["weak_alpha"], 0)
            self.assertGreater(payload["summary"]["state_counts"]["strong_alpha"], 0)
            self.assertGreater(
                payload["summary"]["max_alpha_suppression_from_baseline"],
                0,
            )
            self.assertEqual(len(run.figure_paths), 3)
            self.assertTrue(all(path.exists() for path in run.figure_paths))

    def test_offline_visual_load_tracks_synthetic_alpha_suppression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            demo_path = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=36,
            )
            run = run_visual_cognitive_load(
                read_neuradock_txt(demo_path),
                output_root=root / "runs",
            )
            payload = json.loads(run.results_path.read_text(encoding="utf-8"))
            valid_windows = [item for item in payload["windows"] if item["valid"]]
            first_third = [
                item["load_percentile"]
                for item in valid_windows
                if item["center_sec"] < 12.0
            ]
            last_third = [
                item["load_percentile"]
                for item in valid_windows
                if item["center_sec"] >= 24.0
            ]
            self.assertLess(np.mean(first_third), np.mean(last_third))
            self.assertGreater(payload["summary"]["class_counts"]["low"], 0)
            self.assertGreater(payload["summary"]["class_counts"]["medium"], 0)
            self.assertGreater(payload["summary"]["class_counts"]["high"], 0)
            self.assertEqual(
                {path.name for path in run.run_dir.iterdir()},
                {"figures", "report.md", "results.json"},
            )
            self.assertTrue(
                (run.run_dir / "figures" / "visual_cognitive_load.png").exists()
            )

    def test_quality_and_psd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_path = generate_visual_load_demo_file(
                root / "inputs",
                duration_sec=12,
            )
            recording = read_neuradock_txt(open_path)
            quality_run = run_signal_quality(recording, root / "quality")
            psd_run = run_psd_bandpower(recording, root / "psd")
            quality = json.loads(quality_run.results_path.read_text(encoding="utf-8"))
            psd = json.loads(psd_run.results_path.read_text(encoding="utf-8"))
            self.assertGreater(quality["retention_rate"], 0.8)
            self.assertEqual(quality["method"], "neuradock_preprocess_v17_tools")
            self.assertIn("spatial_quality", quality)
            self.assertIn("acquisition_context", quality)
            self.assertEqual(len(quality_run.figure_paths), 2)
            self.assertEqual(len(quality_run.data_paths), 1)
            for path in (*quality_run.figure_paths, *quality_run.data_paths):
                self.assertTrue(path.exists(), path)
            self.assertEqual(
                {path.name for path in quality_run.run_dir.iterdir()},
                {"figures", "clean_eeg_data.npz", "report.md", "results.json"},
            )
            with np.load(quality_run.run_dir / "clean_eeg_data.npz") as clean:
                self.assertEqual(clean["data"].shape[0], 7)
                self.assertEqual(
                    clean["data"].shape[1], quality["clean_shape"][1]
                )
                self.assertEqual(
                    clean["keep_mask"].shape[0], quality["raw_shape"][1]
                )
            self.assertGreater(psd["spectral"]["posterior_alpha_peak_hz"], 8.0)
            self.assertLess(psd["spectral"]["posterior_alpha_peak_hz"], 13.0)

    def test_trial_batch_visual_load_preserves_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self._trial_batch("task_trials.npy", alpha_amplitude=8.0)
            run = run_visual_cognitive_load(batch, root)
            payload = json.loads(run.results_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["input_structure"], "trial_batch")
            self.assertEqual(payload["recording"]["trial_count"], 8)
            self.assertEqual(payload["summary"]["window_count"], 8)
            self.assertEqual(
                [item["trial_number"] for item in payload["windows"]],
                list(range(1, 9)),
            )
            self.assertTrue(run.figure_paths[0].exists())

    def test_trial_batch_quality_writes_masked_trial_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = self._trial_batch("trials.npy", alpha_amplitude=8.0)
            run = run_signal_quality(batch, root)
            payload = json.loads(run.results_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["input_structure"], "trial_batch")
            self.assertTrue(run.report_path.exists())
            self.assertEqual(run.data_paths[0].name, "clean_eeg_trials.npz")
            with np.load(run.data_paths[0], allow_pickle=False) as clean:
                self.assertEqual(clean["data"].shape, (8, 7, 1016))
                self.assertEqual(clean["keep_masks"].shape, (8, 1016))

    def test_rest_task_comparison_uses_raw_alpha_contrast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rest = self._trial_batch("rest.npy", alpha_amplitude=12.0)
            task = self._trial_batch("task.npy", alpha_amplitude=5.0)
            run = run_visual_cognitive_load_comparison(rest, task, root)
            payload = json.loads(run.results_path.read_text(encoding="utf-8"))
            contrast = payload["descriptive_contrast"][
                "posterior_log_alpha_power"
            ]

            self.assertEqual(
                payload["workflow"],
                "visual_cognitive_load_comparison",
            )
            self.assertLess(contrast["task_minus_rest"], 0)
            self.assertLess(contrast["task_to_rest_power_ratio"], 1)
            self.assertEqual(len(run.figure_paths), 3)
            self.assertTrue(all(path.exists() for path in run.figure_paths))


if __name__ == "__main__":
    unittest.main()
