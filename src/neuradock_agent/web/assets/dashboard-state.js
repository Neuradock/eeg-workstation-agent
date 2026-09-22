/* Pure UI state: no DOM, network, device commands, or implicit numeric coercion. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.AlphaDashboardState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SOURCE = Object.freeze({
    synthetic_demo: ["Synthetic demo", "Generated signal, not your EEG."],
    recorded_replay: ["Recorded replay", "Recorded data, not a live stream."],
    live_device: ["Live device", "EEG received from your configured NeuraDock device."],
    manual_post: ["Manual input", "Samples submitted to the local API; source not verified."],
    unknown: ["Unknown source", "Data source is not verified. Feedback is unavailable."]
  });
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const object = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const positive = value => finite(value) && value > 0;

  function kindOf(payload) {
    const kind = object(payload.source_info).kind;
    return Object.prototype.hasOwnProperty.call(SOURCE, kind) && kind !== "unknown" ? kind : "unknown";
  }

  function qualityOf(payload) {
    const quality = object(payload.quality);
    const current = object(payload.current);
    const statuses = [quality.status, current.quality_status];
    const flags = Array.isArray(quality.bad_channel_candidates)
      ? [...new Set(quality.bad_channel_candidates.filter(name => typeof name === "string" && name.length > 0))]
      : [];
    const flagText = flags.length ? ` · ${flags.length} flagged` : "";
    if (statuses.some(status => status === "fail" || status === "error")) {
      return { allowed: false, label: `Quality fail${flagText}`, tone: "fail", title: "Quality gate failed. Check electrodes, movement, and interference." };
    }
    if (statuses.some(status => status === "warning" || status === "bad")) {
      return { allowed: false, label: `Quality warning${flagText}`, tone: "warning", title: "Quality gate warning. Feedback is unavailable until signal quality recovers." };
    }
    if (quality.status === "pass" && current.quality_status === "pass") {
      return {
        allowed: true,
        label: `Quality pass${flagText}`,
        tone: flags.length ? "warning" : "pass",
        title: flags.length
          ? `Window gate passed; channel flags remain: ${flags.join(", ")}. Inspect these channels.`
          : "Window quality gate passed; no bad-channel candidates reported."
      };
    }
    return { allowed: false, label: "Quality pending", tone: "muted", title: "Waiting for a complete quality-checked window." };
  }

  function freshnessOf(payload, sourceKind, nowMs) {
    if (sourceKind !== "live_device" && sourceKind !== "manual_post") return "not_applicable";
    const freshness = object(payload.freshness);
    if (freshness.status === "stale") return "stale";
    if (positive(freshness.stale_after_sec)) {
      if (finite(freshness.age_sec) && freshness.age_sec > freshness.stale_after_sec) return "stale";
      const lastSample = object(payload.stream).last_sample_time;
      // Worker timestamps are Unix seconds, not browser milliseconds. This is a
      // conservative second check; the backend's monotonic freshness is primary.
      if (sourceKind === "live_device" && positive(lastSample) && finite(nowMs)
          && nowMs / 1000 - lastSample > freshness.stale_after_sec) return "stale";
    }
    return freshness.status === "fresh" ? "fresh" : "waiting_for_data";
  }

  /**
   * Derive a display-only view from /api/status or /api/next.
   * Text fields: modeLabel, modeDescription, sourceKind, playbackLabel,
   * playbackDetail, qualityLabel, qualityTone (pass/warning/fail/muted),
   * qualityTitle, warning (empty when none), primaryLabel, feedbackMessage.
   * ratio is a positive finite Alpha power multiplier or null. A null value
   * MUST remain a gap/placeholder, never zero. feedbackAvailable is boolean.
   * Pausing hides CURRENT feedback only; seriesFrom retains historical values.
   */
  function deriveView(payload, { paused = false, requestError = false, nowMs = Date.now() } = {}) {
    const data = object(payload);
    const current = object(data.current);
    const sourceKind = kindOf(data);
    const source = SOURCE[sourceKind];
    const quality = qualityOf(data);
    const stream = object(data.stream);
    const freshness = freshnessOf(data, sourceKind, nowMs);
    const baseline = object(data.baseline);
    const count = finite(baseline.history_count) ? baseline.history_count : current.baseline_history_count;
    const minimum = positive(baseline.minimum_history_count) ? baseline.minimum_history_count : 3;
    const playbackNoun = sourceKind === "synthetic_demo" ? "demo" : sourceKind === "recorded_replay" ? "replay" : "display";
    const warmup = data.status !== "ok" || current.alpha_state === "initializing"
      || data.feedback_reason === "baseline_warming_up" || current.feedback_reason === "baseline_warming_up"
      || (finite(count) && count < minimum);
    const view = {
      modeLabel: source[0], modeDescription: source[1], sourceKind,
      playbackLabel: sourceKind === "synthetic_demo" ? "Demo running"
        : sourceKind === "recorded_replay" ? "Replay running"
        : sourceKind === "live_device" ? "Live stream"
        : sourceKind === "manual_post" ? "Receiving input" : "Waiting for source",
      playbackDetail: source[1], qualityLabel: quality.label, qualityTone: quality.tone,
      qualityTitle: quality.title, ratio: null, feedbackAvailable: false, warning: "",
      primaryLabel: `${paused ? "Resume" : "Pause"} ${playbackNoun}`,
      feedbackMessage: "Feedback unavailable."
    };
    const unavailableQuality = (title, pending = false) => {
      view.qualityLabel = pending ? "Quality pending" : "Quality unavailable";
      view.qualityTone = "muted";
      view.qualityTitle = title;
    };

    // Safety states take priority over stored values from the last successful poll.
    if (requestError) {
      view.playbackLabel = "Connection lost";
      view.playbackDetail = "Cannot reach the local Agent. Check that its server is running.";
      unavailableQuality("No current quality result is available while the Agent is unreachable.");
      view.warning = "Agent connection lost. Current feedback is hidden.";
    } else if (sourceKind === "unknown") {
      unavailableQuality("Current signal quality cannot be confirmed for an unverified data source.");
      view.warning = "Source metadata is missing or unrecognized. Current feedback is hidden.";
    } else if (sourceKind === "live_device" && stream.connected !== true) {
      const connecting = stream.status === "starting" || stream.status === "connecting";
      view.playbackLabel = connecting ? "Connecting to device" : "Device disconnected";
      view.playbackDetail = "Waiting for a device connection; previous values are not live feedback.";
      view.modeDescription = "Device mode selected; no active device connection.";
      unavailableQuality("No current signal-quality result is available without a device connection.", connecting);
      view.warning = connecting ? "Waiting for a NeuraDock device connection." : "Device disconnected. Current feedback is hidden.";
    } else if (freshness === "stale") {
      view.playbackLabel = "Data stale";
      view.playbackDetail = "No recent samples received. Check the input connection.";
      unavailableQuality("Previous quality results are historical; no recent samples are available for a current quality check.");
      view.warning = "No recent samples. Current feedback is hidden.";
    } else if (freshness === "waiting_for_data") {
      view.playbackLabel = sourceKind === "live_device" ? "Connected · waiting for samples" : "Waiting for input";
      view.playbackDetail = "Waiting for fresh samples and a complete analysis window.";
      if (sourceKind === "live_device") view.modeDescription = "Device connected; waiting for EEG samples.";
      unavailableQuality("Waiting for fresh samples and a complete quality-checked window.", true);
      view.warning = "Waiting for fresh samples. Current feedback is unavailable.";
    } else if (!quality.allowed && (quality.tone === "warning" || quality.tone === "fail")) {
      view.warning = quality.title;
    } else if (warmup) {
      if (data.status !== "ok") unavailableQuality("Waiting for a complete quality-checked analysis window.", true);
      view.playbackLabel = "Warming up";
      view.playbackDetail = "Collecting complete, quality-passing windows for the rolling reference.";
      view.feedbackMessage = "Building the rolling reference. Feedback will appear after enough valid windows.";
    } else if (!quality.allowed) {
      view.warning = "Signal quality has not been confirmed. Current feedback is hidden.";
    } else if (data.feedback_available !== true || current.feedback_available !== true
        || !positive(current.posterior_alpha_relative)) {
      view.feedbackMessage = "Waiting for a valid Alpha estimate.";
    } else {
      view.ratio = current.posterior_alpha_relative;
      view.feedbackAvailable = true;
      view.feedbackMessage = "Alpha power relative to the rolling reference; not a relaxation score.";
    }

    if (view.warning) view.feedbackMessage = view.warning;
    if (paused) {
      view.ratio = null;
      view.feedbackAvailable = false;
      view.playbackLabel = "Display paused";
      view.playbackDetail = sourceKind === "live_device"
        ? "Display paused; device acquisition may continue. Resume to request fresh values."
        : "Display paused. Historical values remain visible; resume to request fresh values.";
      view.feedbackMessage = view.warning || "Display paused. Current feedback is hidden.";
    }
    return view;
  }

  /** Last 60 source seconds, ordered by time; rejected values stay null gaps. */
  function seriesFrom(payload) {
    const data = object(payload);
    const profile = object(data.profile);
    const sampleRate = profile.sampling_rate_hz;
    const points = (Array.isArray(data.history) ? data.history : []).map(item => {
      const point = object(item);
      const time = finite(point.time_sec) ? point.time_sec
        : finite(point.sample_index) && positive(sampleRate) ? point.sample_index / sampleRate : null;
      const value = point.quality_status === "pass" && point.feedback_available === true
        && positive(point.posterior_alpha_relative) ? point.posterior_alpha_relative : null;
      return { time, value };
    }).filter(point => finite(point.time) && point.time >= 0).sort((a, b) => a.time - b.time);
    if (!points.length) return [];
    const start = points[points.length - 1].time - 60;
    return points.filter(point => point.time >= start);
  }

  function portNumber(value, label) {
    if (!(typeof value === "number" || typeof value === "string")
        || (typeof value === "string" && !/^[0-9]+$/.test(value))) {
      throw new Error(`${label} must be an integer from 1 to 65535.`);
    }
    const port = Number(value);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error(`${label} must be an integer from 1 to 65535.`);
    }
    return port;
  }

  /** Builds text only. Does not execute a command or initiate a connection. */
  function connectionCommand(host, port, dashboardPort) {
    if (typeof host === "string" && /[:\[\]]/.test(host)) {
      throw new Error("IPv6 is not supported by the current device transport. Enter an IPv4 address or hostname, without a port.");
    }
    if (typeof host !== "string" || !host || host.length > 253 || !/^[A-Za-z0-9.-]+$/.test(host)) {
      throw new Error("Host must be an IPv4 address or hostname without spaces or shell characters.");
    }
    if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$/.test(host)) {
      throw new Error("Enter a valid hostname or IPv4 address; labels cannot start or end with a hyphen.");
    }
    if (/^[0-9.]+$/.test(host) && (host.split(".").length !== 4
        || host.split(".").some(part => part.length > 3 || Number(part) > 255))) {
      throw new Error("Enter a complete IPv4 address with four numbers from 0 to 255.");
    }
    const devicePort = portNumber(port, "Device port");
    const uiPort = portNumber(dashboardPort, "Dashboard port");
    return `python -m neuradock_agent online --ip ${host} --port ${devicePort} --dashboard-port ${uiPort}`;
  }

  return Object.freeze({ deriveView, seriesFrom, connectionCommand });
});
