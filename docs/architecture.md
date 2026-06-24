# Architecture

NeuraDock Visual Cognitive Load Agent `2026.6.24` separates deterministic EEG
computation from language behavior and browser presentation.

## Layers

1. **Hardware profile**: one versioned source of truth for channel order,
   sampling rate, packet structure, and quality thresholds.
2. **I/O**: strict USB/Bluetooth text parsing and TCP packet parsing.
3. **Preprocessing and quality gate**: deterministic filtering, segment QC,
   spatial QC, acquisition-context heuristics, and retained clean EEG.
4. **Alpha dynamics core**: posterior Alpha strong/weak state detection,
   suppression from baseline, peak frequency, and left/right posterior
   asymmetry.
5. **Visual cognitive-load workflows**: offline single-recording analysis,
   Rest/Task comparison, and online rolling visual-load API.
6. **Workflow engine**: validates inputs and writes reproducible run artifacts.
7. **HTML dashboard**: local browser UI backed by the online API.
8. **Context pack**: supplies versioned hardware, workflow, scientific-boundary,
   result-field, implementation, and reviewed-case knowledge to connected LLMs.
9. **Agent layer**: maps user intent to a supported workflow and explains the
   structured result.

In LLM mode, workflow planning and result explanation are separate calls. The
scientific core remains local and deterministic. The explanation call receives
only an allowlisted metric summary; raw EEG and dense numerical arrays are
never included. Each call records the context version, selected files, and
context hash in `agent_trace.json`.

The Agent cannot create new formulas or execute generated code. Adding a new
analysis requires a reviewed Python workflow, tests, result schema, and
documentation.

## Run Artifacts

User-facing analysis workflows write machine-readable results, readable
reports, and deterministic figures. Quality runs additionally write retained
clean EEG:

- `results.json`: machine-readable result
- `report.md`: human-readable interpretation
- `figures/`: deterministic visual outputs
- `clean_eeg_data.npz`: quality workflow retained signal
- `llm_interpretation.md`: optional bounded language-model explanation
- `agent_trace.json`: planner and interpretation audit metadata

Alpha Dynamics runs write three figures:

- `alpha_time_domain.png`
- `alpha_frequency_domain.png`
- `alpha_time_frequency.png`

Online dashboard runs do not need a run directory; they expose rolling JSON
through `/api/analyze` and `/api/demo/next`.

## Hardware Binding

This release intentionally targets NeuraDock only. The fixed hardware profile
is a product feature: quality messages can refer to physical posterior
electrodes and known packet behavior instead of using generic channel names.
