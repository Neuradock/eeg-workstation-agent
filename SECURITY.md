# Security Policy

## Supported Version

Security fixes are provided for the latest `0.1.x` release.

## Reporting

Do not open a public issue for credential exposure, unsafe code execution,
path traversal, or participant-data leakage. Report it privately to the
NeuraDock maintainers.

## Data Safety

- Raw EEG stays local by default.
- The Agent does not execute generated Python.
- Output paths are created under the requested run directory.
- API keys entered in LLM mode are stored in the current user's private
  configuration directory. They must never be placed in repository files,
  logs, examples, issues, or commits.
- Public bug reports must use synthetic or explicitly shareable recordings.
