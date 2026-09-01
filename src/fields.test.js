import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseSourceUrl } from "./sourceUrl.js";
import {
  SOURCE_PLACEHOLDER,
  applyPreviewSource,
  readField,
  sameSourceValue,
  writeField,
  writeSourceIfNeeded,
} from "./fields.js";

const WATCH = "https://www.youtube.com/watch?v=jfKfPfyJRdk";
const LIVE_PATH = "https://www.youtube.com/live/abcdefghijk";

function fakeInput({ value = "", placeholder = SOURCE_PLACEHOLDER } = {}) {
  return {
    value,
    getAttribute(name) {
      return name === "placeholder" ? placeholder : null;
    },
  };
}

/** Preview path: read typed value; apply result.source_url / parsed.href only if wrong. */
function runPreviewPath(el, result) {
  const parsed = parseSourceUrl(readField(el));
  return applyPreviewSource(el, result, parsed);
}

describe("writeField / readField", () => {
  it("readField is el.value", () => {
    const el = fakeInput({ value: WATCH });
    assert.equal(readField(el), el.value);
    assert.equal(readField(el), WATCH);
  });

  it("writeField replaces, never appends, never doubles a URL", () => {
    const el = fakeInput({ value: "" });
    writeField(el, WATCH);
    assert.equal(el.value, WATCH);
    writeField(el, WATCH);
    assert.equal(el.value, WATCH);
    writeField(el, WATCH + WATCH);
    assert.equal(el.value, WATCH);
    writeField(el, el.value + WATCH);
    assert.equal(el.value, WATCH);
    assert.equal(el.value.includes(WATCH + WATCH), false);
    assert.doesNotMatch(el.value, /https:\/\/www\.youtube\.com\/watch\?v=jfKfPfyJRdkhttps:\/\//);
  });

  it("does not write placeholder text over a typed URL", () => {
    const el = fakeInput({ value: WATCH, placeholder: SOURCE_PLACEHOLDER });
    writeField(el, SOURCE_PLACEHOLDER);
    assert.equal(el.value, WATCH);
    assert.equal(el.getAttribute("placeholder"), SOURCE_PLACEHOLDER);
  });

  it("placeholder stays exact when value is empty", () => {
    const el = fakeInput({ value: "", placeholder: SOURCE_PLACEHOLDER });
    writeField(el, "");
    assert.equal(el.value, "");
    assert.equal(el.getAttribute("placeholder"), "Paste YouTube URL");
    assert.equal(el.getAttribute("placeholder"), SOURCE_PLACEHOLDER);
  });

  it("RTMP fields still replace/clear via value (no placeholder concat)", () => {
    const rtmp = fakeInput({ value: "rtmps://a.media.example/live", placeholder: "" });
    writeField(rtmp, "rtmps://b.media.example/live");
    assert.equal(readField(rtmp), "rtmps://b.media.example/live");
    writeField(rtmp, "rtmps://b.media.example/live");
    assert.equal(rtmp.value, "rtmps://b.media.example/live");
    writeField(rtmp, "");
    assert.equal(rtmp.value, "");
    writeField(rtmp, "rtmps://a.media.example/live");
    assert.equal(rtmp.value, "rtmps://a.media.example/live");
    assert.equal(rtmp.getAttribute("placeholder"), "");
  });
});

describe("Preview path does not double the URL", () => {
  it("second applyPreviewSource / runPreview with the same URL leaves el.value unchanged", () => {
    const el = fakeInput({ value: WATCH });
    const parsed = parseSourceUrl(readField(el));
    const result = { ok: true, source_url: WATCH, title: "lofi hip hop radio", is_live: true };

    assert.equal(runPreviewPath(el, result), WATCH);
    assert.equal(el.value, WATCH);

    const afterFirst = el.value;
    assert.equal(runPreviewPath(el, result), afterFirst);
    assert.equal(applyPreviewSource(el, result, parsed), WATCH);
    assert.equal(writeSourceIfNeeded(el, result.source_url), WATCH);
    assert.equal(writeSourceIfNeeded(el, parsed.href), WATCH);
    assert.equal(el.value, WATCH);
    assert.equal(el.value, afterFirst);
    assert.equal(sameSourceValue(el.value, WATCH), true);
    assert.equal(el.value.includes(WATCH + WATCH), false);
  });

  it("does not append result.source_url or parsed.href onto an input that already has that URL", () => {
    const el = fakeInput({ value: LIVE_PATH });
    const parsed = parseSourceUrl(readField(el));
    applyPreviewSource(el, { source_url: parsed.href }, parsed);
    applyPreviewSource(el, { source_url: parsed.href }, parsed);
    assert.equal(el.value, LIVE_PATH);
    assert.notEqual(el.value, LIVE_PATH + parsed.href);
    assert.notEqual(el.value, parsed.href + parsed.href);
  });

  it("writes only when the stored value is actually wrong or empty", () => {
    const empty = fakeInput({ value: "" });
    writeSourceIfNeeded(empty, WATCH);
    assert.equal(empty.value, WATCH);

    const typed = fakeInput({ value: WATCH });
    writeSourceIfNeeded(typed, parseSourceUrl(WATCH).href);
    assert.equal(typed.value, WATCH);

    const wrong = fakeInput({ value: "https://example.com/not-yt" });
    writeSourceIfNeeded(wrong, WATCH);
    assert.equal(wrong.value, WATCH);
  });
});

describe("fields wiring lock", () => {
  it("main reads/writes via fields; runPreview does not rewrite source; never +=", () => {
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const fields = readFileSync(new URL("./fields.js", import.meta.url), "utf8");
    const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

    assert.match(main, /from "\.\/fields\.js"/);
    assert.match(main, /writeSourceIfNeeded\(els\.source, result\.source_url\)/);
    assert.match(fields, /export function readField/);
    assert.match(fields, /export function writeField/);
    assert.match(fields, /el\.value = value/);
    assert.doesNotMatch(fields, /\.value\s*\+=/);
    assert.doesNotMatch(main, /\.value\s*\+=/);
    assert.doesNotMatch(main, /els\.source\.value\s*=\s*result\.source_url/);
    const previewStart = main.indexOf("async function runPreview(");
    const previewEnd = main.indexOf("\nfunction ", previewStart + 1);
    const previewFn = main.slice(previewStart, previewEnd);
    assert.match(previewFn, /readField\(els\.source\)/);
    assert.doesNotMatch(previewFn, /writeField/);
    assert.doesNotMatch(previewFn, /writeSourceIfNeeded/);
    assert.doesNotMatch(previewFn, /els\.source\.value\s*=/);
    assert.doesNotMatch(main, /els\.source\.value\s*=\s*["']Paste YouTube live URL["']/);
    assert.doesNotMatch(main, /\.placeholder\s*=/);
    assert.doesNotMatch(fields, /\.placeholder\s*=/);
    assert.match(html, /placeholder="Paste YouTube URL"/);
    assert.match(css, /:not\(:placeholder-shown\)::placeholder/);
    assert.match(css, /#source_url/);
  });
});
