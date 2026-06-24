"""Narrow scipy.signal imports for source runs and PyInstaller bundles."""

from scipy.signal._filter_design import butter, iirnotch
from scipy.signal._signaltools import filtfilt, hilbert, sosfiltfilt
from scipy.signal._spectral_py import spectrogram, welch

