import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  backendFromResult,
  canContinue,
  canStart,
  canStop,
  isUsableStatus,
  nextChrome,
  pillFor,
  pillLabel,
  transportHelper,
} from "./enablement.js";
import { redactSecrets } from "./retransApi.js";

function chromePill(result, previewOk = false) {
  return pillLabel(pillFor({ previewOk, state: backendFromResult(result) }));
}

const ready = {
  previewOk: true,
  configured: true,
  ack: true,
  state: "idle",
  selectedKeyId: "key-a",
};

describe("enablement", () => {
  it("Continue needs a source (playlistReady remap), unused named key, and ack", () => {
    assert.equal(canContinue(ready), true);
    assert.equal(canContinue({ ...ready, previewOk: false }), false);
    assert.equal(canContinue({ ...ready, selectedKeyId: "" }), false);
    assert.equal(canContinue({ ...ready, ack: false }), false);
    assert.equal(canContinue({ previewOk: true, configured: true, ack: true }), true);
  });

  it("Start needs a source (playlistReady remap), unused key, ack, and that key not busy", () => {
    assert.equal(canStart(ready), true);
    assert.equal(canStart({ ...ready, previewOk: false }), false);
    assert.equal(canStart({ ...ready, selectedKeyId: "" }), false);
    assert.equal(canStart({ ...ready, ack: false }), false);
    assert.equal(canStart({ ...ready, selectedBusy: true }), false);
    assert.equal(canStart({ ...ready, state: "error" }), true);
    assert.equal(
      canStart({ previewOk: true, configured: true, ack: true, state: "live" }),
      false,
    );
    assert.equal(
      canStart({ previewOk: true, configured: true, ack: true, state: "starting" }),
      false,
    );
  });

  it("Stop when LIVE or Error", () => {
    assert.equal(canStop({ state: "live" }), true);
    assert.equal(canStop({ state: "error" }), true);
    assert.equal(canStop({ state: "starting" }), false);
    assert.equal(canStop({ state: "idle" }), false);
    assert.equal(canStop({ state: "stopped" }), false);
  });

  it("pills stay in the locked set", () => {
    assert.equal(pillLabel(pillFor({ previewOk: false, state: "idle" })), "Idle");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "idle" })), "Preview");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "starting" })), "Starting");
    assert.equal(pillFor({ previewOk: true, state: "starting" }), "starting");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "live" })), "LIVE");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "stopped" })), "Stopped");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "error" })), "Error");
  });

  it("start HTTP 400 flips the pill to Error even without state", () => {
    const result = { ok: false, error: "invalid fields", httpStatus: 400 };
    assert.equal(backendFromResult(result), "error");
    assert.equal(chromePill(result, true), "Error");
    assert.equal(chromePill({ ok: false, httpStatus: 400 }, false), "Error");
  });

  it("status error string flips the pill to Error", () => {
    const result = {
      ok: true,
      state: "idle",
      error: "ffmpeg restream exited",
      httpStatus: 200,
    };
    assert.equal(isUsableStatus(result), true);
    assert.equal(backendFromResult(result), "error");
    assert.equal(chromePill(result, true), "Error");
    assert.equal(chromePill({ ok: true, state: "error", error: "boom", httpStatus: 200 }, true), "Error");
  });

  it("mid-restream death status {state:error,error} shows unchanged in Error helper", () => {
    const error = "ffmpeg restream exited";
    const result = { ok: true, state: "error", error, httpStatus: 200 };
    assert.equal(isUsableStatus(result), true);
    assert.equal(backendFromResult(result), "error");
    assert.equal(chromePill(result, true), "Error");
    // Server already redacts secrets; helper shows the clear string unchanged.
    assert.equal(transportHelper({ backend: "error", error }), error);
    assert.equal(
      transportHelper({
        backend: "error",
        error: redactSecrets(error, ["rtmps://a.media.example/live", "streamkey"]),
      }),
      error,
    );
  });

  it("idle GET {error:null} stays Idle/Preview, not Error", () => {
    const result = { ok: true, state: "idle", error: null, httpStatus: 200 };
    assert.equal(isUsableStatus(result), true);
    assert.equal(backendFromResult(result), "idle");
    assert.equal(chromePill(result, false), "Idle");
    assert.equal(chromePill(result, true), "Preview");
    assert.equal(chromePill({ ok: true, state: "idle", error: "", httpStatus: 200 }, false), "Idle");
  });

  it("status poll/boot failure stays Idle — not Error / status failed", () => {
    const failed = [
      { ok: false, state: "error", error: "status failed", httpStatus: 502 },
      { ok: false, error: "bad-response", httpStatus: 502 },
      { ok: false, state: "error", error: "", httpStatus: 503 },
      null,
      undefined,
    ];
    for (const result of failed) {
      assert.equal(isUsableStatus(result), false);
      const stuck = nextChrome(
        { backend: "error", error: "source is not a live stream (not_live); VOD and clips are rejected" },
        result,
        "status",
      );
      assert.equal(stuck.backend, "error");
      assert.match(stuck.error, /not a live stream/);
    }
    // Chrome stays Idle; transport helper stays the idle copy (applyStatus no-ops).
    assert.equal(pillLabel(pillFor({ previewOk: false, state: "idle" })), "Idle");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "idle" })), "Preview");
    assert.equal(
      transportHelper({ backend: "idle", error: "" }),
      "Idle until ready",
    );

    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    assert.match(main, /isUsableStatus/);
    assert.match(main, /applyStatus/);
    assert.match(main, /transportHelper/);
    assert.doesNotMatch(main, /error\s*=\s*["']status failed["']/);
    assert.doesNotMatch(api, /["']status failed["']/);
    assert.doesNotMatch(main, /\/api\/clip/);
    assert.doesNotMatch(api, /\/api\/clip/);
  });

  it("start 400 NotLiveError shows unchanged in Error transport helper", () => {
    const messages = [
      "source is not a live stream (not_live); VOD and clips are rejected",
      "source is not a live stream (was_live); VOD and clips are rejected",
      "source is not a live stream (is_upcoming); VOD and clips are rejected",
      "could not confirm live stream (VOD / not live): yt-dlp exit 1",
    ];
    for (const error of messages) {
      const result = { ok: false, error, httpStatus: 400 };
      assert.equal(backendFromResult(result), "error");
      assert.equal(chromePill(result, true), "Error");
      const shown = transportHelper({
        backend: "error",
        error: redactSecrets(error, ["rtmps://a.media.example/live", "streamkey"]),
      });
      assert.equal(shown, error);
    }
  });

  it("start 400 NotLiveError then idle status keeps Error; Stop may leave", () => {
    const notLive =
      "source is not a live stream (not_live); VOD and clips are rejected";
    const start400 = { ok: false, error: notLive, httpStatus: 400 };
    let chrome = nextChrome({ backend: "idle", error: "" }, start400, "command");
    assert.equal(chrome.backend, "error");
    assert.equal(chrome.error, notLive);
    assert.equal(pillLabel(pillFor({ previewOk: true, state: chrome.backend })), "Error");
    assert.equal(transportHelper(chrome), notLive);
    assert.equal(canStart({ ...ready, state: chrome.backend }), true);
    assert.equal(canStop({ state: chrome.backend }), true);

    const idle = { ok: true, state: "idle", error: null, httpStatus: 200 };
    assert.equal(isUsableStatus(idle), true);
    assert.equal(backendFromResult(idle), "idle");
    chrome = nextChrome(chrome, idle, "status");
    assert.equal(chrome.backend, "error");
    assert.equal(chrome.error, notLive);
    assert.equal(pillLabel(pillFor({ previewOk: true, state: chrome.backend })), "Error");
    assert.equal(transportHelper(chrome), notLive);

    const stopped = { ok: true, state: "stopped", error: null, httpStatus: 200 };
    chrome = nextChrome(chrome, stopped, "command");
    assert.equal(chrome.backend, "stopped");
    assert.notEqual(chrome.backend, "error");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: chrome.backend })), "Stopped");
    assert.equal(transportHelper(chrome), "Idle until ready");
  });

  it("Error helper redacts rtmp secrets only", () => {
    const error =
      "source is not a live stream (not_live); VOD and clips are rejected near rtmps://a.media.example/live key streamkey";
    const shown = transportHelper({
      backend: "error",
      error: redactSecrets(error, ["rtmps://a.media.example/live", "streamkey"]),
    });
    assert.match(shown, /source is not a live stream \(not_live\); VOD and clips are rejected/);
    assert.doesNotMatch(shown, /rtmps?:\/\//);
    assert.doesNotMatch(shown, /streamkey/);
    assert.match(shown, /\[redacted/);
  });
});
