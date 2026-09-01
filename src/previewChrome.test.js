import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseSourceUrl } from "./sourceUrl.js";
import { redactSecrets } from "./retransApi.js";
import {
  canContinue,
  canStart,
  pillFor,
  pillLabel,
} from "./enablement.js";
import {
  YOUTUBE_FIRST_HELPER,
  isPreviewProbeFail,
  previewHelperCopy,
  previewPaint,
} from "./previewChrome.js";

const LIVE = "https://www.youtube.com/watch?v=jfKfPfyJRdk";
const LIVE_PATH = "https://www.youtube.com/live/abcdefghijk";
const VOD = "https://www.youtube.com/watch?v=dQw4w9wgGcQ";

const ready = {
  previewOk: true,
  configured: true,
  ack: true,
  state: "idle",
  selectedKeyId: "key-a",
};

describe("preview 502 chrome (primary-flow.md)", () => {
  it("502 {ok:false, error} → helper as-is, hide card, no LIVE, Continue disabled, pill Idle", () => {
    const parsed = parseSourceUrl(LIVE);
    assert.match(parsed.thumbnail, /hqdefault/);
    const error = "yt-dlp preview probe failed: This live stream recording is not available.";
    const result = {
      ok: false,
      httpStatus: 502,
      error,
      title: "",
      is_live: false,
    };
    const paint = previewPaint({ parsed, result });
    assert.equal(isPreviewProbeFail(result), true);
    assert.equal(paint.previewOk, false);
    assert.equal(paint.showCard, false);
    assert.equal(paint.thumbnail, "");
    assert.equal(paint.title, "");
    assert.equal(paint.showLiveBadge, false);
    assert.equal(paint.helper, error);
    assert.equal(canContinue({ ...ready, previewOk: paint.previewOk }), false);
    assert.equal(canStart({ ...ready, previewOk: paint.previewOk }), false);
    assert.equal(pillLabel(pillFor({ previewOk: paint.previewOk, state: "idle" })), "Idle");
    assert.notEqual(pillLabel(pillFor({ previewOk: paint.previewOk, state: "idle" })), "Error");
  });

  it("502 Error helper redacts rtmp secrets only — no invented copy", () => {
    const error =
      "yt-dlp preview probe failed: unavailable near rtmps://a.media.example/live key streamkey";
    const shown = redactSecrets(error, ["rtmps://a.media.example/live", "streamkey"]);
    const paint = previewPaint({
      parsed: parseSourceUrl(LIVE),
      result: { ok: false, httpStatus: 502, error: shown, title: "", is_live: false },
    });
    assert.equal(paint.helper, shown);
    assert.match(paint.helper, /yt-dlp preview probe failed: unavailable/);
    assert.doesNotMatch(paint.helper, /rtmps?:\/\//);
    assert.doesNotMatch(paint.helper, /streamkey/);
    assert.doesNotMatch(paint.helper, /status failed/);
    assert.equal(paint.showCard, false);
    assert.equal(paint.showLiveBadge, false);
    assert.equal(previewHelperCopy({ error: shown }), shown);
  });

  it("ok:false httpStatus 502 never paints empty title + hqdefault or fake LIVE", () => {
    const parsed = parseSourceUrl(LIVE_PATH);
    assert.equal(parsed.isLive, true);
    assert.match(parsed.thumbnail, /hqdefault/);
    const cases = [
      {
        ok: false,
        httpStatus: 502,
        error: "yt-dlp preview probe failed: unavailable",
        title: "",
        is_live: true,
      },
      {
        ok: false,
        httpStatus: 502,
        error: "yt-dlp preview probe failed: This live stream recording is not available.",
        title: "",
        is_live: false,
      },
      {
        ok: false,
        httpStatus: 200,
        error: "yt-dlp preview probe failed: empty json",
        title: "",
        is_live: false,
      },
    ];
    for (const result of cases) {
      const paint = previewPaint({ parsed, result });
      assert.equal(isPreviewProbeFail(result), true);
      assert.equal(paint.previewOk, false);
      assert.equal(paint.showCard, false);
      assert.equal(paint.thumbnail, "");
      assert.equal(paint.showLiveBadge, false);
      assert.equal(paint.title, "");
      assert.equal(paint.helper, result.error);
    }
  });

  it("HTTP 502 with a lying ok:true / is_live body still hides the card", () => {
    const paint = previewPaint({
      parsed: parseSourceUrl(LIVE),
      result: {
        ok: true,
        httpStatus: 502,
        title: "",
        is_live: true,
        error: "yt-dlp preview probe failed: unavailable",
      },
    });
    assert.equal(paint.previewOk, false);
    assert.equal(paint.showCard, false);
    assert.equal(paint.thumbnail, "");
    assert.equal(paint.showLiveBadge, false);
    assert.equal(paint.helper, "yt-dlp preview probe failed: unavailable");
    assert.equal(pillLabel(pillFor({ previewOk: paint.previewOk, state: "idle" })), "Idle");
  });

  it("preview 502 does not flip the status pill to Error", () => {
    const paint = previewPaint({
      parsed: parseSourceUrl(LIVE),
      result: { ok: false, httpStatus: 502, error: "yt-dlp preview probe failed: unavailable" },
    });
    assert.equal(pillLabel(pillFor({ previewOk: paint.previewOk, state: "idle" })), "Idle");
    assert.equal(pillLabel(pillFor({ previewOk: false, state: "error" })), "Error");
  });
});

describe("preview 200 + youtube-first stay locked", () => {
  it("200 ok empty title still host-only / empty card (not the 502 hide rule)", () => {
    const parsed = parseSourceUrl(LIVE);
    const paint = previewPaint({
      parsed,
      result: { ok: true, httpStatus: 200, title: "", is_live: true },
    });
    assert.equal(paint.previewOk, true);
    assert.equal(paint.showCard, true);
    assert.equal(paint.title, "");
    assert.equal(paint.host, parsed.host);
    assert.equal(paint.showLiveBadge, true);
    assert.equal(paint.helper, "");
  });

  it("VOD 200 is_live false still shows card + title, no badge", () => {
    const parsed = parseSourceUrl(VOD);
    const paint = previewPaint({
      parsed,
      result: { ok: true, httpStatus: 200, title: "VOD title", is_live: false },
    });
    assert.equal(paint.previewOk, true);
    assert.equal(paint.showCard, true);
    assert.equal(paint.title, "VOD title");
    assert.equal(paint.showLiveBadge, false);
    assert.equal(paint.helper, "");
  });

  it("200 live shows real title + LIVE badge", () => {
    const paint = previewPaint({
      parsed: parseSourceUrl(LIVE),
      result: {
        ok: true,
        httpStatus: 200,
        title: "lofi hip hop radio",
        is_live: true,
      },
    });
    assert.equal(paint.previewOk, true);
    assert.equal(paint.showCard, true);
    assert.equal(paint.title, "lofi hip hop radio");
    assert.equal(paint.showLiveBadge, true);
    assert.equal(paint.helper, "");
  });

  it("youtube-first helper is exact; no card", () => {
    const paint = previewPaint({
      parsed: parseSourceUrl("https://example.com/live"),
      result: null,
    });
    assert.equal(paint.helper, YOUTUBE_FIRST_HELPER);
    assert.equal(paint.helper, "YouTube first");
    assert.equal(paint.previewOk, false);
    assert.equal(paint.showCard, false);
    assert.equal(paint.thumbnail, "");
    assert.equal(paint.showLiveBadge, false);
  });
});

describe("preview 502 wiring lock", () => {
  it("main consumes previewPaint; 502 is helper chrome not Error pill; no clip", () => {
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    const design = readFileSync(new URL("../design/primary-flow.md", import.meta.url), "utf8");
    assert.match(design, /502.*ok:\s*false.*error/s);
    assert.match(design, /do \*\*not\*\* flip the status pill to Error/);
    assert.match(main, /previewPaint/);
    assert.match(main, /isPreviewProbeFail/);
    assert.match(main, /pasteHelper/);
    assert.match(html, /id="paste-helper"/);
    assert.match(main, /removeAttribute\("src"\)/);
    assert.doesNotMatch(main, /status failed/);
    assert.match(api, /httpStatus:\s*res\.status/);
    assert.match(api, /\/api\/live\/preview/);
    assert.doesNotMatch(api, /\/api\/clip/);
    assert.doesNotMatch(main, /\/api\/clip/);
  });
});
