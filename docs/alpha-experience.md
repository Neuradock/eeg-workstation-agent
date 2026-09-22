# Alpha Experience

Alpha Experience is a local browser interface for exploring posterior 8–13 Hz
Alpha dynamics. It makes the input mode, signal-quality gate, and Alpha relative
to a rolling baseline visible together. It is research and teaching software,
not a validated relaxation, attention, emotion, or health score.

## Choose the input deliberately

| Input | Start the Agent | What the display represents |
|---|---|---|
| Synthetic Demo | `neuradock-agent serve --host 127.0.0.1 --port 8765` | Generated software-test signals; not a person's EEG |
| Recorded file | Add `--demo-file "path/to/recording.txt"` to `serve` | Samples from the specified file; not your current brain activity |
| Live Device | `neuradock-agent online --ip HOST --port PORT` | Incoming NeuraDock samples, only after an actual device connection |

Replace `HOST` and `PORT` with the confirmed bridge endpoint. They are
placeholders, not values to copy unchanged. The dashboard's connection action
provides setup instructions; it does not scan the network or silently open a
hardware connection. A disconnected or waiting live source is not a valid live
EEG measurement.

Run commands from the repository root after installation and open the local URL
printed by the server. The default dashboard URL is `http://127.0.0.1:8765`.
No LLM configuration or API key is required for these modes. Keep the service
bound to localhost for individual classroom use.

An explicitly selected file is not necessarily human EEG. Establish its origin,
channel order, 250 Hz sample rate, microvolt units, and permission to use it.
Never infer these facts from an attractive plot or the filename alone. Keep raw
participant recordings out of public Git repositories.

## Read the Alpha feature correctly

The signal pipeline estimates integrated posterior Alpha power from completed
windows. Its reference is a **rolling baseline** built from quality-accepted
window history; it can change as the session progresses. This is different from
a fixed calibration value frozen before a training block.

The displayed multiplier is `current.posterior_alpha_relative`: the current
posterior Alpha power relative to the rolling log-median reference. `1.0×`
means the reference level; it is a unitless ratio, not a percentage of relaxation.
The reference needs at least three accepted, finite, nonzero-power windows and
uses up to 600 accepted window values, including the current accepted window.
If feedback is unavailable, the ratio is withheld rather than filled with zero.

“Relative to baseline” compares the current Alpha feature with this reference.
It does not mean the fraction of all EEG power in the Alpha band, unless a
separate metric explicitly defines that denominator. Nor does a higher value
mean a known amount of relaxation or successful training. Do not compare the
display across people or sessions without a separately validated protocol.

Keep the same eye state, posture, and environment when exploring changes.
Opening or closing the eyes is itself a change in the experiment. The default
four-second analysis window also means the display summarizes recent history;
it is not an instantaneous mental-state reading.

## Quality and unavailable feedback

Inspect quality before interpreting any feature. During startup, poor signal,
connection loss, or stale data, feedback should be unavailable or neutral, not
presented as a low relaxation score. A previously valid value is historical
evidence, not a substitute for current samples.

Check electrode contact, headset placement, movement, muscle tension, and nearby
electrical sources when the gate reports a problem. Do not lower quality
requirements just to produce a preferred result. Device-specific screening
thresholds remain heuristics rather than clinical acceptance criteria.

## Pause the display versus stop acquisition

Pausing freezes the historical feature plot and hides current feedback. Source
and quality status continue to be checked. In live mode, it does **not** stop
the Agent's background TCP reader or any separate acquisition application.
Resume to view current state; do not interpret the paused screen as a fresh
measurement. Synthetic/file playback is no longer advanced by this paused page;
another open client can still advance a shared replay server.

To end this Agent's session, press `Ctrl+C` in the terminal running its server.
Use the acquisition application's own stop controls for any separate capture.
Participation is voluntary; stop the experience if uncomfortable.

## What a classroom demonstration establishes

A synthetic run can check the interface and processing behavior. File replay can
show how the software handles an authorized recording. Neither verifies live
hardware, end-to-end latency, or a neurofeedback benefit. Before a live class,
check the actual device connection, sample delivery, timing, quality, and stop
procedure on the intended setup.

A useful final report identifies the input mode, feature definition, rolling
baseline, quality interruptions, and interpretation limits. An Alpha increase
or a subjective feeling of relaxation is not required for a successful exercise.
