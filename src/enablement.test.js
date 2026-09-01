import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { backendFromResult, canStart, canStop, pillFor, pillLabel } from "./enablement.js";

function chromePill(result, previewOk = false) {
  return pillLabel(pillFor({ previewOk, state: backendFromResult(result) }));
}

const ready = {
  previewOk: true,
  rtmpUrl: "rtmp://a.media.example/live",
  rtmpKey: "secret",
  ack: true,
  state: "idle",
};

describe("enablement", () => {
  it("Start needs preview, dest, ack, and not LIVE", () => {
    assert.equal(canStart(ready), true);
    assert.equal(canStart({ ...ready, previewOk: false }), false);
    assert.equal(canStart({ ...ready, rtmpUrl: "" }), false);
    assert.equal(canStart({ ...ready, rtmpKey: "" }), false);
    assert.equal(canStart({ ...ready, ack: false }), false);
    assert.equal(canStart({ ...ready, state: "live" }), false);
    assert.equal(canStart({ ...ready, state: "starting" }), false);
  });

  it("Stop only when LIVE", () => {
    assert.equal(canStop({ state: "live" }), true);
    assert.equal(canStop({ state: "starting" }), false);
    assert.equal(canStop({ state: "idle" }), false);
    assert.equal(canStop({ state: "stopped" }), false);
    assert.equal(canStop({ state: "error" }), false);
  });

  it("pills stay in the locked set", () => {
    assert.equal(pillLabel(pillFor({ previewOk: false, state: "idle" })), "Idle");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "idle" })), "Preview");
    assert.equal(pillLabel(pillFor({ previewOk: true, state: "starting" })), "Preview");
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
    assert.equal(backendFromResult(result), "error");
    assert.equal(chromePill(result, true), "Error");
    assert.equal(chromePill({ ok: true, state: "error", error: "boom" }, true), "Error");
  });

  it("idle GET {error:null} stays Idle/Preview, not Error", () => {
    const result = { ok: true, state: "idle", error: null, httpStatus: 200 };
    assert.equal(backendFromResult(result), "idle");
    assert.equal(chromePill(result, false), "Idle");
    assert.equal(chromePill(result, true), "Preview");
    assert.equal(chromePill({ ok: true, state: "idle", error: "", httpStatus: 200 }, false), "Idle");
  });
});
