# NeuraDock Visual Cognitive Load Agent

Version: `2026.6.24`

For data safty, we don't provide data here
### Please download example data from https://github.com/Neuradock/eeg-workstation-data

NeuraDock Agent is a local-first Python toolkit for turning NeuraDock
7-channel EEG streams into quality-gated visual cognitive-load signals that
applications can consume in real time.

The project is built for developers working on adaptive interfaces, XR,
vehicle HMI, rehabilitation training, industrial monitoring, experiments, and
interactive demos. It exposes application-facing state through a local API;
applications do not need to display raw EEG.

## Highlights

- Deterministic EEG parsing, preprocessing, and signal-quality gating.
- Posterior Alpha dynamics, suppression, peak frequency, and asymmetry.
- Within-subject Rest/Task visual cognitive-load comparison.
- Realtime TCP acquisition, local dashboard, and `GET /api/status`.
- Three browser demos: visual search, adaptive vehicle HMI, and a cognitive
  load game.
- A no-hardware synthetic replay for immediate testing.
- Optional privacy-bounded LLM workflow selection and result explanation.
- Automated tests on Windows, macOS, and Linux.

## Scientific Boundary

This is research and engineering software. It is not a medical device and does
not diagnose cognitive load, attention, fatigue, impairment, or performance.

Always check `quality.status` before adapting an application. Workload values
are relative to a rolling or within-subject baseline. Do not compare people
without a separately validated cross-subject calibration protocol.

## Hardware Profile

```text
Sampling rate: 250 Hz
Channels:      0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2
Unit:          microvolts (uV)
Visual ring:   PO3, PO4, O1, Oz, O2
```

## Install

Python `>=3.9,<3.14` is supported. Python 3.11 or 3.12 is recommended.

Windows PowerShell:

```powershell
git clone https://github.com/Neuradock/eeg-workstation-agent.git
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\neuradock-agent.exe --version
```

macOS/Linux:

```bash
git clone https://github.com/Neuradock/eeg-workstation-agent.git
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
neuradock-agent --version
```

## Quick Start Without Hardware

Generate and analyze a deterministic synthetic recording:

```powershell
.\.venv\Scripts\neuradock-agent.exe demo --duration 24
```

Start the realtime API and dashboard with synthetic replay:

```powershell
.\.venv\Scripts\neuradock-agent.exe serve --port 8765
```

Open `http://127.0.0.1:8765`.

## Realtime API

Applications poll:

```text
GET http://127.0.0.1:8765/api/status
```

Important fields:

```text
current.visual_load_index
current.alpha_state
current.alpha_peak_hz
current.alpha_suppression_from_baseline
current.alpha_asymmetry_right_minus_left
quality.status
quality.bad_channel_candidates
stream.connected
stream.samples_received
```

A minimal adaptation rule:

```javascript
const status = await fetch("http://127.0.0.1:8765/api/status")
  .then((response) => response.json());

if (status.quality?.status !== "pass") {
  showSignalQualityWarning();
} else if (status.current?.visual_load_index > 70) {
  enableSimplifiedView();
} else {
  enableStandardView();
}
```

## Live NeuraDock Hardware

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600
```

The Agent sends the device start command, parses the TCP stream, performs
online preprocessing and quality control, calculates the relative workload
index, and serves the local API.

## Application Demos

All demos gate adaptation on `quality.status`.

Visual search:

```powershell
cd examples\visual_search_demo
py -3 -m http.server 8080
```

Open `http://127.0.0.1:8080`.

Adaptive vehicle HMI:

```powershell
cd examples\adaptive_ui_demo
py -3 server.py --port 8081 --api-base http://127.0.0.1:8765
```

Open `http://127.0.0.1:8081`.

Cognitive load game:

```powershell
cd examples\cognitive_load_game_demo
py -3 server.py --port 8082 --api-base http://127.0.0.1:8765
```

Open `http://127.0.0.1:8082`.

## Public EEG Dataset

Human EEG recordings are maintained separately:

[NeuraDock Visual Cognitive Load Mini Dataset v20260622](https://github.com/Neuradock/eeg-workstation-data/tree/add-visual-cognitive-load-mini-dataset-20260622/visual_cognitive_load/mini_dataset_v20260622)

Download the small examples used by the command guide:

```powershell
.\.venv\Scripts\python.exe scripts\download_example_data.py
```

The downloader verifies SHA256 before placing files under `data_examples/`.
See `DATASET.md` before interpreting or redistributing recordings.

## Offline Examples

After downloading the example data:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow alpha dynamics

.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\rest_task\rest_S01_1.txt `
  data_examples\rest_task\task_S01_1.txt `
  --workflow visual cognition comparison `
  --condition-labels Rest Task
```

## Optional LLM Mode

Raw EEG and dense time-series arrays are not sent to the model. The optional
LLM receives compact metrics and reviewed context for workflow selection and
explanation.

No credential is included in this repository. Configuration is stored outside
the project folder:

- Windows: `%APPDATA%\NeuraDock Agent\llm_config.json`
- macOS/Linux: `~/.config/neuradock-agent/llm_config.json`

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
```

See `COMMANDS.md`, `docs/architecture.md`, `docs/data-protocol.md`, and
`CONTRIBUTING.md` for more detail.

## License

The software is released under the MIT License. EEG recordings are a separate
data asset; follow the upstream data repository terms and the scientific usage
rules in `DATASET.md`.
