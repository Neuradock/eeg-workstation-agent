"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const file = path.join(__dirname, "../src/neuradock_agent/web/assets/dashboard-state.js");
const { deriveView, seriesFrom, connectionCommand } = require(file);

function fixture(kind = "synthetic_demo") {
  return {
    status: "ok",
    source_info: { kind, is_synthetic: kind === "synthetic_demo" },
    profile: { sampling_rate_hz: 250 },
    freshness: { status: kind === "live_device" || kind === "manual_post" ? "fresh" : "not_applicable", age_sec: 1, stale_after_sec: 5 },
    feedback_available: true,
    feedback_reason: "ready",
    quality: { status: "pass", bad_channel_candidates: [] },
    current: {
      sample_index: 2500, time_sec: 10, quality_status: "pass",
      posterior_alpha_relative: 1.25, feedback_available: true,
      feedback_reason: "ready", alpha_state: "strong_alpha", baseline_history_count: 7
    },
    baseline: { history_count: 7, minimum_history_count: 3, reference: "rolling_log_median" },
    stream: { connected: true, status: "streaming" },
    history: []
  };
}

test("module supports both CommonJS and a browser global without touching the DOM", () => {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(file, "utf8"), context);
  assert.equal(typeof context.AlphaDashboardState.deriveView, "function");
  assert.equal(typeof context.AlphaDashboardState.seriesFrom, "function");
  assert.equal(typeof context.AlphaDashboardState.connectionCommand, "function");
});

test("synthetic demo is explicitly synthetic, with finite quality-gated ratio", () => {
  const view = deriveView(fixture());
  assert.equal(view.sourceKind, "synthetic_demo");
  assert.equal(view.modeLabel, "Synthetic demo");
  assert.equal(view.modeDescription, "Generated signal, not your EEG.");
  assert.equal(view.playbackLabel, "Demo running");
  assert.equal(view.ratio, 1.25);
  assert.equal(view.feedbackAvailable, true);
  assert.match(view.feedbackMessage, /not a relaxation score/);
  assert.equal(view.warning, "");
});

test("recorded replay is never labeled live or synthetic", () => {
  const view = deriveView(fixture("recorded_replay"));
  assert.equal(view.modeLabel, "Recorded replay");
  assert.equal(view.modeDescription, "Recorded data, not a live stream.");
  assert.equal(view.playbackLabel, "Replay running");
  assert.equal(view.feedbackAvailable, true);
});

test("legacy or unrecognized source names cannot imply provenance", () => {
  for (const source_info of [undefined, null, {}, { kind: "demo_file" }, { kind: "toString" }, { kind: "neuradock_tcp" }]) {
    const data = fixture();
    data.source = "neuradock_tcp";
    data.source_info = source_info;
    const view = deriveView(data);
    assert.equal(view.sourceKind, "unknown");
    assert.equal(view.modeLabel, "Unknown source");
    assert.equal(view.qualityLabel, "Quality unavailable");
    assert.equal(view.qualityTone, "muted");
    assert.equal(view.ratio, null);
    assert.equal(view.feedbackAvailable, false);
  }
});

test("manual API input is not presented as a verified device", () => {
  const view = deriveView(fixture("manual_post"));
  assert.equal(view.modeLabel, "Manual input");
  assert.match(view.modeDescription, /source not verified/);
  assert.equal(view.playbackLabel, "Receiving input");
  assert.equal(view.feedbackAvailable, true);
});

test("missing payload and initialization do not leak last-value feedback", () => {
  for (const payload of [null, undefined, [], false, "bad"]) {
    assert.equal(deriveView(payload).ratio, null);
  }
  const data = fixture();
  for (const status of ["warming_up", "waiting_for_data", "error"]) {
    data.status = status;
    const view = deriveView(data);
    assert.equal(view.ratio, null);
    assert.equal(view.feedbackAvailable, false);
    assert.equal(view.qualityLabel, "Quality pending");
    assert.equal(view.qualityTone, "muted");
  }
});

test("baseline warmup respects initialization, history count, and backend reason", () => {
  const initial = fixture();
  initial.current.alpha_state = "initializing";
  const count = fixture();
  count.baseline.history_count = 2;
  const reason = fixture();
  reason.feedback_reason = "baseline_warming_up";
  for (const data of [initial, count, reason]) {
    const view = deriveView(data);
    assert.equal(view.ratio, null);
    assert.equal(view.feedbackAvailable, false);
    assert.match(view.feedbackMessage, /rolling reference/);
  }
});

test("null, strings, NaN, Infinity, negative and zero ratios stay unavailable", () => {
  for (const value of [null, undefined, "1.2", "", NaN, Infinity, -Infinity, -0.5, 0]) {
    const data = fixture();
    data.current.posterior_alpha_relative = value;
    assert.equal(deriveView(data).ratio, null, `ratio=${String(value)}`);
    assert.equal(deriveView(data).feedbackAvailable, false);
  }
});

test("both backend feedback fields must explicitly permit current feedback", () => {
  for (const field of ["top", "current"]) {
    for (const value of [false, undefined, null, 1, "true"]) {
      const data = fixture();
      (field === "top" ? data : data.current).feedback_available = value;
      assert.equal(deriveView(data).ratio, null);
    }
  }
});

test("quality warning/failure from either source disables feedback", () => {
  for (const status of ["warning", "fail", "error", "bad"]) {
    for (const target of ["quality", "current"]) {
      const data = fixture();
      if (target === "quality") data.quality.status = status;
      else data.current.quality_status = status;
      const view = deriveView(data);
      assert.equal(view.ratio, null);
      assert.equal(view.feedbackAvailable, false);
      assert.ok(view.warning);
    }
  }
  const data = fixture();
  delete data.quality;
  assert.equal(deriveView(data).ratio, null);
});

test("passing gate with bad-channel candidates preserves explicit flag labels", () => {
  const data = fixture();
  data.quality.bad_channel_candidates = ["PO3", "PO3", "O1"];
  const view = deriveView(data);
  assert.equal(view.qualityLabel, "Quality pass · 2 flagged");
  assert.equal(view.qualityTone, "warning");
  assert.match(view.qualityTitle, /PO3, O1/);
  // The UI must not silently redefine the backend gate threshold.
  assert.equal(view.feedbackAvailable, true);
});

test("request errors suppress stored current data and do not imply current quality", () => {
  const view = deriveView(fixture(), { requestError: true });
  assert.equal(view.playbackLabel, "Connection lost");
  assert.equal(view.ratio, null);
  assert.equal(view.qualityLabel, "Quality unavailable");
  assert.equal(view.feedbackAvailable, false);
});

test("disconnected and connecting hardware suppress values from previous windows", () => {
  for (const status of ["reconnecting", "stopped", "connecting", "starting"]) {
    const data = fixture("live_device");
    data.stream = { connected: false, status };
    const view = deriveView(data);
    assert.equal(view.ratio, null);
      assert.equal(view.feedbackAvailable, false);
      assert.match(view.modeDescription, /no active device connection/);
      assert.equal(view.qualityLabel, status === "starting" || status === "connecting" ? "Quality pending" : "Quality unavailable");
      assert.equal(view.qualityTone, "muted");
  }
  const missing = fixture("live_device");
  delete missing.stream;
  assert.equal(deriveView(missing).feedbackAvailable, false);
});

test("live and manual stale status or excessive age disables current feedback", () => {
  for (const kind of ["live_device", "manual_post"]) {
    for (const freshness of [{ status: "stale" }, { status: "fresh", age_sec: 6, stale_after_sec: 5 }]) {
      const data = fixture(kind);
      data.freshness = freshness;
      assert.equal(deriveView(data).playbackLabel, "Data stale");
      assert.equal(deriveView(data).ratio, null);
      assert.equal(deriveView(data).qualityLabel, "Quality unavailable");
      assert.equal(deriveView(data).qualityTone, "muted");
    }
  }
});

test("stream Unix seconds can conservatively detect staleness, without string coercion", () => {
  const data = fixture("live_device");
  data.stream.last_sample_time = 100;
  assert.equal(deriveView(data, { nowMs: 107000 }).ratio, null);
  assert.equal(deriveView(data, { nowMs: 102000 }).ratio, 1.25);
  data.stream.last_sample_time = "100";
  assert.equal(deriveView(data, { nowMs: 107000 }).ratio, 1.25);
});

test("live requires fresh samples, not merely a connected socket", () => {
  const data = fixture("live_device");
  for (const freshness of [{ status: "waiting_for_data" }, {}, null]) {
    data.freshness = freshness;
    const view = deriveView(data);
    assert.equal(view.playbackLabel, "Connected · waiting for samples");
    assert.equal(view.modeDescription, "Device connected; waiting for EEG samples.");
    assert.equal(view.ratio, null);
    assert.equal(view.qualityLabel, "Quality pending");
    assert.equal(view.qualityTone, "muted");
  }
});

test("pausing any source hides current feedback without discarding history", () => {
  for (const kind of ["synthetic_demo", "recorded_replay", "live_device", "manual_post"]) {
    const data = fixture(kind);
    data.history = [{ ...data.current }];
    const before = structuredClone(data);
    const view = deriveView(data, { paused: true });
    assert.equal(view.playbackLabel, "Display paused");
    const noun = kind === "synthetic_demo" ? "demo" : kind === "recorded_replay" ? "replay" : "display";
    assert.equal(view.primaryLabel, `Resume ${noun}`);
    assert.equal(view.ratio, null);
    assert.equal(view.feedbackAvailable, false);
    assert.deepEqual(seriesFrom(data), [{ time: 10, value: 1.25 }]);
    assert.deepEqual(data, before);
    assert.equal(deriveView(data).primaryLabel, `Pause ${noun}`);
  }
});

test("pause retains safety warnings instead of overwriting them", () => {
  const view = deriveView(fixture(), { paused: true, requestError: true });
  assert.equal(view.playbackLabel, "Display paused");
  assert.match(view.warning, /connection lost/);
  assert.equal(view.feedbackMessage, view.warning);
});

test("series retains null gaps for invalid/quality-rejected values, never coerces to zero", () => {
  const data = fixture();
  data.history = [null, NaN, Infinity, "2", 0, -1, 1.25].map((value, index) => ({
    ...data.current, time_sec: index + 10, posterior_alpha_relative: value
  }));
  data.history.push({ ...data.current, time_sec: 17, quality_status: "warning" });
  data.history.push({ ...data.current, time_sec: 18, feedback_available: false });
  assert.deepEqual(seriesFrom(data).map(point => point.value), [null, null, null, null, null, null, 1.25, null, null]);
});

test("series keeps only last 60 source seconds, finite times, and source order", () => {
  const data = fixture();
  data.history = [100, 20, 39, 40, 90].map(time_sec => ({ ...data.current, time_sec }));
  data.history.push({ ...data.current, time_sec: NaN, sample_index: null });
  data.history.push({ ...data.current, time_sec: Infinity, sample_index: null });
  data.history.push({ ...data.current, time_sec: -1 });
  const before = structuredClone(data);
  assert.deepEqual(seriesFrom(data).map(point => point.time), [40, 90, 100]);
  assert.deepEqual(data, before);
});

test("sample indices use the declared sampling rate without a guessed rate", () => {
  const data = fixture();
  data.history = [{ ...data.current, time_sec: null, sample_index: 2500 }];
  assert.deepEqual(seriesFrom(data), [{ time: 10, value: 1.25 }]);
  data.profile = {};
  assert.deepEqual(seriesFrom(data), []);
  assert.deepEqual(seriesFrom(null), []);
});

test("connection command accepts strict endpoint text and normalizes integer ports", () => {
  assert.equal(connectionCommand("127.0.0.1", "09600", 8765), "python -m neuradock_agent online --ip 127.0.0.1 --port 9600 --dashboard-port 8765");
  assert.match(connectionCommand("eeg-device.local", 1, "65535"), /--ip eeg-device\.local --port 1 --dashboard-port 65535$/);
  assert.match(connectionCommand("localhost", 9600, 8765), /--ip localhost /);
});

test("connection command clearly rejects IPv6 unsupported by the current transport", () => {
  for (const host of ["[::1]", "::1", "2001:db8::1", "[2001:db8::1]"]) {
    assert.throws(() => connectionCommand(host, 9600, 8765), /IPv6 is not supported/);
  }
});

test("connection command rejects incomplete or out-of-range numeric IPv4", () => {
  for (const host of ["127.1", "127", "256.1.2.3", "1.2.3.4.5", "0000.1.2.3", "127.0.0.1."]) {
    assert.throws(() => connectionCommand(host, 9600, 8765), /IPv4/);
  }
});

test("connection command rejects shell injection, flags, malformed host labels, and whitespace", () => {
  for (const host of ["", null, 123, "--help", "a;whoami", "a&whoami", "$(whoami)", "`whoami`", "a b", "a\nb", "a\tb", " a", "a ", "a|b", 'a"b', "a'b", "../x", "a\\b", "a%PATH%", "a_b", "a..b", "-a", "a-", "[127.0.0.1]", "[::1", "::1]", ":::1", "a:9600", "::1%eth0"]) {
    assert.throws(() => connectionCommand(host, 9600, 8765), Error, String(host));
  }
});

test("connection command rejects all noninteger or out-of-range ports", () => {
  for (const port of [null, undefined, "", " 1", "1 ", "1;echo", "1.0", 0, -1, 65536, 1.5, NaN, Infinity, true]) {
    assert.throws(() => connectionCommand("localhost", port, 8765), /Device port/);
    assert.throws(() => connectionCommand("localhost", 9600, port), /Dashboard port/);
  }
});
