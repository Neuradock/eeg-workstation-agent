import unittest

from neuradock_agent.profile import PROFILE


class ProfileTests(unittest.TestCase):
    def test_fixed_public_profile(self):
        self.assertEqual(PROFILE.sampling_rate_hz, 250)
        self.assertEqual(
            PROFILE.channels, ("CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2")
        )
        self.assertEqual(PROFILE.amplitude_unit, "uV")
        self.assertEqual(PROFILE.quality.outlier_absolute_amplitude, 100.0)
        self.assertEqual(PROFILE.channel_count, 7)
        self.assertEqual(PROFILE.bluetooth_samples_per_packet, 5)
        self.assertEqual(
            PROFILE.to_dict()["channel_index_map"],
            {
                "0": "CP5",
                "1": "CP6",
                "2": "PO3",
                "3": "PO4",
                "4": "O1",
                "5": "Oz",
                "6": "O2",
            },
        )


if __name__ == "__main__":
    unittest.main()
