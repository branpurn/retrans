import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { attachPlayer, NAMED_TEE, OUTBOUND_LABEL, outboundSrc, playerShouldAttach } from "./player.js";

function fakeVideo() {
  const attrs = {};
  const classes = new Set(["outbound-player", "hidden"]);
  return {
    pause() {},
    load() {},
    getAttribute(name) {
      return attrs[name] ?? null;
    },
    setAttribute(name, value) {
      attrs[name] = String(value);
    },
    removeAttribute(name) {
      delete attrs[name];
    },
    classList: {
      add(name) {
        classes.add(name);
      },
      remove(name) {
        classes.delete(name);
      },
      contains(name) {
        return classes.has(name);
      },
    },
    _attrs: attrs,
  };
}

describe("outbound player", () => {
  it("attaches only while Retrans is starting or live", () => {
    assert.equal(playerShouldAttach({ backend: "starting" }), true);
    assert.equal(playerShouldAttach({ backend: "live" }), true);
    assert.equal(playerShouldAttach({ backend: "idle" }), false);
    assert.equal(playerShouldAttach({ backend: "stopped" }), false);
    assert.equal(playerShouldAttach({ backend: "error" }), false);
    assert.equal(playerShouldAttach({ backend: "preview" }), false);
    assert.equal(
      playerShouldAttach({ backend: "idle", sessions: [{ state: "live" }] }),
      true,
    );
    assert.equal(
      playerShouldAttach({ backend: "idle", sessions: [{ state: "starting" }] }),
      true,
    );
    assert.equal(
      playerShouldAttach({ backend: "idle", sessions: [{ state: "stopped" }] }),
      false,
    );
  });

  it("leaves src empty until a same-origin tee is named; never YouTube or thumbs", () => {
    assert.equal(NAMED_TEE, "");
    assert.equal(OUTBOUND_LABEL, "Outbound");
    assert.equal(outboundSrc(), "");
    assert.equal(outboundSrc(""), "");
    assert.equal(outboundSrc("https://www.youtube.com/watch?v=jfKfPfyJRdk"), "");
    assert.equal(outboundSrc("https://youtu.be/jfKfPfyJRdk"), "");
    assert.equal(outboundSrc("https://i.ytimg.com/vi/abc/hqdefault.jpg"), "");
    assert.equal(outboundSrc("/api/live/preview"), "");
    assert.equal(outboundSrc("http://0.0.0.0:8788/api/live/monitor.m3u8"), "");
    assert.equal(outboundSrc("http://127.0.0.1:5173/out.m3u8"), "");
    assert.equal(outboundSrc("//evil.example/x"), "");
    assert.equal(outboundSrc("/api/live/monitor.m3u8"), "/api/live/monitor.m3u8");
    assert.equal(
      outboundSrc("http://127.0.0.1:8788/api/live/out.ts"),
      "/api/live/out.ts",
    );
  });

  it("shows <video> without wiring a fake src; hides and clears when idle", () => {
    const video = fakeVideo();
    let next = attachPlayer(video, { attach: true, src: NAMED_TEE });
    assert.equal(next.attached, true);
    assert.equal(next.src, "");
    assert.equal(video.getAttribute("src"), null);
    assert.equal(video.getAttribute("poster"), null);
    assert.equal(video.classList.contains("hidden"), false);

    next = attachPlayer(video, { attach: false, src: NAMED_TEE });
    assert.equal(next.attached, false);
    assert.equal(next.src, "");
    assert.equal(video.getAttribute("src"), null);
    assert.equal(video.classList.contains("hidden"), true);

    next = attachPlayer(video, { attach: true, src: "/api/live/monitor.m3u8" });
    assert.equal(next.attached, true);
    assert.equal(next.src, "/api/live/monitor.m3u8");
    assert.equal(video.getAttribute("src"), "/api/live/monitor.m3u8");
  });

  it("chrome is HTML5 video + audio on Beat 3; no YouTube embed, clip, or extra routes", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
    const beat3 = html.slice(html.indexOf('id="beat-3"'));
    assert.match(beat3, />Outbound</);
    assert.match(beat3, /<video\b[^>]*id="outbound-player"/);
    assert.match(beat3, /<video\b[^>]*controls/);
    assert.match(beat3, /<video\b[^>]*playsinline/);
    assert.doesNotMatch(beat3, /\bmuted\b/);
    assert.doesNotMatch(beat3, /\bposter=/);
    assert.doesNotMatch(beat3, /<iframe\b/);
    assert.doesNotMatch(html, /youtube\.com\/embed/);
    assert.doesNotMatch(html, /YT\.Player/);
    assert.doesNotMatch(main, /iframe/);
    assert.doesNotMatch(main, /youtube\.com/);
    assert.doesNotMatch(main, /YT\.Player/);
    assert.doesNotMatch(html, /\b[Cc]lip\b/);
    assert.doesNotMatch(main, /\/api\/clip/);
    assert.match(html, /id="playlist-now"/);
    assert.match(html, /id="stop-btn"[^>]*>Stop</s);
    assert.match(html, />Keys \/ Configuration</);
    assert.match(css, /\.outbound-player/);
    assert.match(main, /attachPlayer/);
    assert.match(main, /playerShouldAttach/);
    assert.match(main, /NAMED_TEE/);
    assert.match(main, /OUTBOUND_LABEL/);
    assert.match(main, /sess\.outbound_url/);
    assert.doesNotMatch(main, /video\.src\s*=\s*.*source_url/);
    assert.doesNotMatch(main, /preview-thumb.*outbound-player/);
    assert.doesNotMatch(api, /\/api\/live\/monitor/);
    assert.doesNotMatch(api, /\/api\/live\/tee/);
    assert.doesNotMatch(api, /\/api\/live\/hls/);
    assert.match(api, /fetch\(START/);
    assert.match(api, /fetch\(STATUS/);
  });
});
