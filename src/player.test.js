import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  attachPlayer,
  NAMED_TEE,
  OUTBOUND_LABEL,
  OUTBOUND_WAIT,
  outboundMediaPath,
  outboundSrc,
  playerShouldAttach,
  playerShouldBindSrc,
  playlistIsReady,
  sessionOutboundSrc,
} from "./player.js";

const SID = "abc123def456";
const HLS = `/live/${SID}/index.m3u8`;

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
  it("binds picture+sound only when live and playlist 200", () => {
    assert.equal(OUTBOUND_WAIT, "Waiting");
    assert.equal(playerShouldBindSrc({ state: "starting", playlistOk: false }), false);
    assert.equal(playerShouldBindSrc({ state: "starting", playlistOk: true }), false);
    assert.equal(playerShouldBindSrc({ state: "live", playlistOk: false }), false);
    assert.equal(playerShouldBindSrc({ state: "live", playlistOk: true }), true);
    assert.equal(playerShouldBindSrc({ state: "idle", playlistOk: true }), false);
    assert.equal(playerShouldBindSrc({ state: "error", playlistOk: true }), false);
  });

  it("playlist 404/empty stays Waiting — not ready, not Error", async () => {
    const orig = globalThis.fetch;
    try {
      globalThis.fetch = async () => ({ status: 404, text: async () => "" });
      assert.equal(await playlistIsReady(HLS), false);
      globalThis.fetch = async () => ({ status: 200, text: async () => "" });
      assert.equal(await playlistIsReady(HLS), false);
      globalThis.fetch = async () => ({ status: 200, text: async () => "  \n" });
      assert.equal(await playlistIsReady(HLS), false);
      globalThis.fetch = async () => {
        throw new Error("network");
      };
      assert.equal(await playlistIsReady(HLS), false);
      globalThis.fetch = async () => ({
        status: 200,
        text: async () => "#EXTM3U\n#EXT-X-TARGETDURATION:1\n",
      });
      assert.equal(await playlistIsReady(HLS), true);
    } finally {
      globalThis.fetch = orig;
    }
    assert.equal(await playlistIsReady("/api/live/preview"), false);
    assert.equal(await playlistIsReady(""), false);
  });

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

  it("src is path-only /live/<session_id>/index.m3u8; never YouTube, preview, or thumbs", () => {
    assert.equal(NAMED_TEE, "");
    assert.equal(OUTBOUND_LABEL, "Outbound");
    assert.equal(outboundSrc(), "");
    assert.equal(outboundSrc(""), "");
    assert.equal(outboundMediaPath(SID), HLS);
    assert.equal(outboundMediaPath("not-hex"), "");
    assert.equal(outboundSrc(HLS), HLS);
    assert.equal(outboundSrc(`http://127.0.0.1:8788${HLS}`), HLS);
    assert.equal(outboundSrc("https://www.youtube.com/watch?v=jfKfPfyJRdk"), "");
    assert.equal(outboundSrc("https://youtu.be/jfKfPfyJRdk"), "");
    assert.equal(outboundSrc("https://i.ytimg.com/vi/abc/hqdefault.jpg"), "");
    assert.equal(outboundSrc("/api/live/preview"), "");
    assert.equal(outboundSrc("http://0.0.0.0:8788/live/abc123def456/index.m3u8"), "");
    assert.equal(outboundSrc("http://127.0.0.1:5173/live/abc123def456/index.m3u8"), "");
    assert.equal(outboundSrc("//evil.example/x"), "");
    assert.equal(outboundSrc("/api/live/monitor.m3u8"), "");
    assert.equal(outboundSrc("/api/live/out.ts"), "");
    assert.equal(sessionOutboundSrc({ state: "idle", outbound_url: HLS }), "");
    assert.equal(sessionOutboundSrc({ state: "live", outbound_url: HLS }), HLS);
    assert.equal(sessionOutboundSrc({ state: "starting", session_id: SID }), HLS);
    assert.equal(
      sessionOutboundSrc({
        state: "live",
        outbound_url: "/api/live/preview",
        session_id: SID,
      }),
      HLS,
    );
    assert.equal(sessionOutboundSrc({ state: "stopped", session_id: SID }), "");
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

    next = attachPlayer(video, { attach: true, src: HLS });
    assert.equal(next.attached, true);
    assert.equal(next.src, HLS);
    assert.equal(video.getAttribute("src"), HLS);
  });

  it("chrome is HTML5 video + audio on Beat 3; no YouTube embed, clip, or extra routes", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
    const beat3 = html.slice(html.indexOf('id="beat-3"'));
    assert.match(beat3, />Outbound</);
    assert.match(beat3, />Waiting</);
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
    assert.doesNotMatch(html, /id="stop-btn"/);
    assert.match(html, />Keys \/ Configuration</);
    assert.match(css, /\.outbound-player/);
    assert.match(main, /attachPlayer/);
    assert.match(main, /playerShouldAttach/);
    assert.match(main, /NAMED_TEE/);
    assert.match(main, /OUTBOUND_LABEL/);
    assert.match(main, /sessionOutboundSrc/);
    assert.match(main, /playerShouldBindSrc/);
    assert.match(main, /playlistIsReady/);
    assert.match(main, /OUTBOUND_WAIT/);
    assert.doesNotMatch(main, /state\.error\s*=\s*.*playlist/);
    assert.doesNotMatch(main, /video\.src\s*=\s*.*source_url/);
    assert.doesNotMatch(main, /preview-thumb.*outbound-player/);
    assert.doesNotMatch(api, /\/api\/live\/monitor/);
    assert.doesNotMatch(api, /\/api\/live\/tee/);
    assert.doesNotMatch(api, /\/api\/live\/hls/);
    assert.match(api, /fetch\(START/);
    assert.match(api, /fetch\(STATUS/);
    assert.match(api, /outbound_url/);
  });
});
