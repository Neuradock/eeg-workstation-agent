# NeuraDock Data Protocol Used by v0.1

The parser accepts the current public NeuraDock export structures.

## Bluetooth Text

Each line contains two leading fields followed by five groups of eight fields.
Each group contains seven EEG values and one reserved/separator value.

```text
timestamp, marker, 7 EEG, reserved, 7 EEG, reserved, ... x5
```

## USB Text

Each line contains two leading fields followed by one group:

```text
timestamp, marker, 7 EEG, reserved
```

Both formats are expanded to a `7 x samples` array in the formal zero-based
order:

```text
0=CP5, 1=CP6, 2=PO3, 3=PO4, 4=O1, 5=Oz, 6=O2
```

Parsed EEG amplitudes are represented in microvolts (`uV`).
The absolute outlier threshold used by the quality workflow is 100 microvolts.
