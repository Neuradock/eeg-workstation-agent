"""Readers and writers for the fixed NeuraDock USB/Bluetooth text protocol."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from .models import Recording, TrialBatch
from .profile import PROFILE


PathLike = Union[str, Path]


class _RestrictedNumpyUnpickler(pickle.Unpickler):
    """Load legacy numeric object arrays without accepting arbitrary classes."""

    _ALLOWED = {
        ("numpy", "ndarray"),
        ("numpy", "dtype"),
        ("numpy._core.multiarray", "_reconstruct"),
        ("numpy.core.multiarray", "_reconstruct"),
    }

    def find_class(self, module: str, name: str) -> object:
        if (module, name) in self._ALLOWED:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"Unsupported object in legacy NPY file: {module}.{name}"
        )


def _load_numeric_npy(path: Path) -> Tuple[np.ndarray, str]:
    try:
        array = np.asarray(np.load(path, allow_pickle=False))
        return array, str(array.dtype)
    except ValueError as exc:
        if "Object arrays cannot be loaded" not in str(exc):
            raise

    with path.open("rb") as handle:
        version = np.lib.format.read_magic(handle)
        if version == (1, 0):
            _, _, dtype = np.lib.format.read_array_header_1_0(handle)
        elif version in {(2, 0), (3, 0)}:
            _, _, dtype = np.lib.format.read_array_header_2_0(handle)
        else:
            raise ValueError(f"Unsupported NPY format version {version}.")
        if not dtype.hasobject:
            raise ValueError("Could not load numeric NPY array.")
        try:
            raw = _RestrictedNumpyUnpickler(handle).load()
        except pickle.UnpicklingError as unpickle_error:
            raise ValueError(
                "The NPY object array contains unsupported non-numeric objects."
            ) from unpickle_error
    try:
        return np.asarray(raw.tolist(), dtype=float), str(dtype)
    except (AttributeError, TypeError, ValueError) as convert_error:
        raise ValueError(
            "The NPY object array could not be converted to numeric EEG data."
        ) from convert_error


def parse_trial_selection(
    value: str,
    total_trials: Optional[int] = None,
) -> Tuple[int, ...]:
    """Parse one-based trial numbers such as ``1,3,8-10``."""

    text = str(value or "").strip()
    if not text:
        return ()
    selected = set()
    for token in text.replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise ValueError(f"Invalid trial range: {token}") from exc
            if start > end:
                raise ValueError(f"Trial range must be ascending: {token}")
            selected.update(range(start, end + 1))
        else:
            try:
                selected.add(int(token))
            except ValueError as exc:
                raise ValueError(f"Invalid trial number: {token}") from exc
    if any(index < 1 for index in selected):
        raise ValueError("Trial numbers are 1-based and must be positive.")
    if total_trials is not None and any(index > total_trials for index in selected):
        raise ValueError(
            f"Trial selection exceeds available range 1-{total_trials}."
        )
    return tuple(sorted(selected))


def read_neuradock_npy(
    path: PathLike,
    exclude_trials: Sequence[int] = (),
) -> TrialBatch:
    """Read a trial batch shaped (trials, 7, samples) or (trials, samples, 7)."""

    source = Path(path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"NeuraDock trial batch not found: {source}")
    batch, original_dtype = _load_numeric_npy(source)
    if batch.ndim != 3:
        raise ValueError(
            "Expected NPY shape (trials, 7, samples) or "
            f"(trials, samples, 7), got {batch.shape}."
        )
    if batch.shape[1] == PROFILE.channel_count:
        oriented = batch
        input_axis_order = "trials_channels_samples"
    elif batch.shape[2] == PROFILE.channel_count:
        oriented = np.transpose(batch, (0, 2, 1))
        input_axis_order = "trials_samples_channels"
    else:
        raise ValueError(
            f"Expected one NPY axis to contain {PROFILE.channel_count} channels, "
            f"got {batch.shape}."
        )
    if not np.all(np.isfinite(oriented)):
        raise ValueError(f"NPY trial batch contains NaN or infinite values: {source}")

    excluded = tuple(sorted(set(int(index) for index in exclude_trials)))
    if any(index < 1 or index > oriented.shape[0] for index in excluded):
        raise ValueError(
            f"Excluded trials must be within 1-{oriented.shape[0]}."
        )
    retained_numbers = tuple(
        index
        for index in range(1, oriented.shape[0] + 1)
        if index not in excluded
    )
    retained = oriented[np.asarray(retained_numbers, dtype=int) - 1]
    return TrialBatch(
        data=retained,
        source=source,
        trial_numbers=retained_numbers,
        metadata={
            "input_axis_order": input_axis_order,
            "original_dtype": original_dtype,
            "original_trial_count": int(oriented.shape[0]),
            "excluded_trial_numbers": list(excluded),
            "retained_trial_count": len(retained_numbers),
        },
    )


def read_neuradock_input(
    path: PathLike,
    exclude_trials: Sequence[int] = (),
) -> Union[Recording, TrialBatch]:
    source = Path(path).expanduser()
    if source.suffix.casefold() == ".npy":
        return read_neuradock_npy(source, exclude_trials=exclude_trials)
    if exclude_trials:
        raise ValueError("--exclude-trials can only be used with NPY trial batches.")
    return read_neuradock_txt(source)


def _as_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_neuradock_txt(path: PathLike) -> Recording:
    """Parse a NeuraDock USB or Bluetooth text export.

    The parser requires the public packet shape and never guesses channel order.
    Malformed rows are skipped and reported in ``recording.metadata``.
    """

    source = Path(path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"NeuraDock recording not found: {source}")

    samples: List[List[float]] = []
    timestamps: List[float] = []
    markers: List[str] = []
    total_lines = 0
    malformed_lines = 0
    usb_lines = 0
    bluetooth_lines = 0

    with source.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            total_lines += 1
            line = raw_line.strip()
            if not line:
                continue
            fields = [part.strip() for part in line.split(",")]
            groups = 0
            if len(fields) >= 2 + 5 * PROFILE.packet_total_channels:
                groups = PROFILE.bluetooth_samples_per_packet
                bluetooth_lines += 1
            elif len(fields) >= 2 + PROFILE.packet_total_channels:
                groups = 1
                usb_lines += 1
            else:
                malformed_lines += 1
                continue

            base_timestamp = _as_float(fields[0])
            marker = fields[1]
            line_samples: List[List[float]] = []
            valid_line = True
            for group_index in range(groups):
                start = 2 + group_index * PROFILE.packet_total_channels
                stop = start + PROFILE.packet_used_channels
                values = [_as_float(value) for value in fields[start:stop]]
                if len(values) != PROFILE.channel_count or any(value is None for value in values):
                    valid_line = False
                    break
                line_samples.append([float(value) for value in values if value is not None])

            if not valid_line:
                malformed_lines += 1
                continue

            for group_index, sample in enumerate(line_samples):
                samples.append(sample)
                markers.append(marker)
                if base_timestamp is None:
                    timestamps.append(np.nan)
                else:
                    timestamps.append(base_timestamp + group_index / PROFILE.sampling_rate_hz)

    if not samples:
        raise ValueError(f"No valid NeuraDock EEG samples found in {source}.")

    transport = "bluetooth" if bluetooth_lines >= usb_lines else "usb"
    if bluetooth_lines and usb_lines:
        transport = "mixed"

    timestamp_array = np.asarray(timestamps, dtype=float)
    if np.all(np.isnan(timestamp_array)):
        timestamp_array = None

    return Recording(
        data=np.asarray(samples, dtype=float).T,
        source=source,
        transport=transport,
        timestamps=timestamp_array,
        markers=np.asarray(markers, dtype=object),
        metadata={
            "total_lines": total_lines,
            "malformed_lines": malformed_lines,
            "valid_usb_lines": usb_lines,
            "valid_bluetooth_lines": bluetooth_lines,
            "malformed_line_ratio": malformed_lines / max(total_lines, 1),
        },
    )


def write_neuradock_bluetooth_txt(
    path: PathLike,
    data: np.ndarray,
    marker: str = "0",
    start_timestamp: float = 0.0,
) -> Path:
    """Write a matrix as the public Bluetooth text shape.

    This helper is used by the transparent synthetic demo and parser tests.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    matrix = np.asarray(data, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != PROFILE.channel_count:
        raise ValueError(
            f"Expected ({PROFILE.channel_count}, samples), got {matrix.shape}."
        )

    group_size = PROFILE.bluetooth_samples_per_packet
    usable = matrix.shape[1] - (matrix.shape[1] % group_size)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for start in range(0, usable, group_size):
            timestamp = start_timestamp + start / PROFILE.sampling_rate_hz
            fields = [f"{timestamp:.6f}", str(marker)]
            for offset in range(group_size):
                sample = matrix[:, start + offset]
                fields.extend(f"{float(value):.8f}" for value in sample)
                fields.append("0")
            handle.write(",".join(fields) + "\n")
    return target


def packet_fields_to_samples(fields: List[str]) -> Tuple[np.ndarray, str, Optional[float]]:
    """Parse one realtime CSV packet into ``samples x 7 channels``."""

    expected = 2 + PROFILE.bluetooth_samples_per_packet * PROFILE.packet_total_channels
    if len(fields) < expected:
        raise ValueError(f"Incomplete NeuraDock packet: expected {expected} fields.")
    timestamp = _as_float(fields[0])
    marker = fields[1].strip()
    values = np.asarray(
        fields[2 : 2 + PROFILE.bluetooth_samples_per_packet * PROFILE.packet_total_channels],
        dtype=float,
    )
    packet = values.reshape(
        PROFILE.bluetooth_samples_per_packet, PROFILE.packet_total_channels
    )
    return packet[:, : PROFILE.packet_used_channels], marker, timestamp
