# NeuraDock Visual Cognitive Load Agent Command Guide

Version: `2026.6.24`

This file collects the commands for the clean open-source release. Replace
`neuradock-agent` with your local repository folder if you downloaded the ZIP
instead of cloning from GitHub.

## 1. Get The Project

Git clone:

```powershell
git clone https://github.com/Neuradock/neuradock-agent.git
cd neuradock-agent
```

Downloaded ZIP:

```powershell
cd path\to\neuradock-agent
```

## 2. Create The Python Environment

Python `>=3.9,<3.14` is supported. Python 3.11 or 3.12 is recommended.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If Python 3.12 is not installed:

```powershell
py -3.11 -m venv .venv
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 3. Check Version And Hardware Profile

Windows:

```powershell
.\.venv\Scripts\neuradock-agent.exe --version
.\.venv\Scripts\neuradock-agent.exe profile
```

macOS/Linux:

```bash
neuradock-agent --version
neuradock-agent profile
```

Expected version:

```text
2026.6.24
```

The hardware profile reports the fixed NeuraDock channel order:

```text
0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2
```

## Optional: Download Public EEG Examples

The software runs without human EEG data. Commands below that reference
`data_examples/` require the separately maintained public examples:

```powershell
.\.venv\Scripts\python.exe scripts\download_example_data.py
```

The downloader verifies SHA256 values. Read `DATASET.md` before interpretation.

## 4. EEG Preprocessing And Quality Gate

Run this before interpreting cognitive-load results:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow quality
```

Batch quality processing:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze data_examples\rest_task --workflow quality
```

Recursive batch processing:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze data_examples --workflow quality --recursive
```

Main output:

```text
runs/<timestamp>_quality/
|-- report.md
|-- results.json
|-- clean_eeg_data.npz
`-- figures/
```

All downstream Alpha and workload workflows use preprocessed, quality-gated
signals internally. Raw data is parsed as input, then cleaned before metrics are
computed.

## 5. Alpha Dynamics

This workflow automatically finds strong and weak posterior Alpha windows and
writes time-domain, frequency-domain, and time-frequency figures.

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow alpha dynamics
```

Custom window and step:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow alpha dynamics `
  --window-sec 4 `
  --step-sec 1
```

Main output:

```text
runs/<timestamp>_alpha_dynamics/
|-- report.md
|-- results.json
`-- figures/
    |-- alpha_time_domain.png
    |-- alpha_frequency_domain.png
    `-- alpha_time_frequency.png
```

## 6. Offline Visual Cognitive Load Index

Single-recording relative visual cognitive-load analysis:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow visual cognition index
```

Custom window and step:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow visual cognition index `
  --window-sec 4 `
  --step-sec 1
```

## 7. Offline Rest/Task Comparison

Use Rest first and Task second. The included pair is one subject and one
session:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\rest_task\rest_S01_1.txt `
  data_examples\rest_task\task_S01_1.txt `
  --workflow visual cognition comparison
```

With explicit labels:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\rest_task\rest_S01_1.txt `
  data_examples\rest_task\task_S01_1.txt `
  --workflow visual cognition comparison `
  --condition-labels Rest Task
```

Main output:

```text
runs/<timestamp>_visual_cognitive_load_comparison/
|-- report.md
|-- results.json
`-- figures/
    |-- visual_cognitive_load_comparison.png
    |-- rest_visual_cognitive_load.png
    `-- task_visual_cognitive_load.png
```

## 8. Online Hardware Dashboard

For normal users, this is the simplest live workflow. Enter the NeuraDock
hardware realtime stream IP and port:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600
```

The Agent will:

1. connect to the NeuraDock TCP stream;
2. send the device `start` command;
3. parse the realtime data stream;
4. run online preprocessing and quality control;
5. calculate the rolling visual workload index;
6. open the local HTML dashboard.

Dashboard URL:

```text
http://127.0.0.1:8765
```

Use another local dashboard port if 8765 is occupied:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600 `
  --dashboard-port 8766
```

Start without opening the browser automatically:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600 `
  --no-open
```

## 9. Demo Dashboard Without Hardware

This generates a deterministic synthetic replay and does not require NeuraDock
hardware or downloaded EEG data:

```powershell
.\.venv\Scripts\neuradock-agent.exe serve --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Use a custom demo file:

```powershell
.\.venv\Scripts\neuradock-agent.exe serve `
  --port 8765 `
  --demo-file data_examples\alpha\open_closed_eye2.txt
```

The browser refreshes automatically. The Start button resumes the dashboard
after Pause; users do not need to manually POST data.

## 10. Realtime Workload API For Applications

After starting `online` or `serve`, user applications should read the latest
computed workload from:

```text
GET http://127.0.0.1:8765/api/status
```

PowerShell check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/status
```

Important fields:

```text
status
current.visual_load_index
current.alpha_state
current.alpha_peak_hz
current.alpha_suppression_from_baseline
current.alpha_asymmetry_right_minus_left
quality.status
quality.bad_channel_candidates
channels
stream.connected
stream.samples_received
stream.last_error
```

Python integration:

```python
import time
import requests

URL = "http://127.0.0.1:8765/api/status"

while True:
    data = requests.get(URL, timeout=2).json()
    if data["status"] == "ok" and data["quality"]["status"] == "pass":
        current = data["current"]
        print(
            "workload={:.1f}, alpha={}, peak={:.2f} Hz".format(
                current["visual_load_index"],
                current["alpha_state"],
                current["alpha_peak_hz"],
            )
        )
    else:
        print("Waiting or low quality:", data.get("status"))
    time.sleep(1)
```

JavaScript browser or web-app integration:

```javascript
async function readWorkload() {
  const response = await fetch("http://127.0.0.1:8765/api/status");
  const data = await response.json();

  if (data.status === "ok" && data.quality.status === "pass") {
    console.log({
      workload: data.current.visual_load_index,
      alphaState: data.current.alpha_state,
      alphaPeak: data.current.alpha_peak_hz,
    });
  } else {
    console.log("Waiting or low quality", data.status);
  }
}

setInterval(readWorkload, 1000);
```

Recommended integration pattern:

```text
NeuraDock hardware
  -> neuradock-agent online
  -> GET /api/status
  -> user application
```

Use `quality.status == "pass"` as the gate for adaptive UI, XR, HMI, or other
application actions.

## 11. Developer API Endpoints

```text
GET  /api/health
GET  /api/status
GET  /api/next
GET  /api/demo/next
GET  /api/demo/reset
POST /api/analyze
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health
```

Advance the built-in demo stream:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/demo/next
```

Reset the built-in demo stream:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/demo/reset
```

Post custom online samples:

```powershell
$body = @{
  samples = @(
    @(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7),
    @(0.2, 0.1, 0.4, 0.3, 0.6, 0.5, 0.8)
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri http://127.0.0.1:8765/api/analyze `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

The API accepts either `samples x 7` or `7 x samples` numeric arrays.

## 12. Visual Search Application Demo

This example shows how a browser application can consume the NeuraDock
quality-gated visual workload API and adapt a visual search task.

Start the NeuraDock API in no-hardware replay mode:

```powershell
.\.venv\Scripts\neuradock-agent.exe serve --port 8765
```

In another terminal, serve the demo application:

```powershell
cd examples\visual_search_demo
py -3 -m http.server 8080
```

Open:

```text
http://127.0.0.1:8080
```

For live hardware, replace the first command with:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600
```

The demo reads `/api/status` and `/api/next`, then adjusts visual search
density only after checking the quality gate.

## 13. Adaptive Vehicle HMI Demo

This example shows a vehicle HMI that adapts application layout from the
workload API instead of showing EEG traces.

Self-contained simulated status API:

```powershell
cd examples\adaptive_ui_demo
py -3 server.py --port 8081
```

Open:

```text
http://127.0.0.1:8081
```

For live hardware, first start the NeuraDock online API:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600
```

Then proxy the live API through the demo server:

```powershell
cd examples\adaptive_ui_demo
py -3 server.py --port 8081 --api-base http://127.0.0.1:8765
```

The UI polls `GET /api/status` every second. If `quality.status` is not `pass`,
it holds the standard vehicle HMI and shows `Signal quality warning`. If quality
passes and `current.visual_load_index` is above 70, it simplifies navigation,
ADAS, route, and driver controls, hides non-essential panels, and shows
`High visual load, simplified view enabled`. If quality passes and load is low,
the HMI expands with richer route, ADAS, energy, and context symbols.

## 14. Cognitive Load Game Demo

This example shows a lightweight browser game driven by the realtime workload
API. It demonstrates an application loop where game difficulty reacts to the
quality-gated load signal.

Self-contained simulated status API:

```powershell
cd examples\cognitive_load_game_demo
py -3 server.py --port 8082
```

Open:

```text
http://127.0.0.1:8082
```

For live hardware, first start the NeuraDock online API:

```powershell
.\.venv\Scripts\neuradock-agent.exe online `
  --ip 192.168.4.1 `
  --port 9600
```

Then proxy the live API through the game server:

```powershell
cd examples\cognitive_load_game_demo
py -3 server.py --port 8082 --api-base http://127.0.0.1:8765
```

The game polls `GET /api/status` every second. Low load increases target count
and speed, moderate load holds the balanced difficulty, high load reduces speed
and distractors, and quality warnings pause adaptation while still displaying
the incoming signal data.

## 15. Natural-Language Local Routing

Without LLM:

```powershell
.\.venv\Scripts\neuradock-agent.exe ask `
  "find strong and weak alpha waves" `
  --file data_examples\alpha\open_closed_eye2.txt
```

Signal quality:

```powershell
.\.venv\Scripts\neuradock-agent.exe ask `
  "check EEG signal quality" `
  --file data_examples\alpha\open_closed_eye2.txt
```

Rest/Task comparison:

```powershell
.\.venv\Scripts\neuradock-agent.exe ask `
  "compare rest and task visual cognitive load" `
  --file data_examples\rest_task\rest_S01_1.txt `
  --file2 data_examples\rest_task\task_S01_1.txt
```

## 16. LLM Mode

No API key is shipped with this repository. Each user must enter their own LLM
provider settings the first time LLM mode is used.

Interactive LLM mode:

```powershell
.\.venv\Scripts\neuradock-agent.exe
```

Then enter:

```text
/mode LLM
```

The Agent will prompt for:

```text
Base URL
Model name
API key
```

The config is saved outside the repo:

```text
Windows:     %APPDATA%\NeuraDock Agent\llm_config.json
macOS/Linux: ~/.config/neuradock-agent/llm_config.json
```

To reset credentials, delete that local file and run LLM mode again.

One-shot Alpha dynamics explanation:

```powershell
.\.venv\Scripts\neuradock-agent.exe ask `
  "Analyze Alpha dynamics and explain cognitive-load risk limits" `
  --file data_examples\alpha\open_closed_eye2.txt `
  --llm
```

One-shot Rest/Task explanation:

```powershell
.\.venv\Scripts\neuradock-agent.exe ask `
  "Compare Rest and Task visual cognitive load and explain quality risks" `
  --file data_examples\rest_task\rest_S01_1.txt `
  --file2 data_examples\rest_task\task_S01_1.txt `
  --llm
```

LLM mode sends only allowlisted summaries, warnings, and limits. Raw EEG,
per-sample arrays, full PSD arrays, and full Alpha time series are not sent to
the model.

## 17. Device Doctor

Use this for live NeuraDock TCP stream diagnostics:

```powershell
.\.venv\Scripts\neuradock-agent.exe doctor `
  --ip 192.168.4.1 `
  --port 9600 `
  --windows 3
```

## 18. Advanced PSD Support Workflow

PSD remains available as a supporting engineering workflow:

```powershell
.\.venv\Scripts\neuradock-agent.exe analyze `
  data_examples\alpha\open_closed_eye2.txt `
  --workflow psd
```

## 19. Python API

```python
from neuradock_agent.io import read_neuradock_txt
from neuradock_agent.workflows import run_alpha_dynamics

recording = read_neuradock_txt("data_examples/alpha/open_closed_eye2.txt")
run = run_alpha_dynamics(recording, output_root="runs/python_api_alpha")

print(run.report_path)
print(run.results_path)
for figure in run.figure_paths:
    print(figure)
```

## 20. Development Checks

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run a focused test subset:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_workflows.py tests\test_online.py
```

Run lint:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
```

## 21. Clean Generated Outputs

Generated outputs are written under `runs/`.

```powershell
Remove-Item -Recurse -Force runs
```

## 22. Scientific Boundary

All cognitive-load outputs are relative engineering and research-development
signals. They are not medical, clinical, attention, fatigue, or performance
diagnoses.
