from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .profile import PROFILE


@dataclass
class Recording:
    data: np.ndarray
    source: Path
    transport: str
    fs: int = PROFILE.sampling_rate_hz
    channels: Tuple[str, ...] = PROFILE.channels
    timestamps: Optional[np.ndarray] = None
    markers: Optional[np.ndarray] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = Path(self.source)
        self.data = np.asarray(self.data, dtype=float)
        if self.data.ndim != 2:
            raise ValueError("Recording data must have shape (channels, samples).")
        if self.data.shape[0] != len(self.channels):
            raise ValueError(
                "NeuraDock recording must contain exactly "
                f"{len(self.channels)} channels in order {list(self.channels)}; "
                f"received shape {self.data.shape}."
            )
        if self.data.shape[1] == 0:
            raise ValueError("Recording contains no valid samples.")
        if not np.all(np.isfinite(self.data)):
            raise ValueError("Recording contains NaN or infinite EEG values.")
        if self.fs != PROFILE.sampling_rate_hz:
            raise ValueError(
                f"NeuraDock v0.1 requires {PROFILE.sampling_rate_hz} Hz, got {self.fs} Hz."
            )
        if self.timestamps is not None and len(self.timestamps) != self.n_samples:
            raise ValueError("Timestamp count does not match sample count.")
        if self.markers is not None and len(self.markers) != self.n_samples:
            raise ValueError("Marker count does not match sample count.")

    @property
    def n_samples(self) -> int:
        return int(self.data.shape[1])

    @property
    def duration_sec(self) -> float:
        return self.n_samples / float(self.fs)

    def summary(self) -> Dict[str, object]:
        return {
            "source": str(self.source),
            "transport": self.transport,
            "shape": list(self.data.shape),
            "sampling_rate_hz": self.fs,
            "duration_sec": self.duration_sec,
            "channels": list(self.channels),
            "amplitude_unit": PROFILE.amplitude_unit,
            "metadata": self.metadata,
        }


@dataclass
class TrialBatch:
    data: np.ndarray
    source: Path
    transport: str = "npy_trial_batch"
    fs: int = PROFILE.sampling_rate_hz
    channels: Tuple[str, ...] = PROFILE.channels
    trial_numbers: Tuple[int, ...] = ()
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = Path(self.source)
        self.data = np.asarray(self.data, dtype=float)
        if self.data.ndim != 3:
            raise ValueError(
                "Trial batch data must have shape (trials, channels, samples)."
            )
        if self.data.shape[0] == 0:
            raise ValueError("Trial batch contains no retained trials.")
        if self.data.shape[1] != len(self.channels):
            raise ValueError(
                "NeuraDock trial batch must contain exactly "
                f"{len(self.channels)} channels in order {list(self.channels)}; "
                f"received shape {self.data.shape}."
            )
        if self.data.shape[2] == 0:
            raise ValueError("Trial batch contains no EEG samples.")
        if not np.all(np.isfinite(self.data)):
            raise ValueError("Trial batch contains NaN or infinite EEG values.")
        if self.fs != PROFILE.sampling_rate_hz:
            raise ValueError(
                f"NeuraDock v0.1 requires {PROFILE.sampling_rate_hz} Hz, got "
                f"{self.fs} Hz."
            )
        if not self.trial_numbers:
            self.trial_numbers = tuple(range(1, self.data.shape[0] + 1))
        if len(self.trial_numbers) != self.data.shape[0]:
            raise ValueError("Trial-number count does not match retained trials.")

    @property
    def n_trials(self) -> int:
        return int(self.data.shape[0])

    @property
    def samples_per_trial(self) -> int:
        return int(self.data.shape[2])

    @property
    def trial_duration_sec(self) -> float:
        return self.samples_per_trial / float(self.fs)

    def recordings(self) -> List[Recording]:
        return [
            Recording(
                data=self.data[index],
                source=self.source,
                transport=self.transport,
                fs=self.fs,
                channels=self.channels,
                metadata={
                    **self.metadata,
                    "trial_number": trial_number,
                    "trial_position": index + 1,
                    "trial_count": self.n_trials,
                },
            )
            for index, trial_number in enumerate(self.trial_numbers)
        ]

    def summary(self) -> Dict[str, object]:
        return {
            "source": str(self.source),
            "transport": self.transport,
            "shape": list(self.data.shape),
            "sampling_rate_hz": self.fs,
            "trial_count": self.n_trials,
            "samples_per_trial": self.samples_per_trial,
            "trial_duration_sec": self.trial_duration_sec,
            "channels": list(self.channels),
            "amplitude_unit": PROFILE.amplitude_unit,
            "retained_trial_numbers": list(self.trial_numbers),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    results_path: Path
    report_path: Path
    figure_paths: Tuple[Path, ...]
    data_paths: Tuple[Path, ...] = ()
