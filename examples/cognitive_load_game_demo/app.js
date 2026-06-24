const state = {
  apiBase: "",
  pollTimer: null,
  running: true,
  score: 0,
  hits: 0,
  misses: 0,
  load: null,
  quality: "waiting",
  mode: "standard",
  symbol: "WAITING",
  history: [],
  entities: [],
  particles: [],
  lastFrame: 0,
  nextId: 1,
  config: {
    targetCount: 4,
    distractorCount: 4,
    speed: 1,
    targetRadius: 24,
    modeLabel: "Standard",
  },
};

const configs = {
  challenge: {
    targetCount: 7,
    distractorCount: 7,
    speed: 1.55,
    targetRadius: 18,
    modeLabel: "Challenge",
    detail: "More targets, faster motion",
  },
  standard: {
    targetCount: 4,
    distractorCount: 4,
    speed: 1,
    targetRadius: 23,
    modeLabel: "Standard",
    detail: "Balanced loop",
  },
  simplified: {
    targetCount: 2,
    distractorCount: 1,
    speed: 0.62,
    targetRadius: 31,
    modeLabel: "Simplified",
    detail: "Slower targets, fewer distractors",
  },
};

const $ = (id) => document.getElementById(id);

const els = {
  app: $("app"),
  apiBase: $("apiBase"),
  connectBtn: $("connectBtn"),
  connectionState: $("connectionState"),
  messageBanner: $("messageBanner"),
  scoreValue: $("scoreValue"),
  hitsValue: $("hitsValue"),
  missValue: $("missValue"),
  loadCard: $("loadCard"),
  loadValue: $("loadValue"),
  loadBand: $("loadBand"),
  qualityLamp: $("qualityLamp"),
  qualityStatus: $("qualityStatus"),
  qualityDetail: $("qualityDetail"),
  modeValue: $("modeValue"),
  modeDetail: $("modeDetail"),
  roundLabel: $("roundLabel"),
  gameCanvas: $("gameCanvas"),
  startBtn: $("startBtn"),
  pauseBtn: $("pauseBtn"),
  resetBtn: $("resetBtn"),
  sourceLabel: $("sourceLabel"),
  symbolValue: $("symbolValue"),
  targetCount: $("targetCount"),
  speedFactor: $("speedFactor"),
  distractorCount: $("distractorCount"),
  loadChart: $("loadChart"),
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

function symbolFromStatus(load, qualityStatus, apiSymbol) {
  if (qualityStatus !== "pass") return "SIGNAL_QUALITY_WARNING";
  if (apiSymbol) return String(apiSymbol).toUpperCase();
  if (typeof load !== "number") return "WAITING";
  if (load > 70) return "VISUAL_LOAD_HIGH";
  if (load < 35) return "VISUAL_LOAD_LOW";
  return "VISUAL_LOAD_STABLE";
}

function modeFromSymbol(symbol) {
  if (symbol === "VISUAL_LOAD_LOW") return "challenge";
  if (symbol === "VISUAL_LOAD_HIGH") return "simplified";
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

function ensureEntities() {
  const canvas = els.gameCanvas;
  const desiredTargets = state.config.targetCount;
  const desiredDistractors = state.config.distractorCount;
  let targets = state.entities.filter((entity) => entity.kind === "target");
  let distractors = state.entities.filter((entity) => entity.kind === "distractor");

  while (targets.length < desiredTargets) {
    const entity = createEntity("target", canvas);
    state.entities.push(entity);
    targets.push(entity);
  }
  while (distractors.length < desiredDistractors) {
    const entity = createEntity("distractor", canvas);
    state.entities.push(entity);
    distractors.push(entity);
  }

  targets = targets.slice(0, desiredTargets);
  distractors = distractors.slice(0, desiredDistractors);
  state.entities = [...targets, ...distractors];
  state.entities.forEach((entity) => {
    entity.radius = entity.kind === "target" ? state.config.targetRadius : Math.max(14, state.config.targetRadius * 0.78);
  });
}

function createEntity(kind, canvas) {
  const radius = kind === "target" ? state.config.targetRadius : Math.max(14, state.config.targetRadius * 0.78);
  const angle = Math.random() * Math.PI * 2;
  const baseSpeed = kind === "target" ? 120 : 90;
  return {
    id: state.nextId++,
    kind,
    x: radius + Math.random() * (canvas.width - radius * 2),
    y: radius + Math.random() * (canvas.height - radius * 2),
    vx: Math.cos(angle) * baseSpeed,
    vy: Math.sin(angle) * baseSpeed,
    radius,
    phase: Math.random() * Math.PI * 2,
  };
}

function applyMode(nextMode, reason) {
  if (!configs[nextMode]) return;
  if (state.mode !== nextMode) {
    logEvent(`${configs[nextMode].modeLabel} mode: ${reason}`);
  }
  state.mode = nextMode;
  state.config = { ...configs[nextMode] };
  els.app.classList.toggle("is-challenge", nextMode === "challenge");
  els.app.classList.toggle("is-simplified", nextMode === "simplified");
  els.modeValue.textContent = state.config.modeLabel;
  els.modeDetail.textContent = state.config.detail;
  els.roundLabel.textContent =
    nextMode === "challenge"
      ? "Challenge Round"
      : nextMode === "simplified"
        ? "Simplified Round"
        : "Adaptive Round";
  ensureEntities();
  updateConfigReadouts();
}

function applyStatus(result) {
  const current = result.current || {};
  const quality = result.quality || {};
  const load = typeof current.visual_load_index === "number" ? current.visual_load_index : null;
  const qualityStatus = String(quality.status || current.quality_status || "waiting").toLowerCase();
  const symbol = symbolFromStatus(load, qualityStatus, current.visual_cognitive_symbol);
  const [band, bandLabel] = loadBand(load);

  state.load = load;
  state.quality = qualityStatus;
  state.symbol = symbol;

  els.loadCard.className = `metric-card is-${band}`;
  els.loadValue.textContent = load == null ? "--" : Math.round(load);
  els.loadBand.textContent = bandLabel;
  els.qualityLamp.className = `quality-lamp is-${qualityStatus === "pass" ? "pass" : qualityStatus === "waiting" ? "idle" : "warning"}`;
  els.qualityStatus.textContent =
    qualityStatus === "pass" ? "Pass" : qualityStatus === "waiting" ? "Waiting" : "Warning";
  els.qualityDetail.textContent = qualityDetail(result);
  els.sourceLabel.textContent = result.source || "status API";
  els.symbolValue.textContent = symbol;

  const qualityWarning = qualityStatus !== "pass";
  els.app.classList.toggle("has-quality-warning", qualityWarning);
  els.messageBanner.className = "message-banner";
  if (qualityWarning) {
    els.messageBanner.textContent = "Signal quality warning, adaptation paused";
    els.messageBanner.classList.add("is-quality");
  } else if (symbol === "VISUAL_LOAD_LOW") {
    els.messageBanner.textContent = "Low visual load, challenge increased";
    els.messageBanner.classList.add("is-low");
    applyMode("challenge", "low load");
  } else if (symbol === "VISUAL_LOAD_HIGH") {
    els.messageBanner.textContent = "High visual load, simplified game enabled";
    els.messageBanner.classList.add("is-high");
    applyMode("simplified", "high load");
  } else {
    els.messageBanner.textContent = "";
    els.messageBanner.classList.add("is-hidden");
    applyMode("standard", "moderate load");
  }

  if (qualityWarning) {
    updateConfigReadouts();
  }
  if (typeof load === "number") {
    state.history.push({ load, quality: qualityStatus });
    state.history = state.history.slice(-120);
  }
  drawLoadChart();
}

function updateConfigReadouts() {
  els.targetCount.textContent = String(state.config.targetCount);
  els.speedFactor.textContent = `${state.config.speed.toFixed(2)}x`;
  els.distractorCount.textContent = String(state.config.distractorCount);
}

function updateScore() {
  els.scoreValue.textContent = String(state.score);
  els.hitsValue.textContent = String(state.hits);
  els.missValue.textContent = String(state.misses);
}

function canvasPoint(event) {
  const rect = els.gameCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * els.gameCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * els.gameCanvas.height,
  };
}

function handleCanvasClick(event) {
  if (!state.running) return;
  const point = canvasPoint(event);
  const hit = state.entities
    .filter((entity) => entity.kind === "target")
    .find((entity) => Math.hypot(point.x - entity.x, point.y - entity.y) <= entity.radius + 4);
  if (hit) {
    state.score += state.mode === "challenge" ? 14 : state.mode === "simplified" ? 8 : 10;
    state.hits += 1;
    burst(hit.x, hit.y, "#12846f");
    Object.assign(hit, createEntity("target", els.gameCanvas), { id: hit.id });
    logEvent(`Hit at ${state.config.modeLabel}`);
  } else {
    const distractor = state.entities
      .filter((entity) => entity.kind === "distractor")
      .find((entity) => Math.hypot(point.x - entity.x, point.y - entity.y) <= entity.radius + 4);
    if (distractor) {
      state.score = Math.max(0, state.score - 6);
      state.misses += 1;
      burst(distractor.x, distractor.y, "#c83f34");
      logEvent("Distractor clicked");
    } else {
      state.score = Math.max(0, state.score - 2);
      state.misses += 1;
    }
  }
  updateScore();
}

function burst(x, y, color) {
  for (let i = 0; i < 12; i += 1) {
    const angle = (Math.PI * 2 * i) / 12;
    state.particles.push({
      x,
      y,
      vx: Math.cos(angle) * (80 + Math.random() * 60),
      vy: Math.sin(angle) * (80 + Math.random() * 60),
      life: 0.45,
      color,
    });
  }
}

function updateGame(dt) {
  if (!state.running) return;
  const canvas = els.gameCanvas;
  state.entities.forEach((entity) => {
    entity.x += entity.vx * state.config.speed * dt;
    entity.y += entity.vy * state.config.speed * dt;
    entity.phase += dt * 4;
    if (entity.x < entity.radius || entity.x > canvas.width - entity.radius) {
      entity.vx *= -1;
      entity.x = Math.max(entity.radius, Math.min(canvas.width - entity.radius, entity.x));
    }
    if (entity.y < entity.radius || entity.y > canvas.height - entity.radius) {
      entity.vy *= -1;
      entity.y = Math.max(entity.radius, Math.min(canvas.height - entity.radius, entity.y));
    }
  });
  state.particles.forEach((particle) => {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.life -= dt;
  });
  state.particles = state.particles.filter((particle) => particle.life > 0);
}

function drawGame() {
  const canvas = els.gameCanvas;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "#f9fcfd");
  bg.addColorStop(1, "#e9f1f5");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(36, 95, 159, 0.12)";
  ctx.lineWidth = 1;
  for (let x = 40; x < width; x += 80) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 40; y < height; y += 80) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  state.entities
    .filter((entity) => entity.kind === "distractor")
    .forEach((entity) => drawDistractor(ctx, entity));
  state.entities
    .filter((entity) => entity.kind === "target")
    .forEach((entity) => drawTarget(ctx, entity));

  state.particles.forEach((particle) => {
    ctx.globalAlpha = Math.max(0, particle.life / 0.45);
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  });

  if (!state.running) {
    ctx.fillStyle = "rgba(23, 33, 43, 0.58)";
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.font = "900 42px Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("PAUSED", width / 2, height / 2);
  }
}

function drawTarget(ctx, entity) {
  const pulse = Math.sin(entity.phase) * 2;
  const radius = entity.radius + pulse;
  ctx.save();
  ctx.translate(entity.x, entity.y);
  ctx.fillStyle = "#12846f";
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.strokeStyle = "rgba(18, 132, 111, 0.32)";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(0, 0, radius + 11, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(0, 0, Math.max(5, radius * 0.26), 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawDistractor(ctx, entity) {
  ctx.save();
  ctx.translate(entity.x, entity.y);
  ctx.rotate(entity.phase * 0.45);
  ctx.fillStyle = "#6b57a8";
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 4;
  const r = entity.radius;
  ctx.beginPath();
  ctx.moveTo(0, -r);
  ctx.lineTo(r, 0);
  ctx.lineTo(0, r);
  ctx.lineTo(-r, 0);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawLoadChart() {
  const canvas = els.loadChart;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const pad = { left: 34, right: 12, top: 12, bottom: 24 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const yFor = (value) => pad.top + chartH - (Math.max(0, Math.min(100, value)) / 100) * chartH;
  const xFor = (index, count) => pad.left + (count <= 1 ? chartW : (index / (count - 1)) * chartW);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfd";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d7e0e7";
  ctx.lineWidth = 1;
  [0, 50, 100].forEach((tick) => {
    const y = yFor(tick);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillStyle = "#657586";
    ctx.font = "12px Segoe UI, sans-serif";
    ctx.fillText(String(tick), 8, y + 4);
  });
  ctx.strokeStyle = "#c83f34";
  ctx.setLineDash([5, 4]);
  ctx.beginPath();
  ctx.moveTo(pad.left, yFor(70));
  ctx.lineTo(width - pad.right, yFor(70));
  ctx.stroke();
  ctx.setLineDash([]);

  const points = state.history.slice(-70);
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
    ctx.fillStyle = point.quality === "pass" ? "#12846f" : "#b56e09";
    ctx.beginPath();
    ctx.arc(x, y, 3.4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function frame(timestamp) {
  const dt = Math.min(0.04, (timestamp - state.lastFrame) / 1000 || 0.016);
  state.lastFrame = timestamp;
  updateGame(dt);
  drawGame();
  requestAnimationFrame(frame);
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
    applyStatus(result);
  } catch (error) {
    setConnection("error", "Offline");
    els.messageBanner.className = "message-banner is-quality";
    els.messageBanner.textContent = "Signal quality warning, adaptation paused";
    els.qualityLamp.className = "quality-lamp is-warning";
    els.qualityStatus.textContent = "Warning";
    els.qualityDetail.textContent = "Status API unavailable";
  }
}

function connect() {
  state.apiBase = els.apiBase.value.trim();
  clearInterval(state.pollTimer);
  pollStatus();
  state.pollTimer = setInterval(pollStatus, 1000);
  logEvent(`Polling ${statusUrl()}`);
}

function resetGame() {
  state.score = 0;
  state.hits = 0;
  state.misses = 0;
  state.entities = [];
  state.particles = [];
  ensureEntities();
  updateScore();
  logEvent("Round reset");
}

els.connectBtn.addEventListener("click", connect);
els.startBtn.addEventListener("click", () => {
  state.running = true;
  logEvent("Round started");
});
els.pauseBtn.addEventListener("click", () => {
  state.running = false;
  logEvent("Round paused");
});
els.resetBtn.addEventListener("click", resetGame);
els.clearLogBtn.addEventListener("click", () => {
  els.eventLog.innerHTML = "";
});
els.gameCanvas.addEventListener("click", handleCanvasClick);

updateScore();
applyMode("standard", "initial");
connect();
requestAnimationFrame(frame);
