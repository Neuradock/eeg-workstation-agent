# Current Implementation Map

Use this map when explaining current code behavior. Do not claim functionality
that is absent from these reviewed modules.

- `profile.py`: formal hardware profile, channel order, units, packet shape, and
  quality thresholds.
- `io.py`: strict USB/Bluetooth text parsing, restricted numeric NPY trial-batch
  loading, trial selection, and TCP packet field parsing.
- `quality_tools.py`: preprocessing QC, segment rejection, spatial checks, and
  acquisition-context heuristics.
- `alpha_dynamics.py`: posterior Alpha feature extraction, strong/weak Alpha
  state detection, suppression-from-baseline scoring, peak frequency, and
  left/right posterior asymmetry.
- `analysis.py`: fixed preprocessing, Welch PSD, band power, and the simpler
  quality bundle used by PSD and Device Doctor.
- `cognitive_load.py`: Visual Cognitive Load features, trial-boundary-aware
  windows, normalization, within-input scoring, labels, and warnings.
- `workflows.py`: reviewed workflow entry points and artifact generation.
- `online.py`: rolling online preprocessing, visual-load API, demo stream
  endpoint, and HTML dashboard server.
- `realtime.py`: TCP capture and Device Doctor.
- `agent.py`: constrained intent routing and workflow execution.
- `llm.py`: OpenAI-compatible planning limited to reviewed intents.
- `llm_interpretation.py`: allowlisted privacy-bounded result summaries and LLM
  explanations.

The Agent does not execute LLM-generated Python. A new numerical method requires
reviewed Python code, tests, result schema, and documentation.
