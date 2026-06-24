# External EEG Examples

Human EEG files are maintained in the public NeuraDock data repository rather
than committed to this software release.

Download and verify the small examples used by `README.md` and `COMMANDS.md`:

```powershell
python scripts\download_example_data.py
```

The script creates:

```text
data_examples/
|-- alpha/
|   `-- open_closed_eye2.txt
`-- rest_task/
    |-- rest_S01_1.txt
    `-- task_S01_1.txt
```

Read `DATASET.md` and the upstream dataset README before interpretation.
