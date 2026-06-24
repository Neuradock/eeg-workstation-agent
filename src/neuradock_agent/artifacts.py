from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple, Union

import numpy as np

from .models import Recording
from .profile import PROFILE, __version__


PathLike = Union[str, Path]


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def write_json(path: Path, payload: Dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    return path


def create_run_dir(output_root: PathLike, workflow: str, run_name: Optional[str] = None) -> Path:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if run_name:
        name = run_name
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        name = f"{stamp}_{workflow}"
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "figures").mkdir()
    return run_dir


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_input_manifest(run_dir: Path, recordings: Iterable[Recording]) -> Path:
    inputs = []
    for recording in recordings:
        inputs.append(
            {
                **recording.summary(),
                "sha256": sha256_file(recording.source),
            }
        )
    return write_json(
        run_dir / "input_manifest.json",
        {
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "agent_version": __version__,
            "hardware_profile": PROFILE.to_dict(),
            "inputs": inputs,
        },
    )


def write_workflow_manifest(
    run_dir: Path, workflow: str, parameters: Dict[str, object]
) -> Path:
    return write_json(
        run_dir / "workflow.json",
        {
            "workflow": workflow,
            "workflow_version": "1.0",
            "agent_version": __version__,
            "parameters": parameters,
            "deterministic_core": True,
            "generated_code_execution": False,
        },
    )


def write_batch_clean_npz(
    path: PathLike,
    entries: Sequence[Tuple[PathLike, PathLike]],
) -> Path:
    """Write variable-length clean EEG arrays into one standard NPZ archive."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        raise ValueError("At least one clean EEG entry is required.")

    source_files = []
    clean_data_paths = []
    data_keys = []
    sample_counts = []
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{target.stem}_",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()

    def write_array(
        archive: zipfile.ZipFile,
        key: str,
        array: np.ndarray,
    ) -> None:
        with archive.open(f"{key}.npy", mode="w", force_zip64=True) as handle:
            np.lib.format.write_array(
                handle,
                np.asarray(array),
                allow_pickle=False,
            )

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for index, (source, clean_path) in enumerate(entries):
                source_path = Path(source).expanduser().resolve()
                clean_data_path = Path(clean_path).expanduser().resolve()
                key = f"clean_data_{index:03d}"
                with np.load(clean_data_path, allow_pickle=False) as payload:
                    data = np.asarray(payload["data"], dtype=float)
                if data.ndim != 2 or data.shape[0] != PROFILE.channel_count:
                    raise ValueError(
                        f"Expected clean EEG shape ({PROFILE.channel_count}, samples), "
                        f"got {data.shape} from {clean_data_path}."
                    )
                write_array(archive, key, data)
                source_files.append(str(source_path))
                clean_data_paths.append(str(clean_data_path))
                data_keys.append(key)
                sample_counts.append(data.shape[1])

            write_array(archive, "format_version", np.asarray("1.0"))
            write_array(archive, "channels", np.asarray(PROFILE.channels, dtype=str))
            write_array(
                archive,
                "sampling_rate_hz",
                np.asarray(PROFILE.sampling_rate_hz, dtype=np.int64),
            )
            write_array(archive, "source_files", np.asarray(source_files, dtype=str))
            write_array(
                archive,
                "clean_data_paths",
                np.asarray(clean_data_paths, dtype=str),
            )
            write_array(archive, "data_keys", np.asarray(data_keys, dtype=str))
            write_array(
                archive,
                "sample_counts",
                np.asarray(sample_counts, dtype=np.int64),
            )
            write_array(
                archive,
                "duration_seconds",
                np.asarray(sample_counts, dtype=float) / PROFILE.sampling_rate_hz,
            )
        temporary_path.replace(target)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


def relative_artifacts(run_dir: Path) -> Dict[str, object]:
    files = sorted(
        str(path.relative_to(run_dir)).replace("\\", "/")
        for path in run_dir.rglob("*")
        if path.is_file()
    )
    return {"run_dir": str(run_dir), "files": files}
