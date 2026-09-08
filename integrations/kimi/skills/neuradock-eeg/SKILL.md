---
name: neuradock-eeg
description: NeuraDock EEG Workstation (7-channel dry-electrode, 250 Hz) R&D skill. Use when the user works with NeuraDock/Neuradock EEG data or code — parsing recorded TXT files or real-time TCP streams (USB/Bluetooth), signal-quality QC, PSD/band-power/Alpha-dynamics analysis, visual cognitive-load estimation, Rest/Task comparison, P300/ERP, SSVEP/cVEP experiments, building BCI applications or demos on the NeuraDock SDK/agent, or reviewing NeuraDock signal-processing code. 适用于 NeuraDock 脑电数据分析、认知负荷算法、信号质量检查、脑机接口应用开发。
---

# NeuraDock EEG

Analyze NeuraDock EEG recordings and build NeuraDock BCI applications that
respect the canonical device profile, gate on signal quality before any
interpretation, and stay inside scientific boundaries.

## Canonical invariants (never violate)

- Device: NeuraDock EEG Workstation, 7 channels, 250 Hz, microvolts (uV),
  arrays oriented `channels x samples`.
- Zero-based channel order: `0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2`.
  Never infer channel order from filenames or legacy code; never relabel with
  legacy T5/T6. Posterior set: `PO3, PO4, O1, Oz, O2`.
- Line frequency: 50 Hz (notch in preprocessing).
- If a public example conflicts with this profile, keep the profile and flag
  the example as legacy. Details: `references/device-profile.md`.

## Load references by task

- Parsing TXT/TCP data, units, markers, timestamps: `references/data-format.md`
- QC thresholds, preprocessing, Alpha dynamics, cognitive-load index, PSD,
  Rest/Task comparison, result fields: `references/analysis.md`
- P300, SSVEP, cVEP, online API, demos, application architecture:
  `references/applications.md`
- Any interpretation, report, or claim: `references/scientific-boundaries.md`
  (mandatory before concluding anything about a person or state)

## Quick analysis with the bundled script

`scripts/neuradock_toolkit.py` parses NeuraDock TXT recordings (auto-detects
USB/Bluetooth, expands Bluetooth 5-sample packets, skips `HEADER_DEF` lines,
handles clock or numeric timestamps) and runs the standard pipeline. Tested
against the public sample datasets.

```bash
python scripts/neuradock_toolkit.py parse <file.txt>            # format/integrity summary
python scripts/neuradock_toolkit.py qc    <file.txt>            # 1-s segment QC report
python scripts/neuradock_toolkit.py bands <file.txt>            # abs/rel band power + Alpha peak
python scripts/neuradock_toolkit.py alpha <file.txt> --json out.json  # rolling Alpha dynamics
```

Use it as a library (`load_txt`, `preprocess`, `qc_report`, `band_power_table`,
`alpha_dynamics`, `load_npy_trials`) or as a starting point to modify. It never
modifies source recordings.

Resolve script/reference paths relative to this skill's directory, not the
user's working directory. Install `requirements.txt` with the selected project
Python environment before running scripts. The CLI checks quality on unfiltered
samples before computing filtered features. `bands` pauses on rejected segments;
`alpha` gates aligned windows. Malformed TXT rows block feature analysis to avoid
compressing gaps. Multi-trial NPY input requires explicit `--trial` selection.

## Analysis workflow

1. Confirm input format, shape, sample rate, units, channels, markers, and
   experimental conditions before touching the data.
2. Parse and check integrity (malformed rows, duration, sample count).
3. Check QC on unfiltered input so line noise and amplitude failures remain
   visible. Report retention, rejected segments, bad-channel candidates and thresholds.
4. Preprocess for offline features: median-center, 1-45 Hz bandpass, 50 Hz notch.
   Gate every downstream feature using the corresponding unfiltered QC input.
5. Extract features (band power, posterior Alpha dynamics, cognitive-load
   index, ERP) only from quality-valid data; preserve trial/condition
   boundaries; never filter across unrelated trials.
6. For classifiers: train-only calibration, leakage-safe validation, honest
   held-out metrics.
7. Deliver machine-readable results (JSON/CSV) plus plots/report. Record
   settings, channel order, sample rate, QC result, and software/seed info.
8. Phrase findings per `references/scientific-boundaries.md`: sensor-level,
   within-recording/session, relative — never absolute or clinical.

## Application-development workflow

1. Classify the mode and state it: `code_only`, `simulation`, `replay`, or
   `live_device`. Never silently substitute simulation for live validation.
2. Build one shared pipeline for all modes:
   `source -> packet parser -> 7ch samples -> QC -> marker alignment ->
   feature/model -> application state`.
3. TCP readers must buffer partial/multiple lines per `recv`; default
   `127.0.0.1:9600` is a config default, not endpoint discovery — get host/port
   from the user. Never scan networks.
4. Signal-quality gating before any training, classification, feedback, or
   interpretation. Causal (non-zero-phase) filtering for live feedback.
5. Claim `live_device verified` only with measured evidence (endpoint,
   duration, samples, transport, QC). Connection success ≠ signal quality.
6. Paradigm-specific recipes (P300, SSVEP, cVEP, online load API):
   `references/applications.md`.

## Ecosystem map

| Repo (github.com/Neuradock) | Contents |
|---|---|
| eeg-workstation-python | Official SDK: `Neuradock_library.py` (`text2data_usb/bluetooth`, `eeg_quality_check`, `clean_eeg_data`), 6 tutorial notebooks |
| eeg-workstation-agent | `neuradock-agent` CLI: QC, Alpha dynamics, cognitive load, Rest/Task, online dashboard/API (`serve`, `online`, `demo`, `doctor`) |
| eeg-workstation-examples | Demos: eyes-open/closed, PSD, band power, SSVEP, cVEP, P300, MI neurofeedback, markers |
| eeg-workstation-data | Public sample datasets (USB/Bluetooth txt, visual cognitive-load mini dataset) |
| eeg-workstation-docs | Data format, tutorials, hardware interface |
| eeg-workstation-hardware | Pinout/port specs for third-party integration |

## Hard boundaries (summary — full list in references/scientific-boundaries.md)

Never output: medical/clinical diagnosis; emotion/deception/fatigue/attention
"diagnosis"; absolute cognitive-load scores or uncalibrated cross-person
comparison; cortical source localization from this montage; causal/population
claims from one recording; precise ERP latency without measured display/marker
timing. Never present synthetic data as human EEG. Visual-flicker paradigms
require operator warning, consent, immediate stop, and conservative luminance.
