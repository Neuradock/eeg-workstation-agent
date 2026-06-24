# Dataset Use

The NeuraDock Agent software repository and the EEG data repository are
separate releases.

## Upstream Dataset

Dataset version: `20260622`

Repository:

https://github.com/Neuradock/eeg-workstation-data

Mini dataset:

https://github.com/Neuradock/eeg-workstation-data/tree/add-visual-cognitive-load-mini-dataset-20260622/visual_cognitive_load/mini_dataset_v20260622

This software repository does not redistribute human EEG files. Run:

```powershell
python scripts\download_example_data.py
```

to download three public examples and verify their SHA256 values.

## Required Interpretation Rules

1. Use each subject's own rest or baseline file.
2. Compare Rest and Task only within the same subject and session.
3. Do not infer population or cross-subject differences from this dataset.
4. Treat Alpha suppression as a relative within-subject signal.
5. Mixed eye-state files can alter posterior Alpha independently of workload.
6. Report signal-quality warnings; do not hide or override them.
7. Do not use the recordings for medical, clinical, attention, fatigue, or
   performance diagnosis.

## Channel And Format

```text
Sampling rate: 250 Hz
Channel order: 0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2
Amplitude unit: microvolts (uV)
Format: NeuraDock raw text export parsed to 7 x samples
```

## Dataset Scope

The upstream mini dataset contains:

- `cohort_2subj_ljw_xzy`: task variants with subject-specific baselines.
- `cohort_3subj_rest_task`: S01, S02, and S03 Rest/Task pairs across two
  sessions.

For the `xzy` mixed-eye-state files, interpret Alpha changes with particular
caution.

## Licensing And Citation

The MIT License in this repository applies to the software, not automatically
to EEG recordings. Check the upstream data repository for its current data
license, citation instructions, consent scope, and redistribution terms before
publishing derived datasets or redistributing recordings.
