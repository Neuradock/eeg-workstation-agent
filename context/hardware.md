# Hardware Context

## Product Position

NeuraDock EEG Workstation is a 7-channel dry-electrode EEG development kit for
researchers, engineers, BCI developers, and prototyping teams. In this release,
NeuraDock Agent is focused on visual cognitive-load workflows built around
posterior Alpha dynamics.

## Formal Channel Mapping

The current Agent uses this exact zero-based mapping:

| Data index | Electrode |
|---:|---|
| 0 | CP5 |
| 1 | CP6 |
| 2 | PO3 |
| 3 | PO4 |
| 4 | O1 |
| 5 | Oz |
| 6 | O2 |

The montage covers centro-parietal, parieto-occipital, and occipital posterior
sites. It is useful for visual EEG development such as SSVEP, cVEP, P300,
posterior Alpha analysis, and related interaction prototypes.

## Acquisition

- Sampling rate: 250 Hz.
- Unit: microvolts (`uV`).
- USB text: one sample group per line after timestamp and marker fields.
- Bluetooth text: five sample groups per line after timestamp and marker
  fields.
- Each sample group contains seven EEG values and one reserved field.
- Live Device Doctor uses a TCP stream and saves the capture for reproduction.

## Quality Thresholds

The current engineering heuristics include:

- 49-51 Hz line-noise power threshold: 10.
- 20-40 Hz EMG/high-frequency power threshold: 20.
- Absolute outlier threshold: 100 microvolts.
- Outlier-count threshold: more than 2 samples per one-second segment.
- Bad-channel candidate threshold: affected in more than 40% of segments.
- Minimum neighbor correlation: 0.15.

These are workflow engineering thresholds, not clinical limits.

## Source Notes

Authoritative current sources:

- `src/neuradock_agent/profile.py`
- `docs/data-protocol.md`
- https://github.com/Neuradock/eeg-workstation
- https://github.com/Neuradock/eeg-workstation-docs
