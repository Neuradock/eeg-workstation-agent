# Public Release Checklist

The software is runnable as a focused visual cognitive-load alpha release. The
following hardware facts must be signed off by the NeuraDock hardware and
recording-software owners before claims are expanded beyond the documented
profile:

- [x] Confirm the formal zero-based parsed channel order:
  `0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2`.
- [x] Treat conflicting mappings in older sample-data materials as legacy.
- [x] Confirm that current parsed amplitudes and the 100 absolute-outlier
  threshold are expressed in microvolts (`uV`).
- [ ] Confirm whether USB and Bluetooth use identical scaling.
- [ ] Confirm timestamp units and whether timestamps are device-side or
  host-side.
- [ ] Confirm marker timing: per sample, per packet, or host-injected state.
- [ ] Confirm the TCP `start` command and default packet field count.
- [ ] Validate QC thresholds against a documented set of good-contact,
  poor-contact, movement, and line-noise recordings.
- [x] Include only the focused sample files selected for this release.
- [ ] Run the Device Doctor against release hardware on each supported
  recording-software version.

The current Agent reports parsed EEG amplitude in microvolts. Remaining
unchecked items are documented limitations, not implied validations.
