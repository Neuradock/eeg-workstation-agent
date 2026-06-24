# Cognitive Load Game Demo

This lightweight browser game demonstrates a realtime API + application loop.
The browser polls:

```text
GET /api/status
```

every second.

Adaptation rules:

- Low load: increase target count and speed, add distractors.
- Moderate load: keep the current balanced difficulty.
- High load: lower speed, reduce targets and distractors, enlarge targets.
- Quality warning: pause adaptation and show the signal data without changing
  the current difficulty.

If `current.visual_cognitive_symbol` is present, the game uses it. Otherwise it
derives the symbol from `quality.status` and `current.visual_load_index`.

## Run The Self-Contained Demo

```powershell
cd examples\cognitive_load_game_demo
py -3 server.py --port 8082
```

Open:

```text
http://127.0.0.1:8082
```

## Run With A Live NeuraDock API

Start the NeuraDock API in another terminal:

```powershell
.\.venv\Scripts\neuradock-agent.exe online --ip 192.168.4.1 --port 9600
```

Then proxy the live status endpoint through the game server:

```powershell
cd examples\cognitive_load_game_demo
py -3 server.py --port 8082 --api-base http://127.0.0.1:8765
```
