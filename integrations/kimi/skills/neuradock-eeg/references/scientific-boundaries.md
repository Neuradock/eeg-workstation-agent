# Scientific, privacy, and safety boundaries

## Supported outputs

- recording integrity, malformed packets, timing continuity, and
  signal-quality status;
- sensor-level time series, PSD, band power, posterior Alpha dynamics, and
  ERP contrasts;
- session-calibrated BCI classifier outputs with honest validation metrics;
- possible acquisition problems such as movement, muscle activity, line noise,
  unstable contact, or marker/timing failure;
- relative within-recording/session visual-load demonstrations with explicit
  limits.

## Unsupported conclusions

- medical diagnosis, treatment, or clinical decision-making;
- emotion, deception, personality, mental-health, fatigue, or attention
  diagnosis;
- absolute cognitive-load scores or uncalibrated comparison across
  people/sessions;
- cortical source localization from this sparse montage;
- causality, population claims, or deployment readiness from one recording or
  demo;
- precise ERP latency when the display/marker path was not independently
  measured.

## Low-quality data

Put the warning near the beginning. Report retention, malformed rows, rejected
windows, bad-channel candidates, and thresholds. Separate descriptive
observations that remain visible from conclusions made uncertain by quality. Do
not fill gaps by interpolation or speculation. Recommend checking electrode
contact, headset placement, participant motion, muscle tension, cable
stability, electrical sources, and protocol timing as relevant.

## Privacy and artifacts

Process raw EEG locally by default. Avoid embedding participant names in
filenames, record consent/protocol identifiers separately, define
retention/deletion behavior, and never commit raw participant data to Git.

## Human safety

NeuraDock applications are research/development software unless separately
validated and regulated. Visual-flicker experiments need an operator-visible
warning, voluntary consent, an immediate stop control, conservative
luminance/contrast, and exclusion procedures set by the responsible study team.
Never continue a stimulation task after the participant or operator asks to
stop. Never present synthetic data as human EEG or a research demo as a
clinical system.
