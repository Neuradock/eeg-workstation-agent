"""Versioned source of truth for the public NeuraDock v0.1 workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Tuple


__version__ = "2026.6.24"


@dataclass(frozen=True)
class QualityThresholds:
    line_noise_power: float = 10.0
    emg_power: float = 20.0
    outlier_count_per_second: int = 2
    outlier_absolute_amplitude: float = 100.0
    bad_channel_segment_ratio: float = 0.4
    minimum_neighbor_correlation: float = 0.15


@dataclass(frozen=True)
class NeuraDockProfile:
    profile_version: str = "1.1"
    device: str = "NeuraDock EEG Workstation"
    hardware_revision: str = "public-profile-v2"
    sampling_rate_hz: int = 250
    channels: Tuple[str, ...] = ("CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2")
    amplitude_unit: str = "uV"
    line_frequency_hz: float = 50.0
    tcp_default_ip: str = "127.0.0.1"
    tcp_default_port: int = 9600
    tcp_start_command: bytes = b"start"
    packet_total_channels: int = 8
    packet_used_channels: int = 7
    bluetooth_samples_per_packet: int = 5
    quality: QualityThresholds = QualityThresholds()

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["tcp_start_command"] = self.tcp_start_command.decode("ascii")
        payload["channel_count"] = self.channel_count
        payload["channel_index_map"] = {
            str(index): channel for index, channel in enumerate(self.channels)
        }
        payload["unit_status"] = "Parsed EEG amplitudes are represented in microvolts."
        return payload


PROFILE = NeuraDockProfile()

CHANNEL_LAYOUT_2D = {
    "O1": (-0.35, -0.95),
    "O2": (0.35, -0.95),
    "Oz": (0.0, -1.0),
    "PO3": (-0.3, -0.65),
    "PO4": (0.3, -0.65),
    "CP5": (-0.65, -0.25),
    "CP6": (0.65, -0.25),
}

NEIGHBORS = {
    "O1": ("Oz", "PO3"),
    "O2": ("Oz", "PO4"),
    "Oz": ("O1", "O2", "PO3", "PO4"),
    "PO3": ("O1", "Oz", "PO4", "CP5"),
    "PO4": ("O2", "Oz", "PO3", "CP6"),
    "CP5": ("PO3", "CP6"),
    "CP6": ("PO4", "CP5"),
}
