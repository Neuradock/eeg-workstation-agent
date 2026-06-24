"""Download the public NeuraDock examples used by the command guide."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path


BRANCH = "add-visual-cognitive-load-mini-dataset-20260622"
RAW_ROOT = (
    "https://raw.githubusercontent.com/Neuradock/eeg-workstation-data/"
    f"{BRANCH}/"
)
FILES = {
    "alpha/open_closed_eye2.txt": (
        "open_closed_eye2.txt",
        "0e35ae1375b40f65cbb589eb0780d475bf2e098ce9d51"
        "d9db350b5b9b176a279",
    ),
    "rest_task/rest_S01_1.txt": (
        "visual_cognitive_load/mini_dataset_v20260622/"
        "cohort_3subj_rest_task/S01/rest_S01_1.txt",
        "4bd1e976580edb94908d798279f320eecfd2744171e423"
        "20241d2ebc1c851665",
    ),
    "rest_task/task_S01_1.txt": (
        "visual_cognitive_load/mini_dataset_v20260622/"
        "cohort_3subj_rest_task/S01/task_S01_1.txt",
        "5a2fb2de723a6f477170bacf7c38c5b810a0eead76f4e7"
        "b692c4db2c0a936f7a",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_examples(output_dir: Path, force: bool = False) -> None:
    for relative_path, (source_path, expected_hash) in FILES.items():
        destination = output_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists() and not force:
            if _sha256(destination) == expected_hash:
                print(f"Verified: {destination}")
                continue
            raise ValueError(
                f"Existing file has an unexpected SHA256: {destination}. "
                "Use --force to replace it."
            )

        temporary = destination.with_suffix(destination.suffix + ".part")
        request = urllib.request.Request(
            RAW_ROOT + source_path,
            headers={"User-Agent": "NeuraDock-Agent-Data-Downloader/2026.6.24"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                temporary.write_bytes(response.read())
            actual_hash = _sha256(temporary)
            if actual_hash != expected_hash:
                raise ValueError(
                    f"SHA256 mismatch for {source_path}: {actual_hash}"
                )
            temporary.replace(destination)
            print(f"Downloaded: {destination}")
        finally:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify public NeuraDock EEG examples."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data_examples"),
        help="Destination directory (default: data_examples).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing files after downloading verified copies.",
    )
    args = parser.parse_args()
    download_examples(args.output_dir, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
