# NeuraDock Agent 2026.6.24

This is the developer-focused open-source release of NeuraDock Visual
Cognitive Load Agent.

## Included

- Installable Python package under `src/neuradock_agent/`
- Realtime NeuraDock TCP acquisition and local workload API
- Signal-quality gate and posterior Alpha workflows
- Online dashboard
- Visual search, adaptive vehicle HMI, and cognitive load game demos
- Deterministic no-hardware replay
- Optional privacy-bounded LLM interpretation
- Tests, CI, architecture, protocol, security, and contribution documentation
- Verified downloader for the separately maintained public EEG examples

## Important Behavior

- `neuradock-agent serve` now generates a synthetic replay when no
  `--demo-file` is supplied.
- Application adaptation must be disabled when `quality.status != "pass"`.
- Workload values are relative signals, not diagnoses or calibrated
  cross-person measurements.
- Human EEG files are not distributed in this software release.

## Public Dataset

The full tutorial dataset is maintained in:

https://github.com/Neuradock/eeg-workstation-data/tree/add-visual-cognitive-load-mini-dataset-20260622/visual_cognitive_load/mini_dataset_v20260622

Read `DATASET.md` before using the recordings.

## Quick Verification

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\neuradock-agent.exe --version
.\.venv\Scripts\neuradock-agent.exe demo --duration 12
```

Expected version:

```text
2026.6.24
```

Suggested GitHub tag: `v2026.6.24`
