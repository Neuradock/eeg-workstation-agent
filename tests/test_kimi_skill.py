"""Release checks for the separately distributed Kimi skill toolkit."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integrations/kimi/skills/neuradock-eeg/scripts/neuradock_toolkit.py"
spec = importlib.util.spec_from_file_location("kimi_toolkit", SCRIPT)
toolkit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toolkit)


def packet(groups=1, bad_group=None, value=None):
    parts = ["1.0", "target"]
    for g in range(groups):
        values = [str(g * 10 + c) for c in range(7)]
        if g == bad_group:
            values[3] = value
        parts.extend(values + ["0"])
    return ",".join(parts)


@pytest.mark.parametrize("bad", ["broken", "nan", "inf", ""])
def test_bluetooth_packet_is_atomic(tmp_path, bad):
    file = tmp_path / "input.txt"
    file.write_text(packet(5, 3, bad) + "\n" + packet(5), encoding="utf-8")
    data, meta = toolkit.load_txt(file)
    assert data.shape == (7, 5)
    assert meta["malformed_rows"] == 1
    assert len(meta["markers"]) == len(meta["timestamps"]) == 5
    np.testing.assert_allclose(data[:, 2], np.arange(7) + 20)
    np.testing.assert_allclose(meta["timestamps"], 1 + np.arange(5) / 250)


def test_usb_reserved_column_is_not_an_eeg_channel(tmp_path):
    file = tmp_path / "usb.txt"
    file.write_text("HEADER_DEF,T,P,C\n" + packet() + "\nshort,row\n", encoding="utf-8")
    data, meta = toolkit.load_txt(file)
    np.testing.assert_allclose(data[:, 0], np.arange(7))
    assert meta["format"] == "usb" and meta["malformed_rows"] == 1


def alpha_signal(seconds=8):
    t = np.arange(250 * seconds) / 250
    return np.tile(10 * np.sin(2 * np.pi * 10 * t), (7, 1))


def test_flatline_is_not_quality_pass():
    quality = toolkit.qc_report(np.zeros((7, 1000)))
    assert quality["status"] == "warning"
    assert quality["min_posterior_neighbor_correlation"] is None
    json.dumps(quality, allow_nan=False)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_qc_rejects_nonfinite_arrays(bad):
    data = alpha_signal()
    data[0, 0] = bad
    with pytest.raises(ValueError, match="finite"):
        toolkit.qc_report(data)


def test_alpha_window_gate_checks_frequency_contamination():
    data = alpha_signal()
    t = np.arange(data.shape[1]) / 250
    dirty = data + 30 * np.sin(2 * np.pi * 30 * t)
    result = toolkit.alpha_dynamics(toolkit.preprocess(dirty), quality_data=dirty)
    assert result["valid_window_count"] == 0
    assert result["excluded_window_count"] == 5


def test_clean_alpha_peak():
    raw = alpha_signal()
    result = toolkit.alpha_dynamics(toolkit.preprocess(raw), quality_data=raw)
    assert result["valid_window_count"] == 5
    assert all(abs(w["alpha_peak_hz"] - 10) <= 0.25 for w in result["windows"])


def test_npy_requires_trial_selection_and_counts_samples(tmp_path):
    file = tmp_path / "trials.npy"
    np.save(file, np.stack([alpha_signal(), alpha_signal()]))
    with pytest.raises(ValueError, match="--trial"):
        toolkit._load(SimpleNamespace(file=str(file), trial=None))
    data, meta = toolkit._load(SimpleNamespace(file=str(file), trial=2))
    assert data.shape == (7, 2000)
    assert meta["n_samples"] == 2000 and meta["selected_trial"] == 2


def test_cli_gates_bands_before_notch(tmp_path):
    raw = alpha_signal()
    raw += 30 * np.sin(2 * np.pi * 50 * np.arange(raw.shape[1]) / 250)
    file, out = tmp_path / "dirty.npy", tmp_path / "result.json"
    np.save(file, raw[None, ...])
    result = subprocess.run([sys.executable, str(SCRIPT), "bands", str(file),
                             "--json", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text())
    assert data["quality_input"] == "unfiltered_samples"
    assert data["quality"]["issue_counts"]["line_noise"] > 0
    assert data["status"] == "warning" and "posterior_alpha_peak_hz" not in data


def test_cli_does_not_filter_across_malformed_packet_gaps(tmp_path):
    raw = alpha_signal()
    rows = [",".join([str(i / 250), "0"] + [str(x) for x in raw[:, i]] + ["0"])
            for i in range(raw.shape[1])]
    rows.insert(500, "malformed,row")
    file, out = tmp_path / "gapped.txt", tmp_path / "result.json"
    file.write_text("\n".join(rows), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "alpha", str(file),
                             "--json", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(out.read_text())
    assert data["recording"]["malformed_rows"] == 1
    assert data["status"] == "warning" and "windows" not in data
