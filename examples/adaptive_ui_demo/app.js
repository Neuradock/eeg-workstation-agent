const state = {
  apiBase: "",
  pollTimer: null,
  history: [],
  quality: "waiting",
  load: null,
  hmiMode: "standard",
  tick: 0,
};

const adasItems = [
  { code: "LKA", label: "Lane", priority: "critical" },
  { code: "FCW", label: "Lead", priority: "critical" },
  { code: "NAV", label: "Turn", priority: "critical" },
  { code: "SPD", label: "Limit", priority: "standard" },
  { code: "BSM", label: "Blind", priority: "standard" },
  { code: "TLC", label: "Light", priority: "standard" },
  { code: "ECO", label: "Eco", priority: "complex" },
  { code: "POI", label: "Nearby", priority: "complex" },
  { code: "PDC", label: "Park", priority: "complex" },
];

const routeItems = [
  { title: "Airport Expressway", detail: "1.2 km, keep right", priority: "critical" },
  { title: "Speed limit", detail: "80 km/h for next 4.6 km", priority: "standard" },
  { title: "Traffic wave", detail: "Dense merge at exit 12", priority: "standard" },
  { title: "Fast charger", detail: "17 km, 6 stalls open", priority: "complex" },
  { title: "Weather", detail: "Light rain in 18 minutes", priority: "complex" },
];

const $ = (id) => document.getElementById(id);

const els = {
  app: $("app"),
  apiBase: $("apiBase"),
  connectBtn: $("connectBtn"),
  connectionState: $("connectionState"),
  messageBanner: $("messageBanner"),
  speedValue: $("speedValue"),
  rangeValue: $("rangeValue"),
  loadCard: $("loadCard"),
  loadValue: $("loadValue"),
  loadBand: $("loadBand"),
  qualityLamp: $("qualityLamp"),
  qualityStatus: $("qualityStatus"),
  qualityDetail: $("qualityDetail"),
  symbolState: $("symbolState"),
  symbolDetail: $("symbolDetail"),
  navInstruction: $("navInstruction"),
  navDistance: $("navDistance"),
  roadCanvas: $("roadCanvas"),
  laneStatus: $("laneStatus"),
  leadDistance: $("leadDistance"),
  modeState: $("modeState"),
  actionMode: $("actionMode"),
  adasSymbols: $("adasSymbols"),
  symbolCount: $("symbolCount"),
  routeList: $("routeList"),
  loadChart: $("loadChart"),
  handoverBtn: $("handoverBtn"),
  confirmBtn: $("confirmBtn"),
  muteBtn: $("muteBtn"),
  assistBtn: $("assistBtn"),
  clearLogBtn: $("clearLogBtn"),
  eventLog: $("eventLog"),
};

function logEvent(message) {
  const item = document.createElement("li");
  const time = new Date().toLocaleTimeString([], { hour12: false });
  item.textContent = `${time}  ${message}`;
  els.eventLog.prepend(item);
  while (els.eventLog.children.length > 12) {
    els.eventLog.lastElementChild.remove();
  }
}

function loadBand(value) {
  if (value == null || Number.isNaN(value)) return ["waiting", "Waiting"];
  if (value > 70) return ["high", "High"];
  if (value < 35) return ["low", "Low"];
  return ["moderate", "Moderate"];
}

function visualSymbol(load, qualityStatus, apiSymbol) {
  if (qualityStatus !== "pass") return "SIGNAL_QUALITY_WARNING";
  if (apiSymbol) return String(apiSymbol).toUpperCase();
  if (typeof load !== "number") return "WAITING";
  if (load > 70) return "VISUAL_LOAD_HIGH";
  if (load < 35) return "VISUAL_LOAD_LOW";
  return "VISUAL_LOAD_STABLE";
}

function hmiModeFromSymbol(symbol) {
  if (symbol === "VISUAL_LOAD_HIGH") return "simplified";
  if (symbol === "VISUAL_LOAD_LOW") return "expanded";
  return "standard";
}

function qualityDetail(result) {
  const quality = result?.quality || {};
  const channels = quality.bad_channel_candidates || [];
  if (channels.length) return `${channels.length} channels flagged: ${channels.join(", ")}`;
  if (quality.status === "pass") return "Signal accepted for adaptation";
  return "Signal quality warning";
}

function setConnection(kind, label) {
  els.connectionState.className = `status-pill is-${kind}`;
  els.connectionState.textContent = label;
}

function renderSymbols() {
  const visible = adasItems.filter((item) => {
    if (state.hmiMode === "simplified") return item.priority === "critical";
    if (state.hmiMode === "expanded") return true;
    return item.priority !== "complex";
  });
  els.adasSymbols.innerHTML = "";
  visible.forEach((item) => {
    const tile = document.createElement("div");
    tile.className = `symbol-tile is-${item.priority}`;
    tile.innerHTML = `<strong>${item.code}</strong><span>${item.label}</span>`;
    els.adasSymbols.appendChild(tile);
  });
  els.symbolCount.textContent = `${visible.length}`;
}

function renderRoute() {
  const visible = routeItems.filter((item) => {
    if (state.hmiMode === "simplified") return item.priority === "critical";
    if (state.hmiMode === "expanded") return true;
    return item.priority !== "complex";
  });
  els.routeList.innerHTML = "";
  visible.forEach((item) => {
    const row = document.createElement("li");
    row.className = `detail-item is-${item.priority}`;
    row.innerHTML = `<b>${item.title}</b><span>${item.detail}</span>`;
    els.routeList.appendChild(row);
  });
}

function applyMode(symbol, load, qualityStatus) {
  const qualityWarning = qualityStatus !== "pass";
  const nextMode = qualityWarning ? "standard" : hmiModeFromSymbol(symbol);
  state.hmiMode = nextMode;

  els.app.classList.toggle("is-simplified", nextMode === "simplified");
  els.app.classList.toggle("is-expanded", nextMode === "expanded");
  els.app.classList.toggle("has-quality-warning", qualityWarning);

  els.messageBanner.className = "message-banner";
  if (qualityWarning) {
    els.messageBanner.textContent = "Signal quality warning";
    els.messageBanner.classList.add("is-quality");
  } else if (nextMode === "simplified") {
    els.messageBanner.textContent = "High visual load, simplified view enabled";
    els.messageBanner.classList.add("is-high");
  } else {
    els.messageBanner.classList.add("is-hidden");
  }

  const modeLabel = nextMode === "simplified" ? "Simplified" : nextMode === "expanded" ? "Expanded" : "Standard";
  els.modeState.textContent = modeLabel;
  els.actionMode.textContent = nextMode === "simplified" ? "Priority" : nextMode === "expanded" ? "Rich" : "Normal";
  els.symbolState.textContent = symbol;
  els.symbolDetail.textContent =
    nextMode === "simplified"
      ? "driving priority"
      : nextMode === "expanded"
        ? "context enriched"
        : qualityWarning
          ? "adaptation held"
          : "balanced display";

  if (nextMode === "simplified") {
    els.navInstruction.textContent = "Keep lane. Take over if requested.";
    els.navDistance.textContent = "1.1";
    els.laneStatus.textContent = "Priority";
  } else if (nextMode === "expanded") {
    els.navInstruction.textContent = "Keep right for airport expressway, traffic merge ahead";
    els.navDistance.textContent = "1.4";
    els.laneStatus.textContent = "Centered";
  } else {
    els.navInstruction.textContent = "Keep right for airport expressway";
    els.navDistance.textContent = "1.2";
    els.laneStatus.textContent = "Centered";
  }

  const lead = nextMode === "simplified" ? 44 : nextMode === "expanded" ? 52 : 46;
  els.leadDistance.textContent = `${lead} m`;
  els.speedValue.textContent = String(nextMode === "simplified" ? 60 : nextMode === "expanded" ? 64 : 62);
  els.rangeValue.textContent = String(Math.round(386 - ((typeof load === "number" ? load : 50) - 50) * 0.2));
}

function drawRoad() {
  const canvas = els.roadCanvas;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const t = state.tick;

  ctx.clearRect(0, 0, width, height);
  const sky = ctx.createLinearGradient(0, 0, 0, height * 0.55);
  sky.addColorStop(0, "#dcebf5");
  sky.addColorStop(1, "#f5f8fb");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = "#d7e2df";
  ctx.beginPath();
  ctx.moveTo(0, height * 0.58);
  ctx.lineTo(width, height * 0.52);
  ctx.lineTo(width, height);
  ctx.lineTo(0, height);
  ctx.closePath();
  ctx.fill();

  const road = ctx.createLinearGradient(0, height * 0.36, 0, height);
  road.addColorStop(0, "#52616d");
  road.addColorStop(1, "#1f2932");
  ctx.fillStyle = road;
  ctx.beginPath();
  ctx.moveTo(width * 0.46, height * 0.36);
  ctx.lineTo(width * 0.54, height * 0.36);
  ctx.lineTo(width * 0.88, height);
  ctx.lineTo(width * 0.12, height);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = "rgba(255,255,255,0.72)";
  ctx.lineWidth = state.hmiMode === "simplified" ? 8 : 5;
  ctx.beginPath();
  ctx.moveTo(width * 0.33, height);
  ctx.lineTo(width * 0.47, height * 0.36);
  ctx.moveTo(width * 0.67, height);
  ctx.lineTo(width * 0.53, height * 0.36);
  ctx.stroke();

  ctx.setLineDash([28, 24]);
  ctx.lineWidth = state.hmiMode === "simplified" ? 7 : 4;
  ctx.strokeStyle = "rgba(255,255,255,0.86)";
  ctx.lineDashOffset = -(t % 52);
  ctx.beginPath();
  ctx.moveTo(width * 0.5, height);
  ctx.lineTo(width * 0.5, height * 0.38);
  ctx.stroke();
  ctx.setLineDash([]);

  if (state.hmiMode !== "simplified") {
    drawVehicle(ctx, width * 0.38, height * 0.68, 70, "#607d94", "A");
    drawVehicle(ctx, width * 0.63, height * 0.56, 52, "#7b8a96", "B");
    drawSign(ctx, width * 0.75, height * 0.42, "80");
  }

  if (state.hmiMode === "expanded") {
    drawVehicle(ctx, width * 0.27, height * 0.78, 58, "#8b6d9f", "C");
    drawSign(ctx, width * 0.23, height * 0.48, "EV");
  }

  drawVehicle(ctx, width * 0.5, height * 0.47, state.hmiMode === "simplified" ? 72 : 56, "#d8a32a", "LEAD");
  drawEgo(ctx, width * 0.5, height * 0.82, state.hmiMode === "simplified");
}

function drawVehicle(ctx, x, y, size, color, label) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = color;
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.roundRect(-size * 0.5, -size * 0.28, size, size * 0.56, 10);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.font = "700 12px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(label, 0, 4);
  ctx.restore();
}

function drawEgo(ctx, x, y, simplified) {
  ctx.save();
  ctx.translate(x, y);
  const w = simplified ? 128 : 104;
  const h = simplified ? 68 : 56;
  ctx.fillStyle = "#1d3447";
  ctx.strokeStyle = "#73d6c4";
  ctx.lineWidth = simplified ? 5 : 3;
  ctx.beginPath();
  ctx.roundRect(-w / 2, -h / 2, w, h, 18);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#e9f7f6";
  ctx.beginPath();
  ctx.roundRect(-w * 0.26, -h * 0.26, w * 0.52, h * 0.3, 8);
  ctx.fill();
  ctx.restore();
}

function drawSign(ctx, x, y, label) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#c83f34";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(0, 0, 25, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#192733";
  ctx.font = "800 14px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(label, 0, 5);
  ctx.restore();
}

function drawLoadChart() {
  const canvas = els.loadChart;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = { left: 38, right: 14, top: 16, bottom: 28 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const yFor = (value) => pad.top + chartH - (Math.max(0, Math.min(100, value)) / 100) * chartH;
  const xFor = (index, count) => pad.left + (count <= 1 ? chartW : (index / (count - 1)) * chartW);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfd";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d8e0e7";
  ctx.lineWidth = 1;
  [0, 25, 50, 75, 100].forEach((tick) => {
    const y = yFor(tick);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillStyle = "#657482";
    ctx.font = "12px Segoe UI, sans-serif";
    ctx.fillText(String(tick), 8, y + 4);
  });

  const thresholdY = yFor(70);
  ctx.strokeStyle = "#c83f34";
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(pad.left, thresholdY);
  ctx.lineTo(width - pad.right, thresholdY);
  ctx.stroke();
  ctx.setLineDash([]);

  const points = state.history.slice(-60);
  if (!points.length) return;
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#245f9f";
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = xFor(index, points.length);
    const y = yFor(point.load);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  points.forEach((point, index) => {
    const x = xFor(index, points.length);
    const y = yFor(point.load);
    ctx.beginPath();
    ctx.fillStyle = point.quality === "pass" ? "#12846f" : "#b56e09";
    ctx.arc(x, y, point.load > 70 && point.quality === "pass" ? 5 : 3.4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function updateFromStatus(result) {
  const current = result.current || {};
  const quality = result.quality || {};
  const load = typeof current.visual_load_index === "number" ? current.visual_load_index : null;
  const qualityStatus = String(quality.status || current.quality_status || "waiting").toLowerCase();
  const symbol = visualSymbol(load, qualityStatus, current.visual_cognitive_symbol);
  const [band, bandLabel] = loadBand(load);

  state.load = load;
  state.quality = qualityStatus;
  applyMode(symbol, load, qualityStatus);

  els.loadCard.className = `mini-card is-${band}`;
  els.loadValue.textContent = load == null ? "--" : Math.round(load);
  els.loadBand.textContent = bandLabel;
  els.qualityLamp.className = `quality-lamp is-${qualityStatus === "pass" ? "pass" : qualityStatus === "waiting" ? "idle" : "warning"}`;
  els.qualityStatus.textContent =
    qualityStatus === "pass" ? "Pass" : qualityStatus === "waiting" ? "Waiting" : "Warning";
  els.qualityDetail.textContent = qualityDetail(result);

  if (typeof load === "number") {
    state.history.push({ load, quality: qualityStatus, time: Date.now() });
    state.history = state.history.slice(-160);
  }

  renderSymbols();
  renderRoute();
  drawRoad();
  drawLoadChart();
}

function statusUrl() {
  const base = state.apiBase ? state.apiBase.replace(/\/$/, "") : "";
  return `${base}/api/status`;
}

async function pollStatus() {
  try {
    const response = await fetch(statusUrl(), { cache: "no-store" });
    if (!response.ok) throw new Error(`/api/status ${response.status}`);
    const result = await response.json();
    setConnection("live", "Live");
    updateFromStatus(result);
  } catch (error) {
    setConnection("error", "Offline");
    applyMode("SIGNAL_QUALITY_WARNING", null, "warning");
    els.qualityLamp.className = "quality-lamp is-warning";
    els.qualityStatus.textContent = "Warning";
    els.qualityDetail.textContent = "Status API unavailable";
    renderSymbols();
    renderRoute();
    drawRoad();
    drawLoadChart();
  }
}

function connect() {
  state.apiBase = els.apiBase.value.trim();
  clearInterval(state.pollTimer);
  pollStatus();
  state.pollTimer = setInterval(pollStatus, 1000);
  logEvent(`Polling ${statusUrl()}`);
}

function animate() {
  state.tick += 1;
  drawRoad();
  requestAnimationFrame(animate);
}

function bindAction(button, label) {
  button.addEventListener("click", () => logEvent(label));
}

els.connectBtn.addEventListener("click", connect);
els.clearLogBtn.addEventListener("click", () => {
  els.eventLog.innerHTML = "";
});
bindAction(els.handoverBtn, "Take over selected");
bindAction(els.confirmBtn, "Route confirmed");
bindAction(els.muteBtn, "Alert audio muted");
bindAction(els.assistBtn, "Driver assist menu opened");

renderSymbols();
renderRoute();
drawRoad();
drawLoadChart();
connect();
requestAnimationFrame(animate);
