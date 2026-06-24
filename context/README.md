# NeuraDock Context Pack

This directory contains the reviewed phase-one knowledge supplied to connected
LLMs.

- Context version: `2026.6.24`
- Intended users: EEG researchers and engineers
- Explanation style: plain language, technically accurate
- Canonical system prompt: `neuradock-system-prompt.md`

The Agent loads a small core for workflow planning and adds workflow-specific
documents and reviewed cases for result interpretation. This is deterministic
file selection, not vector retrieval.

## Source Authority

When sources disagree, use this order:

1. Current reviewed context pack and current Agent code.
2. Current NeuraDock hardware profile and workflow result schema.
3. Current NeuraDock documentation.
4. Older examples and sample-data notes, which may contain legacy mappings.

Raw EEG and dense per-sample arrays are not included in the LLM context.
