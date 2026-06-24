# Result Field Guide

## Shared Fields

- `workflow`: reviewed workflow identifier.
- `status`: `pass` or `warning`; a warning does not mean clinical abnormality.
- `recording`: source, transport, shape, duration, channels, sampling rate, and
  amplitude unit.
- `warnings`: deterministic issues that must be discussed prominently.

## Signal Quality

- `retention_rate`: fraction of original samples retained after segment QC.
- `rejected_segment_count`: rejected one-second segments.
- `bad_channel_candidates`: channels affected in more than the configured
  segment ratio.
- `issue_counts.line_noise`: channel-segment line-noise flags.
- `issue_counts.emg_or_high_frequency`: channel-segment EMG/high-frequency
  flags.
- `issue_counts.extreme_amplitude`: channel-segment 100 microvolt outlier flags.
- `spatial_quality`: sparse neighbor consistency, not source localization.
- `acquisition_context`: heuristic environment and movement/muscle labels.

## Alpha Dynamics

- `state_counts`: number of weak, baseline, strong, or stable Alpha windows.
- `posterior_log_alpha_power`: log10 posterior Alpha power for one window.
- `alpha_suppression_from_baseline`: baseline median log Alpha minus current
  log Alpha; positive values mean weaker Alpha than this recording's baseline.
- `alpha_peak_hz`: posterior peak frequency inside 8-13 Hz.
- `alpha_asymmetry_right_minus_left`: posterior right-minus-left Alpha
  asymmetry normalized by total left/right Alpha power.
- `strongest_alpha_window`: window with the highest posterior log Alpha power.
- `weakest_alpha_window`: window with the lowest posterior log Alpha power.
- `alpha_state_ranges`: compact time ranges for weak, baseline, and strong
  Alpha states.

Weak Alpha is a relative Alpha-suppression observation. It must not be stated as
absolute cognitive load without task context, quality review, and validation.

## PSD

- `posterior_alpha_peak_hz`: peak frequency in the posterior 8-13 Hz range.
- `absolute_band_power`: integrated power by channel and band.
- `relative_band_power`: each band divided by total 1-45 Hz power.

## Visual Cognitive Load

- `valid_window_count`: windows meeting the clean-sample requirement.
- `excluded_window_count`: windows withheld because quality was insufficient.
- `class_counts`: valid low, medium, and high windows.
- `load_percentile`: relative rank among valid windows in the same recording.
- `label_ranges`: compact time ranges for valid labels.
- `trial_number`: original one-based trial number for trial-batch input.
- `low_retention_trial_numbers`: trials below the clean-window requirement.

Disconnected label plots usually indicate excluded windows, not missing file
output. Do not connect excluded periods as if they were valid measurements.

## Rest/Task Comparison

- `condition_labels`: display names in reference/comparison order.
- `conditions.rest` and `conditions.task`: deterministic per-input results.
- `posterior_log_alpha_power.task_minus_rest`: median Task minus Rest log Alpha.
- `task_to_rest_power_ratio`: median posterior Alpha power ratio.
- `alpha_peak_hz.task_minus_rest_hz`: descriptive peak-frequency shift.
- `alpha_asymmetry_magnitude.task_minus_rest`: descriptive asymmetry change.

Do not interpret similar low/medium/high counts as evidence that the conditions
are equivalent; the labels are generated from separate within-input tertiles.

## Online Visual Load API

- `current.visual_load_index`: rolling 0-100 index derived from current Alpha
  suppression relative to recent valid windows.
- `current.alpha_state`: initializing, weak, baseline, or strong Alpha.
- `quality`: online line-noise, EMG/high-frequency, and extreme-amplitude gate.
- `baseline.history_count`: number of valid windows in the rolling baseline.

The online index is a session-relative monitoring feature, not an absolute
attention, fatigue, clinical, or performance measurement.
