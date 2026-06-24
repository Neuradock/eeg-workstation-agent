# Scientific Boundaries

NeuraDock Agent is an engineering and research-development tool.

## Supported Language

- signal quality and recording integrity
- sensor-level posterior EEG patterns
- PSD and frequency-band power
- relative within-recording visual cognitive-load stratification
- posterior Alpha suppression and peak-frequency dynamics
- sparse left/right posterior Alpha asymmetry

## Unsupported Claims

- medical diagnosis or treatment
- mental-health, emotion, deception, or personality inference
- fatigue or attention diagnosis from a single ratio
- absolute or cross-participant cognitive-load diagnosis
- cortical source localization
- causal conclusions from an uncontrolled comparison
- population-level claims from one participant

Quality thresholds are hardware workflow heuristics, not clinical limits.
Results should be validated for each study design.

When data quality is low, explanations continue but must place a prominent
warning near the beginning and state how rejected segments, bad channels, or
excluded windows limit confidence.

LLM explanations summarize deterministic outputs and must preserve these same
boundaries. They do not replace protocol-specific validation or expert review.
