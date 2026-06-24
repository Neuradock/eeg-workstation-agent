# Reviewed Workflows

NeuraDock Agent 2026.6.24 is focused on visual cognitive-load workflows. The
main path is: preprocessing quality gate, posterior Alpha dynamics, offline
Rest/Task comparison, online visual-load API, and bounded LLM interpretation.

## Signal Quality

Purpose: inspect recording integrity before cognitive-load analysis.

The workflow filters the signal, checks one-second channel segments for line
noise, EMG/high-frequency power, and absolute outliers, identifies bad-channel
candidates, checks sparse posterior spatial consistency, estimates acquisition
conditions, and retains quality-approved samples.

Outputs include `results.json`, `report.md`, deterministic figures, and
`clean_eeg_data.npz`.

## Alpha Dynamics

Purpose: automatically locate strong and weak posterior Alpha periods in one
continuous recording.

- Data source used by the public example: `open_closed_eye2.txt`.
- Posterior channels: O1, O2, Oz, PO3, PO4.
- Left channels: O1, PO3.
- Right channels: O2, PO4.
- Default window: 4 seconds.
- Default step: 1 second.
- A window is valid when at least 80% of its samples pass the quality gate.
- Features: posterior log Alpha power, Alpha suppression from baseline,
  Alpha peak frequency, and posterior left/right Alpha asymmetry.
- Weak, baseline, and strong Alpha states are assigned from within-recording
  posterior log Alpha tertiles.
- Outputs include time-domain, frequency-domain, and time-frequency figures.

Strong/weak Alpha states are relative to the analyzed recording. Weak Alpha can
be consistent with Alpha suppression, but it does not by itself prove cognitive
load without task context and adequate signal quality.

## PSD and Frequency-Band Power

Purpose: describe sensor-level spectral content as an advanced support
workflow.

The workflow applies fixed offline preprocessing and Welch PSD estimation. It
reports absolute and relative power for Delta 1-4 Hz, Theta 4-8 Hz, Alpha 8-13
Hz, Beta 13-30 Hz, and Gamma 30-45 Hz, plus the posterior Alpha peak.

PSD and band power are not cortical source localization.

## Visual Cognitive Load

Purpose: estimate relative temporal visual cognitive-load changes within one
recording.

- Visual channels: O1, O2, Oz, PO3, PO4.
- Left channels: O1, PO3.
- Right channels: O2, PO4.
- Default window: 4 seconds.
- Default step: 1 second.
- A window is valid when at least 80% of its samples pass quality control.
- Features: posterior Alpha suppression, Alpha peak-frequency shift, and
  posterior left/right Alpha asymmetry.
- Weights: 65%, 15%, and 20%, respectively.
- Valid windows are labeled low, medium, or high using within-recording score
  tertiles.

The labels are relative to one recording. They are not absolute measurements
and should not be compared across people or sessions without calibration.

### Trial-Batch Input

Visual Cognitive Load and Signal Quality accept `.npy` trial batches shaped
`(trials, 7, samples)` or `(trials, samples, 7)`. Every trial is filtered and
quality-checked independently. Users may exclude one-based trial numbers before
analysis; the source file is not modified.

Legacy numeric object-dtype NPY files are loaded with a restricted NumPy
unpickler and immediately converted to a floating-point array.

## Rest/Task Visual Cognitive Load Comparison

Purpose: compare one Rest input with one Task input from the same participant
or explicitly paired acquisition.

- Input order is Rest first, Task second.
- Each input may be a continuous TXT recording or an NPY trial batch.
- The primary contrast uses quality-valid posterior log Alpha power.
- Additional contrasts describe Alpha peak frequency, Alpha asymmetry
  magnitude, and signal-quality retention.
- Separate temporal or trial plots are retained for each condition.
- Low/medium/high labels remain within-input tertiles and are not the primary
  cross-condition comparison.

Lower Task posterior Alpha than Rest is consistent with stronger Alpha
suppression, but it does not by itself prove higher cognitive load or establish
a causal or clinical conclusion.

## Device Doctor

Purpose: capture a short live TCP stream, inspect packet and timestamp behavior,
run signal-quality checks, and save a reproducible text capture.

## Online Visual Cognitive Load API

Purpose: process incoming 7-channel samples in rolling windows and expose a
browser dashboard.

- API endpoint: `POST /api/analyze`.
- Demo endpoint: `GET /api/demo/next`.
- Dashboard command: `neuradock-agent serve`.
- Online preprocessing: median centering, 1-45 Hz bandpass, 50 Hz notch,
  window-level quality gate, posterior Alpha feature extraction.
- Output: rolling visual-load index, Alpha state, Alpha peak, Alpha
  suppression, posterior asymmetry, and quality warnings.

The online index is relative to the rolling Alpha baseline and is not an
absolute cognitive-load, attention, fatigue, clinical, or performance score.

## Demonstration

Purpose: exercise the software without hardware or live streaming. Synthetic
results and public sample files are examples, not human EEG validation.
