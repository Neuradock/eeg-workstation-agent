/* NeuraDock Alpha Experience: same-origin, quality-gated, no external assets. */
"use strict";
(() => {
  const state = window.AlphaDashboardState;
  const $ = id => document.getElementById(id);
  let payload = {};
  let paused = false;
  let pausedSeries = null;
  let pausedSource = null;
  let requestError = false;
  let timer = null;
  let controller = null;
  let generation = 0;
  let plot = null;
  let view = null;
  const fmt = value => typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) + "×" : "—";
  const text = (id, value) => { $(id).textContent = value; };
  const visibleSeries = () => paused && pausedSeries ? pausedSeries : state.seriesFrom(payload);

  function fitCanvas(canvas) {
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return null;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width, height };
  }

  function drawChart() {
    const canvas = $("alphaChart"), surface = fitCanvas(canvas);
    if (!surface) return;
    const { ctx, width, height } = surface;
    const data = visibleSeries();
    const values = data.map(p => p.value).filter(v => typeof v === "number" && Number.isFinite(v));
    const end = Math.max(60, ...data.map(p => p.time));
    const start = Math.max(0, end - 60);
    const low = values.length && Math.min(...values) < .5 ? 0 : .5;
    const high = Math.max(1.5, values.length ? Math.ceil(Math.max(...values) * 2) / 2 : 1.5);
    const box = { x: width < 400 ? 57 : 72, y: 16, width: width - (width < 400 ? 78 : 98), height: height - 70 };
    const x = t => box.x + ((t - start) / (end - start)) * box.width;
    const y = v => box.y + (high - v) / (high - low) * box.height;
    ctx.clearRect(0, 0, width, height);
    ctx.font = '14px "Segoe UI", sans-serif';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const value = low + (high - low) * i / 4, py = y(value);
      ctx.strokeStyle = "#183445"; ctx.beginPath(); ctx.moveTo(box.x, py); ctx.lineTo(box.x + box.width, py); ctx.stroke();
      if (i % 2 === 0) { ctx.fillStyle = "#b4cadd"; ctx.textAlign = "right"; ctx.fillText(value.toFixed(1) + "×", box.x - 12, py + 5); }
    }
    for (let i = 0; i <= 4; i++) {
      const value = start + (end - start) * i / 4, px = x(value);
      ctx.strokeStyle = "#183445"; ctx.beginPath(); ctx.moveTo(px, box.y); ctx.lineTo(px, box.y + box.height); ctx.stroke();
      ctx.fillStyle = "#b4cadd"; ctx.textAlign = "center"; ctx.fillText(Math.round(value).toString(), px, box.y + box.height + 29);
    }
    ctx.strokeStyle = "#67869d"; ctx.beginPath(); ctx.moveTo(box.x, box.y); ctx.lineTo(box.x, box.y + box.height); ctx.lineTo(box.x + box.width, box.y + box.height); ctx.stroke();
    ctx.strokeStyle = "#9bb4c7"; ctx.setLineDash([6, 6]); ctx.beginPath(); ctx.moveTo(box.x, y(1)); ctx.lineTo(box.x + box.width, y(1)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#b4cadd"; ctx.textAlign = "center";
    ctx.fillText("Time (s)", box.x + box.width / 2, height - 7);
    ctx.save(); ctx.translate(16, box.y + box.height / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("Power / baseline", 0, 0); ctx.restore();
    let segments = [], segment = [];
    for (const point of data) {
      if (typeof point.value === "number" && Number.isFinite(point.value)) segment.push(point);
      else if (segment.length) { segments.push(segment); segment = []; }
    }
    if (segment.length) segments.push(segment);
    ctx.save(); ctx.beginPath(); ctx.rect(box.x, box.y - 2, box.width + 2, box.height + 4); ctx.clip();
    for (const part of segments) {
      ctx.beginPath(); ctx.moveTo(x(part[0].time), y(part[0].value));
      part.slice(1).forEach(p => ctx.lineTo(x(p.time), y(p.value)));
      ctx.strokeStyle = paused ? "#7198a7" : "#46d8e8"; ctx.lineWidth = 2.5; ctx.stroke();
      ctx.lineTo(x(part[part.length - 1].time), y(low)); ctx.lineTo(x(part[0].time), y(low)); ctx.closePath(); ctx.fillStyle = "#46d8e80a"; ctx.fill();
    }
    ctx.restore();
    const last = data[data.length - 1];
    if (last && last.value !== null && Number.isFinite(last.value)) {
      ctx.fillStyle = paused ? "#7198a7" : "#46d8e8"; ctx.beginPath(); ctx.arc(x(last.time), y(last.value), 5, 0, Math.PI * 2); ctx.fill();
      ctx.font = '600 15px "Segoe UI", sans-serif'; ctx.textAlign = "right";
      ctx.fillText(fmt(last.value), Math.min(width - 4, x(last.time) + 8), Math.max(14, y(last.value) - 18));
    }
    plot = { data, box, start, end, x, y };
    $("chartEmpty").hidden = values.length > 0;
    text("chartEmpty", payload.status === "warming_up" ? "Collecting a clean analysis window…" : "Building a clean rolling baseline…");
    canvas.setAttribute("aria-label", "Alpha power relative to rolling baseline. " + (values.length ? values.length + " valid historical points. Current feedback: " + fmt(view?.ratio) + ". Gaps indicate invalid data." : "Waiting for three clean windows."));
  }

  function drawRing() {
    const surface = fitCanvas($("feedbackRing"));
    if (!surface) return;
    const { ctx, width, height } = surface;
    const radius = Math.max(25, Math.min(width, height) / 2 - 15);
    const ratio = view?.ratio;
    ctx.clearRect(0, 0, width, height); ctx.lineWidth = Math.min(16, radius * .12); ctx.lineCap = "round";
    ctx.strokeStyle = "#284354"; ctx.beginPath(); ctx.arc(width / 2, height / 2, radius, 0, Math.PI * 2); ctx.stroke();
    if (typeof ratio === "number" && Number.isFinite(ratio)) {
      const fraction = Math.max(0, Math.min(1, ratio / 1.5));
      if (fraction > 0) { ctx.strokeStyle = "#46d8e8"; ctx.beginPath(); ctx.arc(width / 2, height / 2, radius, -Math.PI / 2, -Math.PI / 2 + fraction * 2 * Math.PI); ctx.stroke(); }
    }
  }

  function render() {
    view = state.deriveView(payload, { paused, requestError });
    ["modeDescription", "playbackLabel", "playbackDetail", "primaryLabel", "feedbackMessage"].forEach(id => text(id, view[id]));
    text("modeLabel", view.modeLabel.toUpperCase());
    text("qualityTitle", view.sourceKind === "synthetic_demo" ? "Demo quality" : "Signal quality");
    const qualityLabel = view.qualityLabel.replace(/^Quality /, "");
    text("qualityLabel", qualityLabel.charAt(0).toUpperCase() + qualityLabel.slice(1));
    document.querySelector(".quality-summary").title = view.qualityTitle;
    if (view.feedbackAvailable) {
      text("playbackLabel", "Running");
      text("playbackDetail", {synthetic_demo:"Synthetic signal",recorded_replay:"Recorded replay",live_device:"Live device stream",manual_post:"Local API input"}[view.sourceKind]);
    } else if (paused) {
      text("playbackDetail", view.sourceKind === "live_device" ? "Acquisition continues" : "Historical view");
    } else if (view.playbackLabel === "Warming up") text("playbackDetail", "Building rolling baseline");
    text("alphaValue", fmt(view.ratio)); text("feedbackValue", fmt(view.ratio));
    $("sourceBadge").classList.toggle("live", view.sourceKind === "live_device");
    $("playbackDot").className = "status-dot " + (view.feedbackAvailable ? "running" : "paused");
    $("pauseButton").disabled = false;
    $("pauseIcon").src = paused ? "/assets/icons/play-fill.svg" : "/assets/icons/pause-fill.svg";
    $("warningBanner").hidden = !view.warning; text("warningText", view.warning);
    document.querySelector(".feedback-panel").classList.toggle("unavailable", !view.feedbackAvailable);
    document.querySelector(".quality-summary").className = "quality-summary " + view.qualityTone;
    $("qualityIcon").src = "/assets/icons/" + (view.qualityTone === "pass" ? "check-circle" : view.qualityTone === "muted" ? "info-circle" : "exclamation-triangle") + ".svg";
    const metrics = new Map((Array.isArray(payload.channels) ? payload.channels : []).filter(c => c && typeof c.name === "string").map(c => [c.name, c]));
    const bad = new Set(Array.isArray(payload.quality?.bad_channel_candidates) ? payload.quality.bad_channel_candidates : []);
    for (const el of document.querySelectorAll("[data-channel]")) {
      const name = el.dataset.channel, metric = metrics.get(name);
      const available = !requestError && payload.status === "ok" && payload.freshness?.status !== "stale" && (view.sourceKind !== "live_device" || payload.stream?.connected === true);
      const status = !available ? "unavailable" : bad.has(name) || metric?.status === "flagged" ? "flagged" : metric?.status === "pass" ? "pass" : "unavailable";
      const reasons = (Array.isArray(metric?.reasons) ? metric.reasons : []).join(", ").replaceAll("_", " ");
      el.className = status;
      el.title = name + ": " + status + (reasons ? " — " + reasons : "");
      el.setAttribute("aria-label", el.title);
    }
    const sourceText = {synthetic_demo:"Synthetic data",recorded_replay:"Recorded replay",live_device:"Device stream",manual_post:"External input",unknown:"Unverified source"}[view.sourceKind] || "Unverified source";
    text("footerMode", sourceText + " · Research & education only · Not a relaxation score");
    drawChart(); drawRing();
  }

  async function poll() {
    const ticket = generation;
    const requestController = new AbortController();
    controller = requestController;
    const timeout = setTimeout(() => requestController.abort(), 5000);
    try {
      const response = await fetch(paused ? "/api/status" : "/api/next", {cache:"no-store", signal:requestController.signal});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const result = await response.json();
      if (!result || typeof result !== "object" || Array.isArray(result) || result.error) throw new Error("Invalid dashboard response");
      if (ticket !== generation) return;
      if (paused && result.source_info?.kind !== pausedSource) {
        pausedSeries = [];
        pausedSource = result.source_info?.kind;
      }
      payload = result; requestError = false; render();
    } catch (error) {
      if (ticket === generation) { requestError = true; render(); }
    } finally {
      clearTimeout(timeout);
      if (ticket === generation) timer = setTimeout(poll, 1000);
    }
  }

  $("pauseButton").addEventListener("click", () => {
    paused = !paused;
    pausedSeries = paused ? state.seriesFrom(payload) : null;
    pausedSource = paused ? payload.source_info?.kind : null;
    generation++; clearTimeout(timer); controller?.abort(); render(); poll();
  });
  $("connectButton").addEventListener("click", () => $("connectDialog").showModal());
  $("infoButton").addEventListener("click", () => $("infoDialog").showModal());
  document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
  $("connectionForm").addEventListener("submit", event => {
    event.preventDefault(); $("commandBlock").hidden = true; text("connectionMessage", "");
    try {
      const command = state.connectionCommand($("deviceHost").value, $("devicePort").value, location.port || (location.protocol === "https:" ? 443 : 80));
      text("connectionCommand", command); $("commandBlock").hidden = false;
      text("copyCommand", "Copy command");
    } catch (error) { text("connectionMessage", error.message); }
  });
  $("copyCommand").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("connectionCommand").textContent); text("copyCommand", "Copied"); }
    catch { text("connectionMessage", "Select and copy the command manually; clipboard access is unavailable."); $("connectionCommand").focus(); }
  });
  $("alphaChart").addEventListener("pointermove", event => {
    if (!plot?.data.length) return;
    const rect = event.currentTarget.getBoundingClientRect(), px = event.clientX - rect.left;
    const time = plot.start + (px - plot.box.x) / plot.box.width * (plot.end - plot.start);
    const point = plot.data.reduce((best, p) => Math.abs(p.time - time) < Math.abs(best.time - time) ? p : best);
    const tooltip = $("chartTooltip");
    tooltip.textContent = point.time.toFixed(1) + " s · " + (point.value === null ? "Unavailable (quality / baseline)" : fmt(point.value) + " relative power");
    tooltip.hidden = false; tooltip.style.left = Math.max(0, Math.min(rect.width - tooltip.offsetWidth, px + 10)) + "px"; tooltip.style.top = "8px";
  });
  $("alphaChart").addEventListener("pointerleave", () => { $("chartTooltip").hidden = true; });
  const observer = new ResizeObserver(() => { drawChart(); drawRing(); });
  observer.observe(document.querySelector(".chart-figure")); observer.observe(document.querySelector(".feedback-gauge"));
  window.addEventListener("pagehide", () => { generation++; clearTimeout(timer); controller?.abort(); });
  window.addEventListener("pageshow", event => {
    if (event.persisted) { generation++; clearTimeout(timer); controller?.abort(); poll(); }
  });
  render(); poll();
})();
