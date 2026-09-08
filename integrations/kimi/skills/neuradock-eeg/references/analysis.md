# Analysis algorithms and result fields

All analysis runs after parsing, integrity checks, preprocessing, and QC.
Implementations: bundled `scripts/neuradock_toolkit.py`, official
`neuradock-agent` CLI, and SDK notebooks.

## Signal quality (always first)

The bundled CLI uses one-second channel segments on unfiltered input so
bandpass/notch filters do not erase electrical-noise or amplitude evidence.
Feature extraction uses median centering, 1-45 Hz bandpass and 50 Hz notch
after this quality gate. Thresholds are in `device-profile.md`. Other SDK or
Agent pipelines may use different QC stages; record which implementation and
stage produced each report. Key result fields:

- `retention_rate`: fraction of complete one-second segments retained after QC.
- `rejected_segment_count`, `bad_channel_candidates` (ratio > 0.40).
- `issue_counts`: `line_noise`, `emg_or_high_frequency`, `extreme_amplitude`.
- `spatial_quality`: sparse posterior neighbor consistency — not source
  localization.
- `status`: `pass`/`warning`; a warning is not a clinical abnormality.

Put quality warnings near the beginning of any report. Do not fill gaps by
interpolation or speculation.

## PSD and band power

Welch PSD on preprocessed data. Bands: Delta 1-4, Theta 4-8, Alpha 8-13,
Beta 13-30, Gamma 30-45 Hz. Report absolute and relative (per-band / total
1-45 Hz) power per channel plus `posterior_alpha_peak_hz` (peak within 8-13 Hz
averaged over posterior channels). PSD/band power is not cortical source
localization.

Bundled `bands` CLI requires all complete one-second segments and spatial
consistency to pass. It pauses feature output on failed QC or malformed input
rows. Select a continuous valid interval rather than concatenating disjoint
segments into a new PSD. Array helpers alone do not establish acquisition QC.

## Alpha dynamics

Rolling posterior Alpha over one continuous recording:

- Channels: posterior `PO3, PO4, O1, Oz, O2`; left `PO3, O1`; right `PO4, O2`.
- Window 4 s, step 1 s; a window is valid when >= 80% of its samples pass QC.
- Features per window: `posterior_log_alpha_power` (log10 mean posterior Alpha
  power), `alpha_suppression_from_baseline` (baseline median minus current;
  positive = weaker Alpha than this recording's baseline), `alpha_peak_hz`,
  `alpha_asymmetry_right_minus_left` (normalized right-minus-left).
- States weak/baseline/strong come from within-recording posterior log Alpha
  tertiles — relative to the recording, never universal thresholds.
- Also report `state_counts`, `strongest/weakest_alpha_window`, and compact
  state time ranges. Disconnected label plots indicate excluded windows; do not
  connect excluded periods as if valid.

The bundled `alpha` CLI checks the original samples aligned to each filtered
window, including frequency contamination and spatial consistency. Malformed
TXT rows block feature output because the remaining rows would compress gaps.
For multi-trial NPY input, explicitly select a one-based `--trial`; the toolkit
does not silently analyze the first trial or combine trials.

Weak Alpha is consistent with Alpha suppression but does not by itself prove
cognitive load without task context and adequate quality.

## Visual cognitive load (offline index)

- Features: posterior Alpha suppression (weight 65%), Alpha peak-frequency
  shift (15%), posterior left/right Alpha asymmetry (20%).
- Valid windows labeled low/medium/high by within-recording score tertiles.
- Result fields: `valid_window_count`, `excluded_window_count`, `class_counts`,
  `load_percentile` (rank within the same recording), `label_ranges`.
- Trial-batch input: `.npy` `(trials, 7, samples)`; each trial filtered and
  QC'd independently; users may exclude one-based trial numbers.
- Labels are relative to one recording — no absolute measurement, no
  cross-person/session comparison without calibration.

## Rest/Task comparison

- Input order: Rest first, Task second; same participant or explicitly paired
  acquisition. Each input: continuous TXT or NPY trial batch.
- Primary contrast: quality-valid posterior log Alpha power —
  `posterior_log_alpha_power.task_minus_rest` (median Task − Rest),
  `task_to_rest_power_ratio`.
- Secondary descriptive contrasts: Alpha peak-frequency shift, asymmetry
  magnitude, quality retention.
- Keep conditions paired within participant; show accepted duration/trials per
  condition. Do not compare the within-input low/medium/high counts across
  conditions as equivalence evidence.
- Lower Task posterior Alpha is consistent with stronger Alpha suppression —
  not proof of higher cognitive load, causality, or any clinical conclusion.

## Online visual-load API (neuradock-agent)

- `neuradock-agent serve` (dashboard), `POST /api/analyze`, `GET /api/demo/next`.
- Online pipeline: median centering, 1-45 Hz bandpass, 50 Hz notch,
  window-level quality gate, posterior Alpha features.
- Output: rolling `visual_load_index` (0-100, relative to recent valid
  windows), `alpha_state` (initializing/weak/baseline/strong), Alpha peak,
  suppression, asymmetry, quality warnings, `baseline.history_count`.
- The online index is session-relative monitoring — not an absolute attention,
  fatigue, clinical, or performance score. Use causal filtering only for
  future-dependent feedback.

## Classifiers and validation

Training-only calibration; balance classes; leakage-safe splits (keep
calibration and evaluation blocks separate); report held-out AUC/balanced
accuracy with confidence intervals where feasible. Never train and evaluate on
overlapping windows.
