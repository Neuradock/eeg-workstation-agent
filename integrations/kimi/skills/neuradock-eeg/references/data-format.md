# NeuraDock data formats and parsing

## Sources

| Source | Notes |
|---|---|
| Recorded TXT (USB) | 1 sample/line from NeuraDock Recording Software |
| Recorded TXT (Bluetooth) | 5 samples/line |
| Real-time TCP (USB/Bluetooth) | same line shapes streamed; default `127.0.0.1:9600`, command `start` |
| NPY trial batches | `(trials, 7, samples)` or `(trials, samples, 7)` |
| Public datasets | `eeg-workstation-data` repo (USB/Bluetooth txt, visual cognitive-load mini dataset) |

## Recorded TXT structure

Comma-separated lines. First line may be a header: `HEADER_DEF,T,P,C,...(,0,...)` —
skip it. Data lines:

```
timestamp, marker, [7 EEG + reserved]*G
```

- G=1 (USB) → ~10 fields; G=5 (Bluetooth) → ~42 fields.
- Reserved field is usually `0`; ignore it.
- Expand Bluetooth lines into 5 chronological samples, preserving order.
- Timestamp: numeric seconds or clock string `HH:MM:SS.mmm`. Record whether it
  is device-side or host-side.
- Marker column may hold numeric event codes (e.g. P300: target `1`,
  non-target `2`) or be unused (`none`/constant).
- Channel columns follow the canonical order: CP5, CP6, PO3, PO4, O1, Oz, O2.
- Parsed values are microvolts; do not assume a raw-to-voltage conversion
  unless the recording workflow documents one.

## Parsing rules

1. Preserve the original channel order; validate 7 channels before analysis.
2. Convert USB and Bluetooth inputs into one shared parsed form:
   `sample_index, timestamp, CP5..O2, marker` or a `(7, N)` array.
3. Count malformed rows (wrong field count, non-numeric values) and report them.
4. Check for missing values, dropped samples, and timestamp continuity.
5. Keep raw and processed data separate; never overwrite source recordings.
6. Store metadata (condition, channel layout, sample rate, connection mode,
   raw/preprocessed state) alongside results.

## Real-time TCP

- One `recv` may contain a partial line, one line, or many lines — maintain a
  text buffer and split on newlines.
- Apply the same line parser as for TXT files; expand Bluetooth packets inline.
- Use monotonic host timestamps for markers plus device timestamps when
  available. Software-side markers do not establish millisecond timing
  accuracy; measure display/marker latency when the experiment depends on it.
- Get host/port from the user or project config; never scan the network.

## Official SDK reference

`eeg-workstation-python/examples/Neuradock_library.py`:

- `text2data_bluetooth(path)` / `text2data_usb(path)` → `(7, N)` arrays
- `eeg_quality_check(eeg_data, fs=250)` → per-segment quality metrics
- `clean_eeg_data(eeg_data, metrics, thresh, seg_len, bad_ch_ratio)` → cleaned data
- `find_rejected_intervals(mask)`, `visualize_cleaning_comparison(...)`,
  `analyze_alpha_and_plot_eeg_group(data, fs, show_channel)`

Tutorial notebooks 1-6 cover: TXT parsing (BT/USB), real-time streaming
(BT/USB), offline preprocessing/QC, and an eyes-open/closed Alpha-blocking +
ERD study. The bundled `scripts/neuradock_toolkit.py` mirrors this pipeline and
is tested against the public sample files.
