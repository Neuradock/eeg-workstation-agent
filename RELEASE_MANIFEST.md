# Release Manifest

Release: `2026.6.24`

## Included

- `.github/workflows/`: cross-platform continuous integration
- `src/neuradock_agent/`: Agent, EEG workflows, realtime API, and dashboard
- `examples/`: visual search, adaptive HMI, cognitive load game, and Python API
- `tests/`: deterministic unit and integration tests
- `configs/`: public NeuraDock hardware profile
- `context/`: reviewed Agent context and scientific boundaries
- `docs/`: architecture, protocol, release, and scientific documentation
- `scripts/`: verified public-data downloader
- `data_examples/README.md`: external data instructions only
- Root project, governance, security, citation, and release documents

## Excluded

- Human EEG recordings
- Portable executables and binary build output
- Python environments, caches, bytecode, and package metadata
- Generated reports, figures, and experiment runs
- LLM credentials and local provider configuration
- Internal papers, validation folders, and unpublished recordings

## Release Verification

Completed on 2026-06-24:

- 44 automated tests passed with Python `unittest`
- Python source compilation passed
- Wheel build and clean package installation passed
- Package version reported `2026.6.24`
- Synthetic no-hardware analysis passed
- Realtime API health and synthetic replay endpoints passed
- Three public EEG examples downloaded and passed SHA256 verification
- Downloaded `open_closed_eye2.txt` completed Alpha Dynamics analysis
- Sensitive-path, private-key, token-pattern, cache, binary, and old portable
  scans found no release-blocking files

`SHA256SUMS.txt` contains checksums for the published source tree.
