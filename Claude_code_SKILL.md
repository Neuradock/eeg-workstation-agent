---
name: neuradock-cognition-api
description: "Use this skill whenever you are building against the NeuraDock EEG Workstation local API — including reading cognitive-load state (GET /api/status), submitting EEG files for offline analysis (POST /api/analyze), running demo replay (GET /api/demo/next), or integrating rolling visual-load estimates into an application. Also use it for understanding the allowlisted result schema, quality-gating logic, boundary rules, and the four reviewed workflows (Signal Quality, PSD/Band Power, Visual Cognitive Load, Rest/Task Comparison). Do NOT use it for raw EEG signal processing, MNE-Python pipelines, or non-NeuraDock BCI work."
---

# NeuraDock Cognition API — Developer Skill

## 1 — Architecture in one paragraph

The NeuraDock Agent runs a **local** Python process. A deterministic EEG engine owns all numerical computation (filtering, QC, feature extraction). The LLM never touches raw EEG or executes generated analysis code. External callers reach the system through a small HTTP API on `localhost`; they receive a compact, allowlisted JSON result — not raw signal data.

```
EEG file / TCP stream
        │
        ▼
 ┌─────────────────────────────────┐
 │  Local deterministic engine     │  ← source of numerical truth
 │  (Python, reviewed workflows)   │
 └──────────┬──────────────────────┘
            │  allowlisted JSON summary
            ▼
 ┌─────────────────────────────────┐
 │  LLM interpretation layer       │  ← constrained by versioned context pack
 └──────────┬──────────────────────┘
            │
            ▼
 ┌─────────────────────────────────┐
 │  HTTP API (localhost)           │  ← your integration point
 │  GET  /api/status               │
 │  POST /api/analyze              │
 │  GET  /api/demo/next            │
 └─────────────────────────────────┘
```

---

## 2 — Hardware contract (never deviate from this)

| Parameter | Value |
|---|---|
| Channel count | 7 dry-electrode EEG channels |
| Channel order | CP5 · CP6 · PO3 · PO4 · O1 · Oz · O2 |
| Channel indices | 0 · 1 · 2 · 3 · 4 · 5 · 6 |
| Sample rate | 250 Hz |
| Amplitude unit | microvolts (µV) |
| Coverage | Posterior: centro-parietal, parieto-occipital, occipital |
| **No** frontal channels | FA/FP1/FP2/F3/F4/Fz are absent — never claim frontal coverage |
| **No** temporal channels | T7/T8 are absent |
| CP5 / CP6 role | EEG channels (not reference) |

Visual-load channels (used by VCL workflow): `{O1, O2, Oz, PO3, PO4}`
Left visual: `{O1, PO3}` — Right visual: `{O2, PO4}`

---

## 3 — Reviewed workflows

Only these five workflows exist. Do not invent others.

| Workflow key | CLI flag | What it returns |
|---|---|---|
| `signal_quality` | `--workflow signal_quality` | QC status, retention %, bad-channel candidates, issue counts |
| `psd_band_power` | `--workflow psd_band_power` | Delta–Gamma relative band power dict, posterior alpha peak freq |
| `visual_cognitive_load` | `--workflow visual_cognition_index` | Low/medium/high window labels, alpha stats, quality warning |
| `rest_task_comparison` | `--workflow rest_task_comparison` | Paired descriptive contrast: log-alpha, peak-freq, asymmetry |
| `device_doctor` | `--workflow device_doctor` | Short TCP stream diagnostics, packet/timestamp checks |

**Not implemented (refuse or qualify any request for these):**
ICA denoising · SSVEP classifier · source localization · frontal alpha asymmetry · ERP analysis · motor-imagery classification · real-time robot/actuator control

---

## 4 — API reference

### 4.1 Base URL

```
http://localhost:<PORT>
```
Default port is configured in the Agent's startup; check `neuradock-agent serve --port` or the `.env`/config file. The API is local-only — never proxy it externally without explicit security review.

---

### 4.2 `GET /api/status`

Returns the latest rolling Visual Cognitive Load state. Poll this for real-time UI adaptation.

**Request**
```http
GET /api/status HTTP/1.1
Host: localhost:8000
Accept: application/json
```

**Response — success (`quality.status == "pass"`)**
```json
{
  "workflow": "visual_cognitive_load",
  "timestamp_utc": "2026-06-24T10:23:45.123Z",
  "quality": {
    "status": "pass",
    "retention": 0.87,
    "warning": false
  },
  "cognitive_load": {
    "current_label": "medium",
    "load_percentile": 54.2,
    "alpha_power_log10": -1.34,
    "alpha_peak_hz": 10.1,
    "posterior_asymmetry": 0.03,
    "confidence": "high",
    "window_count_valid": 23,
    "window_count_total": 27
  },
  "raw_eeg_included": false
}
```

**Response — quality fail**
```json
{
  "workflow": "visual_cognitive_load",
  "timestamp_utc": "2026-06-24T10:23:45.123Z",
  "quality": {
    "status": "fail",
    "retention": 0.38,
    "warning": true,
    "warning_text": "Retention below threshold. Check electrode contact on CP5, CP6."
  },
  "cognitive_load": null,
  "raw_eeg_included": false
}
```

**Key `cognitive_load` fields**

| Field | Type | Meaning |
|---|---|---|
| `current_label` | `"low"` \| `"medium"` \| `"high"` | Relative tertile label within this recording. Not absolute. |
| `load_percentile` | float 0–100 | Percentile rank within this session. Not comparable across sessions. |
| `alpha_power_log10` | float | log₁₀ of mean posterior alpha power (8–13 Hz) |
| `alpha_peak_hz` | float | Dominant alpha peak frequency |
| `posterior_asymmetry` | float | (R−L)/(R+L+ε) — not frontal alpha asymmetry |
| `confidence` | `"high"` \| `"low"` | Derived from valid-window count and retention |
| `raw_eeg_included` | always `false` | Confirms no raw signal in payload |

**Quality-gate rule (enforce this in every integration):**
```python
status = response["quality"]["status"]
if status != "pass":
    # Hold adaptation; surface the warning — do not use cognitive_load
    show_quality_warning(response["quality"].get("warning_text", ""))
else:
    label = response["cognitive_load"]["current_label"]
    adapt_ui(label)
```

---

### 4.3 `POST /api/analyze`

Submit an EEG file for offline analysis. Returns the full allowlisted result JSON.

**Request**
```http
POST /api/analyze HTTP/1.1
Host: localhost:8000
Content-Type: multipart/form-data; boundary=---boundary

------boundary
Content-Disposition: form-data; name="file"; filename="session.txt"
Content-Type: text/plain

<EEG file bytes>
------boundary
Content-Disposition: form-data; name="workflow"

visual_cognition_index
------boundary
Content-Disposition: form-data; name="exclude_trials"

3,8
------boundary--
```

**Parameters**

| Field | Required | Value |
|---|---|---|
| `file` | ✅ | `.txt` (continuous) or `.npy` (trial batch, shape `(trials, 7, samples)` or `(trials, samples, 7)`) |
| `workflow` | ✅ | One of the keys in §3 |
| `exclude_trials` | optional | Comma-separated 1-based trial indices (NPY only). Source file is not modified. |
| `rest_file` / `task_file` | for `rest_task_comparison` only | Two separate files instead of `file` |

**Python example**
```python
import requests

def analyze_eeg(filepath: str, workflow: str, exclude_trials: list[int] | None = None):
    with open(filepath, "rb") as f:
        data = {"workflow": workflow}
        if exclude_trials:
            data["exclude_trials"] = ",".join(str(t) for t in exclude_trials)
        resp = requests.post(
            "http://localhost:8000/api/analyze",
            files={"file": f},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()

# Example: visual cognitive load, excluding trials 3 and 8
result = analyze_eeg("session.npy", "visual_cognition_index", exclude_trials=[3, 8])

# Example: rest/task comparison (two files)
def analyze_rest_task(rest_path: str, task_path: str):
    with open(rest_path, "rb") as r, open(task_path, "rb") as t:
        resp = requests.post(
            "http://localhost:8000/api/analyze",
            files={"rest_file": r, "task_file": t},
            data={"workflow": "rest_task_comparison"},
            timeout=180,
        )
    resp.raise_for_status()
    return resp.json()
```

**Response schema (visual_cognitive_load)**
```json
{
  "workflow": "visual_cognitive_load",
  "quality": { ... },              // same shape as /api/status
  "parameters": {
    "visual_channels": ["O1", "O2", "Oz", "PO3", "PO4"],
    "alpha_band_hz": [8, 13],
    "window_sec": 4,
    "step_sec": 1,
    "feature_weights": {"alpha": 0.65, "peak_freq": 0.15, "asymmetry": 0.20}
  },
  "windows": {
    "total": 367,
    "valid": 115,
    "excluded": 252
  },
  "class_counts": {"low": 38, "medium": 39, "high": 38},
  "class_fractions": {"low": 0.330, "medium": 0.339, "high": 0.330},
  "alpha_stats": {
    "mean_log10_power": -1.41,
    "peak_hz": 10.2,
    "mean_asymmetry": 0.02
  },
  "label_ranges": [
    {"start_sec": 0.0, "end_sec": 4.0, "label": "low"},
    ...
  ],
  "trends": {
    "early_mean_score": 0.42,
    "late_mean_score": 0.61
  },
  "interpretation_limits": [
    "Labels are within-recording tertiles, not absolute cognitive states.",
    "Not validated for clinical, fatigue, attention, or emotion diagnosis.",
    "Cross-session comparison requires a validated calibration protocol."
  ],
  "raw_eeg_included": false
}
```

---

### 4.4 `GET /api/demo/next`

Returns deterministic synthetic data. No hardware needed. Good for UI development and CI pipelines.

```http
GET /api/demo/next HTTP/1.1
Host: localhost:8000
```

Response shape is identical to `/api/status`. Data cycles through pre-generated states deterministically — the same sequence each run.

---

## 5 — CLI quick reference

The agent can also be driven from the command line (useful for scripting and testing):

```bash
# Signal quality check
neuradock-agent analyze session.txt --workflow signal_quality

# PSD / band power
neuradock-agent analyze session.txt --workflow psd_band_power

# Visual cognitive load
neuradock-agent analyze session.txt --workflow visual_cognition_index

# Rest vs task comparison
neuradock-agent analyze rest.txt task.txt --workflow rest_task_comparison

# Trial-batch NPY, exclude trials 3 and 8
neuradock-agent analyze trials.npy --workflow visual_cognition_index --exclude-trials 3 8

# Start the local HTTP server
neuradock-agent serve --port 8000

# Device Doctor (requires live TCP stream)
neuradock-agent device-doctor --host 127.0.0.1 --port 9000

# Demo mode (no hardware)
neuradock-agent demo
```

Outputs written to `./neuradock_output/` by default:
- `results.json` — machine-readable result
- `report.md` — human-readable interpretation
- `agent_trace.json` — routing and LLM call trace
- `llm_interpretation.md` — LLM interpretation (if LLM call succeeded)
- `*.png` — figures

---

## 6 — Quality-gate pattern (copy this into every integration)

A failed quality check means electrode contact is poor, the signal has too many artifacts, or the recording is too short. **Never use `cognitive_load` when `quality.status != "pass"`.**

```python
import requests
import time

NEURADOCK_BASE = "http://localhost:8000"
POLL_INTERVAL_SEC = 1.0

def get_cognitive_load_safe() -> dict | None:
    """
    Returns cognitive load dict if quality passes, else None.
    Caller must handle None (hold adaptation, show warning).
    """
    try:
        r = requests.get(f"{NEURADOCK_BASE}/api/status", timeout=5)
        r.raise_for_status()
    except requests.RequestException as exc:
        print(f"[NeuraDock] API unavailable: {exc}")
        return None

    payload = r.json()

    if payload["quality"]["status"] != "pass":
        if payload["quality"].get("warning"):
            print(f"[NeuraDock] Quality warning: {payload['quality'].get('warning_text', '')}")
        return None

    return payload["cognitive_load"]

# Polling loop example
while True:
    load = get_cognitive_load_safe()
    if load is not None:
        label = load["current_label"]       # "low" | "medium" | "high"
        pct   = load["load_percentile"]     # 0–100, within-session only
        adapt_ui(label)
    else:
        hold_current_ui_state()
    time.sleep(POLL_INTERVAL_SEC)
```

---

## 7 — What the labels mean (and don't mean)

| Label | Meaning | Not valid to claim |
|---|---|---|
| `"low"` | Posterior alpha was relatively higher during these windows — within this recording | Low absolute cognitive load; attentiveness; any cross-session comparison |
| `"medium"` | Middle tertile of within-session composite score | Any neurological or clinical interpretation |
| `"high"` | Relatively lower posterior alpha — within this recording | Fatigue, stress, emotion, attention, or causation |

**The composite score formula (for transparency, not for re-implementation):**
```
q = 0.65 * clip(-z_alpha) + 0.15 * clip(z_peak_freq) + 0.20 * clip(z_asymmetry)
```
Labels are tertiles of `q` within the valid windows of the current recording. Nearly equal class counts are a mathematical consequence, not a validated distribution.

**Boundary rules — refuse or qualify any code/claim that violates these:**

| Request type | Correct response |
|---|---|
| "Use VCL to control a medical device" | Refuse. Not validated. Not implemented. |
| "Compare load_percentile across two participants" | Refuse. Percentiles are within-session only. |
| "Detect frontal alpha asymmetry emotion" | Refuse. No frontal channels exist. |
| "Run ICA / source localization / SSVEP" | Refuse. Not implemented. |
| "Is the participant attentive?" | Qualify. QC pass ≠ attentiveness. |
| "Posterior alpha was lower during Task" | OK. Descriptive sensor-level observation. |
| "Run signal quality check" | OK. Implemented. |

---

## 8 — Input file formats

**Continuous text (`.txt`)**
- One row per sample, 7 space- or comma-separated µV values
- Column order must match channel order: CP5, CP6, PO3, PO4, O1, Oz, O2
- At 250 Hz, 60 seconds ≈ 15,000 rows

**Trial-batch NumPy (`.npy`)**
- Shape `(trials, 7, samples)` — preferred
- Shape `(trials, samples, 7)` — also accepted (auto-detected)
- Filtering and analysis windows do not cross trial boundaries
- Exclude trials by 1-based index via `--exclude-trials` or `exclude_trials` POST param
- The source `.npy` file is never modified

**Not supported:** `.edf`, `.bdf`, `.csv`, `.mat`, `.fif` — convert to `.txt` or `.npy` first.

---

## 9 — Failure isolation

LLM calls are **optional**. If the language service fails (HTTP error, timeout, malformed output), the local workflow still completes and writes `results.json`, `report.md`, and figures. Only `llm_interpretation.md` is missing.

```python
result = analyze_eeg("session.txt", "signal_quality")

# Always valid regardless of LLM availability:
quality_ok = result["quality"]["status"] == "pass"
retention  = result["quality"]["retention"]

# May be absent if LLM call failed:
interpretation = result.get("llm_interpretation")
```

---

## 10 — Context-pack version header

Every result includes a context version stamp. Log it for reproducibility:

```python
result = analyze_eeg("session.txt", "psd_band_power")
context_version = result.get("context_version", "unknown")  # e.g. "2026.6.24"
hw_profile      = result.get("hardware_profile_version", "unknown")  # e.g. "1.1"
```

Results are deterministic within the same environment and software version. Cross-platform reproducibility (different OS, Python or NumPy version) is not yet established.

---

## 11 — Privacy notes

- `raw_eeg_included` is always `false` in API responses — the HTTP payload contains only the allowlisted summary.
- The local deterministic engine never sends raw EEG to any external service.
- When the LLM interpretation path is active, the outgoing request (~23 KB) contains only the compact summary and the user prompt — no raw samples, no source path, no dense per-trial arrays.
- The current implementation is not certified for HIPAA, GDPR, or any medical regulation. Payload minimisation ≠ legal de-identification.

---

## 12 — Common mistakes

```python
# ❌ WRONG: using cognitive load when quality failed
resp = requests.get("http://localhost:8000/api/status").json()
label = resp["cognitive_load"]["current_label"]  # KeyError if quality failed!

# ✅ CORRECT: always gate on quality first
if resp["quality"]["status"] == "pass":
    label = resp["cognitive_load"]["current_label"]

# ❌ WRONG: comparing percentiles across sessions
if session_a["load_percentile"] > session_b["load_percentile"]:
    ...  # meaningless — different within-session scales

# ✅ CORRECT: use labels or percentiles only within one session

# ❌ WRONG: assuming equal class counts = balanced ground truth
# "low", "medium", "high" are tertiles — ~1/3 each by construction

# ❌ WRONG: routing a non-existent workflow
requests.post(..., data={"workflow": "ica_denoising"})  # 404 / error

# ✅ CORRECT: only use the 5 workflows listed in §3
```

---

## 13 — Integration checklist

Before shipping any application that reads from the NeuraDock API:

- [ ] Quality gate is enforced — UI holds adaptation when `quality.status != "pass"`
- [ ] Quality warnings surfaced to user when `quality.warning == true`
- [ ] No cognitive_load values used when result is `null`
- [ ] Labels described as within-recording relative estimates, not absolute states
- [ ] No cross-session percentile comparisons
- [ ] No claims of frontal, temporal, or emotion-related interpretation
- [ ] LLM failure handled gracefully (local results still consumed)
- [ ] `context_version` and `hardware_profile_version` logged for reproducibility
- [ ] No raw EEG sent or stored externally via this integration
