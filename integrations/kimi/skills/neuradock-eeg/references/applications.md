# Application recipes

Starting workflows, not validated-performance claims. Keep the canonical
device profile, expose protocol parameters in configuration, and validate with
the intended participant, display, and session. Validate in this order:
simulation → replay → live hardware.

## Generated project contract

Unless editing an existing project, include:

- `README.md`: setup, experiment instructions, hardware endpoint config,
  simulator/replay/live commands, expected outputs, limitations.
- Device-profile config with the exact canonical channel order and 250 Hz rate.
- Source-adapter interface so simulation/replay/live feed the same pipeline.
- Rolling TCP buffer handling partial and concatenated lines.
- Signal-quality gating before training, classification, feedback, or
  interpretation.
- Monotonic host timestamps for markers plus device timestamps when available.
- Deterministic tests: packet fragmentation, concatenated packets, malformed
  rows, channel order, sample rate, marker alignment, the requested feature.
- Output metadata: settings, source mode, channel order, sample rate, marker
  definitions, timing evidence, QC result, software version, random seed.

## Signal-quality / device applications (best first live demo)

Contact-quality dashboard, acquisition-environment check, packet/timestamp
monitor, raw/filtered scope, PSD viewer, replay inspector, marker-latency test.
These validate transport and headset before any classifier is introduced.

## P300 oddball / ERP

Public acquisition example: target marker `1`, non-target `2`, 250 Hz, 7 EEG
channels from 8-field groups; records EEG, timestamps, config, marker CSV.
Stages for a generated project:

1. Randomized target/non-target events, configurable target ratio, jittered
   interval; log frame/presentation timing.
2. Continuous EEG + markers through the common source adapter.
3. QC; causal online preprocessing where required; offline 0.1-30 Hz filtering.
4. Epoch ~`-0.2 to 0.8 s` around events; baseline-correct with pre-event
   period; reject contaminated epochs; retain class/trial counts.
5. Plot target vs non-target ERPs at CP/posterior sensors plus the difference.
6. Classification: fit on training blocks only, balance classes, report
   held-out AUC/balanced accuracy with CIs where feasible.

Do not call a positive deflection a P300 solely because it occurs near 300 ms.
Report latency range, electrode, condition contrast, accepted-trial count, and
timing/QC evidence.

## Visual SSVEP

Posterior montage suits sensor-level steady-state demos. Public example:
PsychoPy, assumed 60 Hz display, 4 Hz flicker, 6 trials, 1 s stimulation +
1 s rest. Generated code must measure the actual display refresh rate and
treat legacy channel mappings as noncanonical.

Multi-target demo:

1. Frequencies realizable by integer frame patterns at the measured refresh rate.
2. Log frame drops and actual frame sequence per target.
3. 2-4 s decision windows; configurable rest/calibration blocks.
4. Posterior channels; CCA/FBCCA with reference sinusoids + harmonics, or a
   clearly documented spectral baseline.
5. Per-participant/session calibration, separate evaluation blocks, confidence
   display plus a no-control state.

Safety: photosensitive-seizure/flicker warning, immediate stop action,
conservative luminance/contrast defaults, informed operator confirmation —
never run visual stimulation without it; stop immediately when asked.

## cVEP

Public case configuration (not device invariants): 63-chip m-sequence, 3
display frames per chip, 189 frames at 60 Hz (3.15 s), ~788 samples at 250 Hz,
4 classes, 20 trials/class, five-subband TTCA-style pipeline. Enable QC and
leakage-safe splits; legacy examples that disable QC are not a release
criterion.

## Alpha dynamics / band power apps

Posterior channels, Alpha 8-13 Hz, rolling 4 s/1 s, >= 80% clean-sample
requirement per window. Report posterior log Alpha power, Alpha peak frequency,
optional posterior left/right asymmetry. Label weak/baseline/strong from
within-recording or calibrated-session values only. Reference demos:
eyes-open/closed, PSD, band-power notebooks in `eeg-workstation-examples`.

## Online / interactive demos

`eeg-workstation-agent` ships a browser dashboard (`neuradock-agent serve`),
demo mode without hardware (`demo`), realtime workload API, and example apps:
visual search, adaptive vehicle HMI, cognitive-load game, adaptive UI. Reuse
their server/static structure when generating similar apps; keep the load
index session-relative and quality-gated.

## Motor imagery caution

MI examples expecting T5/T6 or denser motor montages are legacy research
templates and do not map to the canonical seven NeuraDock channels. Preserve
the real channel order, explain the montage limitation, and require new
validation rather than relabeling sensors.
