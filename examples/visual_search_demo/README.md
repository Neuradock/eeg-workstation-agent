# Visual Search Load Demo

This browser demo shows how a product can consume the NeuraDock visual
cognitive-load API and adapt a visual search task in real time.

The demo reads:

```text
GET http://127.0.0.1:8765/api/status
GET http://127.0.0.1:8765/api/next
```

It uses the quality-gated Visual Load Index to adjust visual density:

- Low load: harder search grid
- Moderate load: working-zone search grid
- High load: simplified grid
- Low-quality signal: hold adaptation and show a quality warning

## Run With No Hardware

Terminal 1:

```powershell
cd path\to\neuradock-agent
.\.venv\Scripts\neuradock-agent.exe serve --port 8765
```

Terminal 2:

```powershell
cd path\to\neuradock-agent\examples\visual_search_demo
py -3 -m http.server 8080
```

Open:

```text
http://127.0.0.1:8080
```

## Run With Live NeuraDock Hardware

Terminal 1:

```powershell
cd path\to\neuradock-agent
.\.venv\Scripts\neuradock-agent.exe online --ip 192.168.4.1 --port 9600
```

Terminal 2:

```powershell
cd path\to\neuradock-agent\examples\visual_search_demo
py -3 -m http.server 8080
```

Open:

```text
http://127.0.0.1:8080
```

The browser app only uses the local NeuraDock Agent API. It does not parse raw
EEG and does not send EEG data to a remote service.
