#!/usr/bin/env python3
"""NeuraDock EEG toolkit: parse recordings, run signal QC, band power, and
posterior Alpha dynamics for the NeuraDock EEG Workstation (7ch, 250 Hz).

Canonical device profile (public profile v2):
- Sample rate: 250 Hz. Unit after parsing: microvolts (uV).
- Zero-based channel order: 0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2.
- Text/TCP lines begin with `timestamp, marker`, then EEG packet groups.
  USB: 1 group of 7 EEG + 1 reserved field (>=10 fields per line).
  Bluetooth: 5 groups of 7 EEG + 1 reserved (>=42 fields); expand each line
  into five chronological samples.

Usage:
  python neuradock_toolkit.py parse   <file.txt> [--format usb|bluetooth|auto]
  python neuradock_toolkit.py qc      <file.txt> [--format ...] [--json out.json]
  python neuradock_toolkit.py bands   <file.txt> [--format ...]
  python neuradock_toolkit.py alpha   <file.txt> [--format ...] [--json out.json]

All commands print a summary to stdout; --json writes machine-readable results.
Raw recordings are never modified.
"""
import argparse
import json
import sys

import numpy as np

FS = 250
CHANNELS = ["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"]  # zero-based order
POSTERIOR = ["PO3", "PO4", "O1", "Oz", "O2"]
LEFT = ["PO3", "O1"]
RIGHT = ["PO4", "O2"]

# QC thresholds (device-workflow heuristics, not universal EEG standards)
QC_THRESH = {
    "line_noise_power_49_51hz": 10.0,
    "emg_power_20_40hz": 20.0,
    "abs_amplitude_uv": 100.0,
    "outliers_per_second": 2,
    "bad_channel_segment_ratio": 0.40,
    "min_neighbor_correlation": 0.15,
}

BANDS = {"Delta": (1, 4), "Theta": (4, 8), "Alpha": (8, 13),
         "Beta": (13, 30), "Gamma": (30, 45)}


# ---------------------------------------------------------------- parsing
def _parse_timestamp(raw):
    """Numeric timestamp, or clock string HH:MM:SS.mmm -> seconds; else NaN."""
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        h, m, s = raw.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return float("nan")


def detect_format(path):
    """Detect usb vs bluetooth from field counts of the first data lines."""
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("HEADER"):
                continue
            parts = line.strip().split(",")
            n = len(parts)
            if n >= 42:
                return "bluetooth"
            if n >= 10:
                return "usb"
    raise ValueError("No parseable lines found; not a NeuraDock text recording?")


def load_txt(path, fmt="auto"):
    """Parse a NeuraDock text recording.

    Returns (data, meta): data is (7, N) float array in CHANNELS order;
    meta holds markers, timestamps, malformed-row count, and format info.
    """
    if fmt == "auto":
        fmt = detect_format(path)
    if fmt not in ("usb", "bluetooth"):
        raise ValueError("Format must be auto, usb, or bluetooth.")
    rows, markers, tstamps, malformed = [], [], [], 0
    groups_per_line = 5 if fmt == "bluetooth" else 1
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("HEADER"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2 + groups_per_line * 8:
                malformed += 1
                continue
            ts = _parse_timestamp(parts[0])
            marker = parts[1]
            try:
                # Validate the whole packet before appending any sample.
                packet = []
                for g in range(groups_per_line):
                    base = 2 + g * 8
                    values = [float(v) for v in parts[base:base + 7]]
                    if not np.isfinite(values).all():
                        raise ValueError("Non-finite EEG sample")
                    packet.append(values)
            except ValueError:
                malformed += 1
                continue
            rows.extend(packet)
            markers.extend([marker] * groups_per_line)
            tstamps.extend(ts + g / FS if np.isfinite(ts) else np.nan
                           for g in range(groups_per_line))
    if not rows:
        raise ValueError("Parsed zero samples; check file format.")
    data = np.asarray(rows, dtype=float).T  # (7, N)
    meta = {
        "format": fmt, "n_samples": data.shape[1],
        "duration_s": round(data.shape[1] / FS, 2),
        "malformed_rows": malformed,
        "markers": markers, "timestamps": np.asarray(tstamps),
    }
    return data, meta


def load_npy_trials(path):
    """Load a trial batch shaped (trials, 7, samples) or (trials, samples, 7)."""
    arr = np.load(path, allow_pickle=False)
    if arr.ndim != 3:
        raise ValueError("Expected 3-D trial batch (trials, 7, samples).")
    if arr.shape[1] == 7:
        return arr
    if arr.shape[2] == 7:
        return np.transpose(arr, (0, 2, 1))
    raise ValueError("Neither axis has 7 channels.")


# --------------------------------------------------------- preprocessing
def preprocess(data, fs=FS):
    """Offline descriptive pipeline: median-center, 1-45 Hz bandpass,
    50 Hz notch. Returns filtered (7, N) array."""
    from scipy import signal
    x = data - np.median(data, axis=1, keepdims=True)
    b, a = signal.butter(4, [1.0, 45.0], btype="bandpass", fs=fs)
    x = signal.filtfilt(b, a, x, axis=1)
    b2, a2 = signal.iirnotch(50.0, 30.0, fs=fs)
    return signal.filtfilt(b2, a2, x, axis=1)


def welch_psd(x, fs=FS):
    from scipy import signal
    freqs, psd = signal.welch(x, fs=fs, nperseg=min(4 * fs, x.shape[-1]), axis=-1)
    return freqs, psd


def band_power(freqs, psd, lo, hi):
    idx = (freqs >= lo) & (freqs < hi)
    integrate = getattr(np, "trapezoid", None)
    if integrate is None:
        integrate = np.trapz
    return integrate(psd[..., idx], freqs[idx], axis=-1) if idx.any() else 0.0


# ------------------------------------------------------------------- QC
def qc_report(data, fs=FS, seg_len=250):
    """One-second-segment QC. For acquisition QC pass unfiltered data. Returns
    retention rate, bad-channel candidates, and issue counts."""
    data = np.asarray(data, dtype=float)
    if data.ndim != 2 or data.shape[0] != 7 or not np.isfinite(data).all():
        raise ValueError("QC requires finite data shaped (7, N).")
    n_ch, n = data.shape
    n_seg = n // seg_len
    if n_seg == 0:
        raise ValueError("Recording shorter than one second.")
    seg = data[:, :n_seg * seg_len].reshape(n_ch, n_seg, seg_len)
    counts = {"line_noise": 0, "emg_or_high_frequency": 0,
              "extreme_amplitude": 0}
    bad = np.zeros((n_ch, n_seg), dtype=bool)
    for c in range(n_ch):
        for s in range(n_seg):
            x = seg[c, s]
            freqs, psd = welch_psd(x, fs)
            line_ok = band_power(freqs, psd, 49, 51) <= QC_THRESH["line_noise_power_49_51hz"]
            emg_ok = band_power(freqs, psd, 20, 40) <= QC_THRESH["emg_power_20_40hz"]
            amp_ok = np.sum(np.abs(x) >= QC_THRESH["abs_amplitude_uv"]) <= QC_THRESH["outliers_per_second"]
            if not line_ok:
                counts["line_noise"] += 1
            if not emg_ok:
                counts["emg_or_high_frequency"] += 1
            if not amp_ok:
                counts["extreme_amplitude"] += 1
            bad[c, s] = not (line_ok and emg_ok and amp_ok)
    keep = ~bad.any(axis=0)
    bad_channels = [CHANNELS[c] for c in range(n_ch)
                    if bad[c].mean() > QC_THRESH["bad_channel_segment_ratio"]]
    # sparse posterior neighbor consistency
    post_idx = [CHANNELS.index(ch) for ch in POSTERIOR]
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.corrcoef(data[post_idx])
    off = corr[np.triu_indices(len(post_idx), 1)]
    min_corr = float(np.min(off)) if off.size and np.isfinite(off).all() else None
    spatial_ok = min_corr is not None and min_corr >= QC_THRESH["min_neighbor_correlation"]
    return {
        "status": "pass" if (keep.mean() >= 0.6 and not bad_channels and spatial_ok) else "warning",
        "retention_rate": round(float(keep.mean()), 4),
        "rejected_segment_count": int((~keep).sum()),
        "bad_channel_candidates": bad_channels,
        "issue_counts": counts,
        "min_posterior_neighbor_correlation": round(min_corr, 3) if min_corr is not None else None,
        "spatial_consistency_ok": spatial_ok,
        "thresholds": QC_THRESH, "segment_len_samples": seg_len,
    }


def clean(data, report_keep_mask=None, fs=FS, seg_len=250):
    """Return quality-approved samples only (concatenated clean segments)."""
    n_ch, n = data.shape
    n_seg = n // seg_len
    rep = qc_report(data, fs, seg_len)
    # recompute keep mask cheaply via retained fraction is not exact; instead
    # rerun the segment logic but expose mask:
    seg = data[:, :n_seg * seg_len].reshape(n_ch, n_seg, seg_len)
    bad = np.zeros((n_ch, n_seg), dtype=bool)
    for c in range(n_ch):
        for s in range(n_seg):
            x = seg[c, s]
            freqs, psd = welch_psd(x, fs)
            ok = (band_power(freqs, psd, 49, 51) <= QC_THRESH["line_noise_power_49_51hz"]
                  and band_power(freqs, psd, 20, 40) <= QC_THRESH["emg_power_20_40hz"]
                  and np.sum(np.abs(x) >= 100.0) <= 2)
            bad[c, s] = not ok
    keep = ~bad.any(axis=0)
    return seg[:, keep, :].reshape(n_ch, -1), keep, rep


# --------------------------------------------------------------- features
def band_power_table(data, fs=FS):
    """Absolute and relative band power per channel plus posterior Alpha peak."""
    freqs, psd = welch_psd(data, fs)
    total = band_power(freqs, psd, 1, 45)
    out = {}
    for i, ch in enumerate(CHANNELS):
        abs_pw = {b: round(float(band_power(freqs, psd[i], *rng)), 4)
                  for b, rng in BANDS.items()}
        rel_pw = {b: round(abs_pw[b] / float(total[i]), 4) if total[i] else None
                  for b in BANDS}
        out[ch] = {"absolute": abs_pw, "relative": rel_pw}
    post_idx = [CHANNELS.index(c) for c in POSTERIOR]
    a_idx = (freqs >= 8) & (freqs <= 13)
    peak = float(freqs[a_idx][np.argmax(psd[post_idx][:, a_idx].mean(axis=0))])
    return {"bands_hz": {b: list(r) for b, r in BANDS.items()},
            "channels": out, "posterior_alpha_peak_hz": round(peak, 2)}


def alpha_dynamics(data, fs=FS, win=4, step=1, clean_frac=0.8, quality_data=None):
    """Rolling posterior Alpha dynamics. Labels (weak/baseline/strong) are
    within-recording tertiles — relative, never absolute cognitive load."""
    quality_data = data if quality_data is None else quality_data
    if quality_data.shape != data.shape:
        raise ValueError("Feature and quality data must have the same shape.")
    post_idx = [CHANNELS.index(c) for c in POSTERIOR]
    li = [CHANNELS.index(c) for c in LEFT]
    ri = [CHANNELS.index(c) for c in RIGHT]
    w, s = int(win * fs), int(step * fs)
    windows = []
    for start in range(0, data.shape[1] - w + 1, s):
        seg = data[:, start:start + w]
        quality = qc_report(quality_data[:, start:start + w], fs)
        if quality["status"] != "pass" or quality["retention_rate"] < clean_frac:
            continue
        freqs, psd = welch_psd(seg, fs)
        a_pow = band_power(freqs, psd, 8, 13)
        log_a = float(np.log10(np.mean(a_pow[post_idx]) + 1e-12))
        a_idx = (freqs >= 8) & (freqs <= 13)
        peak = float(freqs[a_idx][np.argmax(psd[post_idx][:, a_idx].mean(axis=0))])
        l_pow = float(np.mean(a_pow[li])); r_pow = float(np.mean(a_pow[ri]))
        asym = (r_pow - l_pow) / (r_pow + l_pow + 1e-12)
        windows.append({"t_start_s": round(start / fs, 1),
                        "posterior_log_alpha_power": round(log_a, 4),
                        "alpha_peak_hz": round(peak, 2),
                        "alpha_asymmetry_right_minus_left": round(asym, 4)})
    if not windows:
        return {"status": "warning", "valid_window_count": 0,
                "excluded_window_count": len(range(0, data.shape[1] - w + 1, s)),
                "message": "No window passed the clean-sample requirement."}
    vals = np.array([x["posterior_log_alpha_power"] for x in windows])
    t1, t2 = np.percentile(vals, [33.3, 66.7])
    base = float(np.median(vals))
    for x in windows:
        v = x["posterior_log_alpha_power"]
        x["alpha_state"] = "weak" if v < t1 else ("strong" if v > t2 else "baseline")
        x["alpha_suppression_from_baseline"] = round(base - v, 4)
    states = [x["alpha_state"] for x in windows]
    return {
        "status": "pass",
        "valid_window_count": len(windows),
        "excluded_window_count": len(range(0, data.shape[1] - w + 1, s)) - len(windows),
        "window_s": win, "step_s": step,
        "state_counts": {st: states.count(st) for st in ("weak", "baseline", "strong")},
        "baseline_median_log_alpha": round(base, 4),
        "strongest_alpha_window": max(windows, key=lambda x: x["posterior_log_alpha_power"]),
        "weakest_alpha_window": min(windows, key=lambda x: x["posterior_log_alpha_power"]),
        "windows": windows,
        "note": "States are within-recording relative tertiles; weak Alpha is an "
                "Alpha-suppression observation, not proof of cognitive load.",
    }


# ------------------------------------------------------------------- CLI
def _load(args):
    if args.file.endswith(".npy"):
        arr = load_npy_trials(args.file)
        trial = args.trial
        if trial is None and arr.shape[0] != 1:
            raise ValueError("For multiple NPY trials, select one with --trial (one-based).")
        trial = 1 if trial is None else trial
        if not 1 <= trial <= arr.shape[0]:
            raise ValueError("Selected trial is out of range.")
        return arr[trial - 1], {"format": "npy-trials", "n_trials": arr.shape[0],
                        "selected_trial": trial,
                        "n_samples": arr.shape[2], "malformed_rows": 0,
                        "duration_s": round(arr.shape[2] / FS, 2)}
    data, meta = load_txt(args.file, args.format)
    return data, meta


def main():
    p = argparse.ArgumentParser(description="NeuraDock EEG toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("parse", "qc", "bands", "alpha"):
        sp = sub.add_parser(name)
        sp.add_argument("file")
        sp.add_argument("--format", default="auto",
                        choices=["auto", "usb", "bluetooth"])
        sp.add_argument("--json", default=None)
        sp.add_argument("--trial", type=int, help="One-based NPY trial selection")
    args = p.parse_args()

    data, meta = _load(args)
    result = {"recording": {k: v for k, v in meta.items()
                            if k not in ("markers", "timestamps")},
              "channels": CHANNELS, "sample_rate_hz": FS, "unit": "uV"}

    if args.cmd == "parse":
        result["shape_channels_x_samples"] = list(data.shape)
        print(json.dumps({k: v for k, v in result.items()}, indent=2))
    else:
        # Preserve electrical-noise evidence before bandpass/notch suppression.
        quality = qc_report(data)
        result["quality"] = quality
        result["quality_input"] = "unfiltered_samples"
        if args.cmd == "qc":
            result.update(quality)
        elif meta["malformed_rows"]:
            result.update(status="warning", message="Malformed rows create gaps; resolve them before feature analysis.")
        elif args.cmd == "bands":
            if quality["status"] != "pass" or quality["rejected_segment_count"]:
                result.update(status="warning", message="Recording failed QC; select a continuous valid interval before band analysis.")
            else:
                result.update(band_power_table(preprocess(data)))
                result["status"] = "pass"
        elif args.cmd == "alpha":
            result.update(alpha_dynamics(preprocess(data), quality_data=data))
        text = json.dumps(result, indent=2, allow_nan=False)
        print(text[:4000] + ("\n... (truncated, see --json)" if len(text) > 4000 else ""))

    if args.json:
        result.pop("windows", None) if args.cmd != "alpha" else None
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2, allow_nan=False)
        print(f"wrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
