# Canonical NeuraDock device profile

Treat these values as invariants unless the user provides a newer, explicit
hardware profile. If a public example conflicts, keep this profile and flag the
example as legacy.

## Signal layout

- Device: NeuraDock EEG Workstation, public profile v2.
- Sample rate: 250 Hz.
- Amplitude unit after parsing: microvolts (`uV`).
- Array orientation for analysis: `channels x samples`.
- Exact zero-based channel order:
  `0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2`.
- Posterior set: `PO3, PO4, O1, Oz, O2`.
- Posterior left: `PO3, O1`; posterior right: `PO4, O2`.
- Nominal line frequency: 50 Hz.

Never reuse legacy labels such as T5/T6 for these seven indices. Never reorder
columns to make an algorithm appear compatible.

## Public text/TCP packet shapes

Each comma-separated line begins with `timestamp, marker`, followed by packet
groups of `7 EEG values + 1 reserved field` (reserved is typically `0`):

- USB: one group per line → at least 10 fields total.
- Bluetooth: five groups per line → at least 42 fields total. Expand each line
  into five chronological samples.
- Recordings may start with a `HEADER_DEF,...` line — skip it.
- Timestamps may be numeric or clock strings (`HH:MM:SS.mmm`). Generate
  within-packet timestamps as `base + sample_index / 250` only when the base
  timestamp unit is confirmed.
- The marker applies to each expanded sample unless the application keeps
  packet-level marker semantics separately.

TCP defaults documented in the current public profile are `127.0.0.1:9600` and
start command `start`. They are configuration defaults, not endpoint discovery.
A robust TCP reader must keep a text buffer because one `recv` may contain a
partial line, one line, or many lines.

## Quality profile

Run one-second channel segments and record the QC input stage. The bundled
CLI checks unfiltered samples before preprocessing for features. Current public
thresholds (device-workflow heuristics, not universal EEG standards):

| Check | Threshold |
|---|---:|
| 49-51 Hz line-noise power | > 10 |
| 20-40 Hz EMG/high-frequency power | > 20 |
| absolute amplitude | >= 100 uV |
| absolute outlier count | > 2 per second |
| bad-channel segment ratio | > 0.40 |
| minimum neighbor correlation | < 0.15 |

Report method, segment length, preprocessing, retained samples, bad-channel
candidates, malformed-row ratio, and thresholds with every QC result.

## Preprocessing defaults

- Bundled offline CLI: one-second QC on unfiltered samples, then median
  centering, 1-45 Hz bandpass, 50 Hz notch and quality-gated feature extraction.
  Other repository pipelines may differ; report their actual QC stage.
- Online rolling analysis: 4-second window, 1-second step, 1-45 Hz bandpass,
  50 Hz notch, window-level QC.
- Do not apply zero-phase filters to future-dependent live feedback; preprocess
  each completed rolling window (accepting its latency) or use a stateful
  causal filter.
- Do not notch 50 Hz and then claim post-notch 50 Hz power is an independent
  measure of raw electrical noise; compute QC from the appropriate stage.

## Provenance

This profile consolidates the public `eeg-workstation-agent` profile and
data-protocol documentation plus the public Python/examples repositories.
Public repositories can change; record the profile version in generated outputs.
