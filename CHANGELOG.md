# Changelog

## 2026.6.24 - 2026-06-24

- Prepared the developer-focused open-source release.
- Added visual search, adaptive vehicle HMI, and cognitive load game examples
  driven by the quality-gated realtime API.
- Made `serve` generate a deterministic synthetic replay when no demo file is
  supplied.
- Separated human EEG recordings from the software release and added a
  SHA256-verifying public-data downloader.
- Added explicit dataset usage rules for within-subject comparison, mixed eye
  states, quality warnings, and non-diagnostic interpretation.
- Updated package, API, context, demo, citation, and test versions.

## 2026.6.22 - 2026-06-22

- Prepared a clean GitHub source release with generated results, paper drafts,
  local build products, and participant validation folders removed.
- Updated public setup instructions for user-controlled project paths and
  Python virtual environments.
- Confirmed LLM credentials are configured locally by each user and are not
  included in the repository.
- Normalized the public amplitude unit string to ASCII `uV` for cross-platform
  terminal and documentation compatibility.

## 2026.6.18 - 2026-06-18

- Refocused the product around visual cognitive load instead of a general EEG
  workstation agent.
- Added the reviewed Alpha Dynamics workflow for strong/weak posterior Alpha,
  Alpha suppression from baseline, Alpha peak frequency, and posterior
  left/right asymmetry.
- Added time-domain, frequency-domain, and time-frequency Alpha visualizations.
- Added focused sample data for `open_closed_eye2.txt` and one S01 Rest/Task
  pair.
- Added the online visual cognitive-load API and local HTML dashboard.
- Updated LLM routing and compact interpretation summaries for Alpha Dynamics.

## 0.1.1 - 2026-06-12

- Added the phase-one versioned NeuraDock LLM context pack with hardware,
  workflow, scientific-boundary, result-field, implementation, and reviewed
  case guidance.
- Updated the formal zero-based channel mapping to
  `CP5, CP6, PO3, PO4, O1, Oz, O2` and the amplitude unit to microvolts.
- Added context metadata to LLM audit traces and a required prominent warning
  policy for low-quality result explanations.
- Added offline relative visual cognitive-load labeling from posterior Alpha
  suppression, peak-frequency shift, and spatial asymmetry.
- Added reviewed Rest/Task Visual Cognitive Load comparison for TXT and
  trial-batch NPY inputs.
- Added non-destructive one-based trial exclusion for supported NPY workflows.
- Added persistent `/mode LLM` configuration, constrained workflow planning,
  privacy-bounded result explanation, and failure-safe LLM audit artifacts.
- Added the hardware-boundary benchmark, evidence scripts, and academic paper.

## 0.1.0 - 2026-06-07

- First public-facing NeuraDock-specific Agent design.
- Added USB/Bluetooth recording parser and TCP stream reader.
- Added device doctor, signal quality, PSD, Alpha Blocking, and task/rest
  workflows.
- Added deterministic natural-language routing without arbitrary code
  execution.
- Added reproducible run artifacts, tests, documentation, and demo data
  generation.
