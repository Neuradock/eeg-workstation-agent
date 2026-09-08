# Kimi skill 0.1.0-beta

Published source preparation: 2026-09-08.

This release packages NeuraDock's existing `kimi_neuradock-eeg.skill` as
inspectable source, an install guide, and reproducible ZIP / `.skill` downloads.
The original input archive SHA-256 was
`536366052c6ca7f4f70f57557a51801d04976f995bd75c23f349a921faa15e3f`.
The published archive includes the release fixes below and is not byte-identical
to that original input. See `downloads/SHA256SUMS.txt` for download hashes.

## Release fixes

- Reject malformed Bluetooth packets atomically, including non-finite EEG values.
- Retain field positions when detecting the transport format.
- Check unfiltered input before filters suppress 50 Hz noise or amplitude artifacts.
- Gate band-power output and Alpha windows on signal quality.
- Pause CLI feature output when malformed rows create gaps.
- Treat undefined posterior correlations, including flatline data, as warnings.
- Require explicit trial selection for multi-trial NPY input and correct its sample count.
- Support NumPy 1.x and 2.x numerical integration APIs.

These changes affect only the bundled Kimi toolkit. They do not change the
Agent's core processing code, public API, hardware profile, or thresholds.

## Validation performed

- Windows, Python 3.12.0, NumPy 1.26.4, SciPy 1.15.3.
- 57 repository tests passed, including 13 Kimi toolkit regression tests.
- Skill frontmatter/structure validator passed.
- Kimi Code CLI 1.44.0's installed skill discovery code recognized
  `neuradock-eeg` as a standard skill from the explicit skills directory.
- Public `open_closed_eye2.txt` replay: 13,210 samples, 250 Hz, seven channels,
  zero malformed rows. Parse, QC, bands and Alpha commands completed.
- This replay produced a QC warning. Band output was withheld and all 49 Alpha
  windows were excluded. This is a gate-behavior check, not a successful
  physiological finding or a claim that this recording is universally unusable.
- Deterministic clean 10 Hz synthetic data passes the Alpha peak test.
  Synthetic EMG/line noise, bad packets and flatline data exercise rejection paths.

Public replay input SHA-256:
`0e35ae1375b40f65cbb589eb0780d475bf2e098ce9d51d9db350b5b9b176a279`.
Recordings and temporary results are not included in the skill downloads.

## Limits

Kimi skill discovery was tested without making an LLM request. Model behavior,
Kimi web/desktop import dialogs, and live-device acquisition were not validated
by this release. Use the documented Kimi Code `--skills-dir` loading route.

The thresholds are engineering heuristics. Raw-input QC is intentionally more
conservative than post-filter QC and may reject recordings accepted by older
examples. Report the processing stage and rejected data rather than bypassing
the gate to obtain a desired result.

Online TCP buffering, reconnection, visual-stimulus timing and hardware control
remain tasks for generated applications and target-device verification. The
bundled CLI analyzes recorded files; it is not a live TCP acquisition client.

For full workflow guidance see the [installation guide](README.md),
[skill](skills/neuradock-eeg/SKILL.md) and
[scientific boundaries](skills/neuradock-eeg/references/scientific-boundaries.md).
