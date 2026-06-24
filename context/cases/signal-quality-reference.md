# Reference Case: Signal Quality

Case type: reviewed local workflow examples

## Higher-Quality Example

A recorded example retained about 95% of samples, had no bad-channel
candidates, and produced no workflow warnings. Appropriate interpretation:
the recording was broadly usable under the current engineering thresholds.
This does not prove clinical normality or guarantee suitability for every
experiment.

## Warning Example

An internal validation recording analyzed with hardware profile 1.1 retained
about 81% of samples and showed low neighbor correlation in CP6 and O2 plus
mild movement or muscle-artifact indications.
Appropriate interpretation: much of the recording remained usable, but local
contact, headset pressure, movement, or channel-specific noise should be
checked before relying on spatial comparisons.

## Incorrect Interpretation

Do not call a low-correlation channel neurologically abnormal. The warning is a
sensor-level engineering flag.

Sources:

- reviewed internal validation results produced with hardware profile 1.1;
  participant recordings are not distributed in the public source release
- `context/scientific-boundaries.md`
