import tempfile
import unittest
from pathlib import Path

import numpy as np

from neuradock_agent.io import (
    packet_fields_to_samples,
    parse_trial_selection,
    read_neuradock_npy,
    read_neuradock_txt,
    write_neuradock_bluetooth_txt,
)
from neuradock_agent.profile import PROFILE


class IOTests(unittest.TestCase):
    def test_bluetooth_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recording.txt"
            data = np.arange(7 * 20, dtype=float).reshape(7, 20)
            write_neuradock_bluetooth_txt(path, data)
            recording = read_neuradock_txt(path)
            self.assertEqual(recording.transport, "bluetooth")
            self.assertEqual(recording.data.shape, (7, 20))
            np.testing.assert_allclose(recording.data, data)

    def test_usb_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usb.txt"
            fields = ["0.0", "marker"] + [str(value) for value in range(7)] + ["0"]
            path.write_text(",".join(fields) + "\n", encoding="utf-8")
            recording = read_neuradock_txt(path)
            self.assertEqual(recording.transport, "usb")
            self.assertEqual(recording.data.shape, (7, 1))
            self.assertEqual(recording.channels, PROFILE.channels)
            np.testing.assert_allclose(recording.data[:, 0], np.arange(7))

    def test_packet_parser(self):
        fields = ["1.0", "3"]
        for sample in range(5):
            fields.extend(str(sample * 10 + channel) for channel in range(8))
        packet, marker, timestamp = packet_fields_to_samples(fields)
        self.assertEqual(packet.shape, (5, PROFILE.channel_count))
        self.assertEqual(marker, "3")
        self.assertEqual(timestamp, 1.0)

    def test_trial_npy_loader_orients_and_excludes_one_based_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trials.npy"
            data = np.arange(5 * 1000 * 7, dtype=float).reshape(5, 1000, 7)
            np.save(path, data)

            batch = read_neuradock_npy(path, exclude_trials=(2, 4))

            self.assertEqual(batch.data.shape, (3, 7, 1000))
            self.assertEqual(batch.trial_numbers, (1, 3, 5))
            self.assertEqual(
                batch.metadata["input_axis_order"],
                "trials_samples_channels",
            )
            np.testing.assert_allclose(batch.data[0], data[0].T)

    def test_legacy_numeric_object_npy_uses_restricted_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.npy"
            data = np.arange(4 * 7 * 1000, dtype=float).reshape(4, 7, 1000)
            np.save(path, data.astype(object))

            batch = read_neuradock_npy(path)

            self.assertEqual(batch.data.dtype, np.float64)
            np.testing.assert_allclose(batch.data, data)

    def test_trial_selection_parser(self):
        self.assertEqual(
            parse_trial_selection("1, 3, 7-9"),
            (1, 3, 7, 8, 9),
        )
        with self.assertRaisesRegex(ValueError, "1-based"):
            parse_trial_selection("0")


if __name__ == "__main__":
    unittest.main()
