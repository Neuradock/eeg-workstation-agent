# Adaptive Vehicle HMI Demo

This demo shows a vehicle HMI that adapts from the realtime NeuraDock API shape.
The browser polls:

```text
GET /api/status
```

every second.

Rules implemented in `app.js`:

- `quality.status != "pass"`: hold the standard HMI and show
  `Signal quality warning`.
- `quality.status == "pass"` and `current.visual_load_index > 70`: simplify the
  HMI, emphasize driving-priority controls, reduce ADAS and route symbols, hide
  media/climate/energy panels, and show
  `High visual load, simplified view enabled`.
- `quality.status == "pass"` and `current.visual_load_index < 35`: expand the
  HMI with richer route, ADAS, energy, and context symbols.
- Otherwise: use the standard HMI.

If `current.visual_cognitive_symbol` is present, the UI uses it. If it is not
present, the UI derives the symbol from `quality.status` and
`current.visual_load_index`, so it remains compatible with the existing
NeuraDock online API.

## Run The Self-Contained Demo

```powershell
cd examples\adaptive_ui_demo
py -3 server.py --port 8081
```

Open:

```text
http://127.0.0.1:8081
```

## Run With A Live NeuraDock API

Start the NeuraDock API in another terminal with live hardware:

```powershell
.\.venv\Scripts\neuradock-agent.exe online --ip 192.168.4.1 --port 9600
```

Then proxy the live status endpoint through the demo server:

```powershell
cd examples\adaptive_ui_demo
py -3 server.py --port 8081 --api-base http://127.0.0.1:8765
```

Open:

```text
http://127.0.0.1:8081
```
