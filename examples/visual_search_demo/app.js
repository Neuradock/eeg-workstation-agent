const state = {
  apiBase: "http://127.0.0.1:8765",
  connected: false,
  running: false,
  pollTimer: null,
  roundStartedAt: 0,
  load: null,
  quality: "waiting",
  difficulty: "Baseline",
  hits: 0,
  misses: 0,
  reaction: null,
  targetIndex: 0,
  cells: [],
  lastResult: null,
};

const $ = (id) => document.getElementById(id);

const els = {
  apiBase: $("apiBase"),
  connectBtn: $("connectBtn"),
  connectionState: $("connectionState"),
  qualityBanner: $("qualityBanner"),
  loadValue: $("loadValue"),
  loadLabel: $("loadLabel"),
  qualityLamp: $("qualityLamp"),
  qualityText: $("qualityText"),
  qualityDetail: $("qualityDetail"),
  alphaState: $("alphaState"),
  suppressionValue: $("suppressionValue"),
  taskDifficulty: $("taskDifficulty"),
  taskRule: $("taskRule"),
  targetPrompt: $("targetPrompt"),
  searchGrid: $("searchGrid"),
  startBtn: $("startBtn"),
  pauseBtn: $("pauseBtn"),
  resetBtn: $("resetBtn"),
  nextDemoBtn: $("nextDemoBtn"),
  hits: $("hits"),
  misses: $("misses"),
  reaction: $("reaction"),
  apiStatus: $("apiStatus"),
  peakHz: $("peakHz"),
  asymmetry: $("asymmetry"),
  sampleCount: $("sampleCount"),
  sourceLabel: $("sourceLabel"),
  adaptiveMode: $("adaptiveMode"),
  adaptiveAction: $("adaptiveAction"),
  clearLogBtn: $("clearLogBtn"),
  eventLog: $("eventLog"),
};

function logEvent(message) {
  const item = document.createElement("li");
  const time = new Date().toLocaleTimeString([], { hour12: false });
  item.textContent = `${time}  ${message}`;
  els.eventLog.prepend(item);
  while (els.eventLog.children.length > 18) {
    els.eventLog.lastElementChild.remove();
  }
}

function loadBand(value) {
  if (value == null || Number.isNaN(value)) return ["waiting", "Waiting"];
  if (value < 30) return ["low", "Low"];
  if (value < 70) return ["moderate", "Moderate"];
  return ["high", "High"];
}

function setConnection(kind, label) {
  els.connectionState.className = `status-pill is-${kind}`;
  els.connectionState.textContent = label;
}

function setLoad(value) {
  const rounded = value == null ? "--" : Math.round(value);
  const [band, label] = loadBand(value);
  els.loadValue.textContent = rounded;
  els.loadValue.className = `load-value is-${band}`;
  els.loadLabel.textContent = label;
}

function setQuality(status, detail) {
  const normalized = String(status || "waiting").toLowerCase();
  let lamp = "idle";
  let label = "Waiting";
  if (normalized === "pass") {
    lamp = "pass";
    label = "Pass";
  } else if (normalized === "warning") {
    lamp = "warning";
    label = "Warning";
  } else if (normalized === "fail") {
    lamp = "fail";
    label = "Fail";
  }
  els.qualityLamp.className = `quality-lamp is-${lamp}`;
  els.qualityText.textContent = label;
  els.qualityDetail.textContent = detail || "No channel flags";

  const shouldWarn = normalized === "warning" || normalized === "fail";
  els.qualityBanner.classList.toggle("is-hidden", !shouldWarn);
  els.qualityBanner.classList.toggle("is-fail", normalized === "fail");
  if (shouldWarn) {
    els.qualityBanner.textContent =
      normalized === "fail"
        ? `Quality fail: ${detail || "signal is not reliable for adaptation."}`
        : `Quality warning: ${detail || "interpret workload with caution."}`;
  }
}

function difficultyFromLoad(load, quality) {
  if (quality !== "pass" && quality !== "warning") {
    return "Baseline";
  }
  if (load == null) return "Baseline";
  if (load >= 70) return "Simplified";
  if (load >= 45) return "Working";
  return "Challenge";
}

function gridSpec(difficulty) {
  const specs = {
    Baseline: { columns: 8, count: 48, distractors: ["L", "I"], noise: 0.1 },
    Simplified: { columns: 8, count: 48, distractors: ["L", "I", "F"], noise: 0.25 },
    Working: { columns: 10, count: 80, distractors: ["L", "I", "F", "7"], noise: 0.45 },
    Challenge: { columns: 12, count: 120, distractors: ["L", "I", "F", "7", "Y"], noise: 0.68 },
  };
  return specs[difficulty] || specs.Baseline;
}

function randomChoice(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function buildRound() {
  const spec = gridSpec(state.difficulty);
  els.searchGrid.style.setProperty("--columns", spec.columns);
  els.searchGrid.innerHTML = "";
  const colors = ["is-blue", "is-green", "is-purple"];
  const targetIndex = Math.floor(Math.random() * spec.count);
  state.targetIndex = targetIndex;
  state.cells = [];
  state.roundStartedAt = performance.now();

  for (let index = 0; index < spec.count; index += 1) {
    const cell = document.createElement("button");
    cell.className = "cell";
    cell.type = "button";
    cell.setAttribute("role", "gridcell");
    const isTarget = index === targetIndex;
    if (isTarget) {
      cell.textContent = "T";
      cell.classList.add("is-red", "is-target");
      cell.dataset.target = "true";
    } else {
      cell.textContent = randomChoice(spec.distractors);
      cell.classList.add(Math.random() < spec.noise ? randomChoice(colors) : "is-blue");
      cell.dataset.target = "false";
    }
    cell.addEventListener("click", () => handleCellClick(cell));
    els.searchGrid.appendChild(cell);
    state.cells.push(cell);
  }

  els.targetPrompt.textContent = "Red T";
  els.taskDifficulty.textContent = state.difficulty;
  els.taskRule.textContent =
    state.difficulty === "Simplified"
      ? "Reduced density after high load"
      : state.difficulty === "Challenge"
        ? "Dense visual search"
        : "Find the target symbol";
}

function handleCellClick(cell) {
  if (!state.running) return;
  const elapsed = Math.round(performance.now() - state.roundStartedAt);
  state.reaction = elapsed;
  if (cell.dataset.target === "true") {
    state.hits += 1;
    cell.classList.add("is-hit");
    logEvent(`Hit in ${elapsed} ms at ${state.difficulty}`);
    setTimeout(buildRound, 280);
  } else {
    state.misses += 1;
    cell.classList.add("is-miss");
    logEvent(`Miss at ${state.difficulty}`);
  }
  renderScore();
}

function renderScore() {
  els.hits.textContent = state.hits;
  els.misses.textContent = state.misses;
  els.reaction.textContent = state.reaction == null ? "--" : state.reaction;
}

function qualityDetail(result) {
  const quality = result?.quality || {};
  const channels = quality.bad_channel_candidates || [];
  const fraction = quality.channel_issue_fraction;
  if (channels.length) return `${channels.length} channels flagged: ${channels.join(", ")}`;
  if (typeof fraction === "number" && fraction > 0) {
    return `${Math.round(fraction * 100)}% channels flagged`;
  }
  return "No channel flags";
}

function updateFromApi(result) {
  state.lastResult = result;
  const current = result.current || {};
  const quality = result.quality || {};
  const stream = result.stream || {};
  const load =
    typeof current.visual_load_index === "number" ? current.visual_load_index : null;
  const qualityStatus = String(quality.status || current.quality_status || "waiting").toLowerCase();
  const detail = qualityDetail(result);

  state.load = load;
  state.quality = qualityStatus;
  const nextDifficulty = difficultyFromLoad(load, qualityStatus);
  const difficultyChanged = nextDifficulty !== state.difficulty;
  state.difficulty = nextDifficulty;

  setLoad(load);
  setQuality(qualityStatus, detail);
  els.alphaState.textContent = current.alpha_state || "--";
  els.suppressionValue.textContent =
    typeof current.alpha_suppression_from_baseline === "number"
      ? `Suppression ${current.alpha_suppression_from_baseline.toFixed(3)}`
      : "Suppression --";
  els.apiStatus.textContent = result.status || "--";
  els.peakHz.textContent =
    typeof current.alpha_peak_hz === "number"
      ? `${current.alpha_peak_hz.toFixed(2)} Hz`
      : "-- Hz";
  els.asymmetry.textContent =
    typeof current.alpha_asymmetry_right_minus_left === "number"
      ? current.alpha_asymmetry_right_minus_left.toFixed(3)
      : "--";
  els.sampleCount.textContent = stream.samples_received ?? current.sample_index ?? "--";
  els.sourceLabel.textContent = result.source || result.demo?.source || "--";

  if (qualityStatus === "pass" || qualityStatus === "warning") {
    if (load != null && load >= 70) {
      els.adaptiveAction.textContent = "High load: task density reduced and adaptation remains quality-gated.";
    } else if (load != null && load < 30) {
      els.adaptiveAction.textContent = "Low load: task density can increase to keep the challenge useful.";
    } else {
      els.adaptiveAction.textContent = "Moderate load: task remains in the working zone.";
    }
  } else {
    els.adaptiveAction.textContent = "Quality gate is not pass/warning; adaptation is held.";
  }

  if (difficultyChanged && state.running) {
    logEvent(`Adapted task to ${state.difficulty}`);
    buildRound();
  } else {
    els.taskDifficulty.textContent = state.difficulty;
  }
}

async function fetchJson(route) {
  const response = await fetch(`${state.apiBase}${route}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${route} ${response.status}`);
  return response.json();
}

async function pollApi() {
  try {
    const route = state.running ? "/api/next" : "/api/status";
    const result = await fetchJson(route);
    state.connected = true;
    setConnection("live", "Live");
    updateFromApi(result);
  } catch (error) {
    state.connected = false;
    setConnection("error", "Offline");
    els.apiStatus.textContent = "offline";
    els.adaptiveAction.textContent = "Start neuradock-agent serve or online mode to enable workload adaptation.";
  }
}

function connect() {
  state.apiBase = els.apiBase.value.trim().replace(/\/$/, "") || "http://127.0.0.1:8765";
  clearInterval(state.pollTimer);
  pollApi();
  state.pollTimer = setInterval(pollApi, 1000);
  logEvent(`Connected to ${state.apiBase}`);
}

async function stepDemo() {
  try {
    const result = await fetchJson("/api/demo/next");
    updateFromApi(result);
    setConnection("live", "Live");
  } catch (error) {
    setConnection("error", "Offline");
    logEvent("Demo step failed; check the agent API.");
  }
}

function startTask() {
  state.running = true;
  buildRound();
  pollApi();
  logEvent("Visual search started");
}

function pauseTask() {
  state.running = false;
  logEvent("Task paused");
}

function resetTask() {
  state.hits = 0;
  state.misses = 0;
  state.reaction = null;
  state.difficulty = "Baseline";
  renderScore();
  buildRound();
  logEvent("Task reset");
}

els.connectBtn.addEventListener("click", connect);
els.nextDemoBtn.addEventListener("click", stepDemo);
els.startBtn.addEventListener("click", startTask);
els.pauseBtn.addEventListener("click", pauseTask);
els.resetBtn.addEventListener("click", resetTask);
els.clearLogBtn.addEventListener("click", () => {
  els.eventLog.innerHTML = "";
});

setLoad(null);
setQuality("waiting", "No API data yet");
renderScore();
buildRound();
connect();
