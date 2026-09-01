import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseSourceUrl } from "./sourceUrl.js";

describe("parseSourceUrl", () => {
  it("accepts a YouTube watch URL", () => {
    const parsed = parseSourceUrl("https://www.youtube.com/watch?v=dQw4w9wgGcQ");
    assert.equal(parsed.ok, true);
    assert.equal(parsed.videoId, "dQw4w9wgGcQ");
    assert.equal(parsed.host, "www.youtube.com");
    assert.equal(parsed.isLive, false);
    assert.equal(parsed.title, "");
    assert.match(parsed.thumbnail, /dQw4w9wgGcQ/);
  });

  it("marks /live paths as live without a synthetic display title", () => {
    const parsed = parseSourceUrl("https://www.youtube.com/live/abcdefghijk");
    assert.equal(parsed.ok, true);
    assert.equal(parsed.isLive, true);
    assert.equal(parsed.videoId, "abcdefghijk");
    assert.equal(parsed.title, "");
  });

  it("does not invent YouTube source / YouTube live display titles", () => {
    const src = readFileSync(new URL("./sourceUrl.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /YouTube source/);
    assert.doesNotMatch(src, /YouTube live/);
    const watch = parseSourceUrl("https://www.youtube.com/watch?v=dQw4w9wgGcQ");
    const live = parseSourceUrl("https://www.youtube.com/live/abcdefghijk");
    const short = parseSourceUrl("https://youtu.be/dQw4w9wgGcQ");
    assert.equal(watch.title, "");
    assert.equal(live.title, "");
    assert.equal(short.title, "");
  });

  it("accepts youtu.be", () => {
    const parsed = parseSourceUrl("https://youtu.be/dQw4w9wgGcQ");
    assert.equal(parsed.ok, true);
    assert.equal(parsed.videoId, "dQw4w9wgGcQ");
  });

  it("rejects non-YouTube with youtube-first", () => {
    const parsed = parseSourceUrl("https://example.com/watch");
    assert.equal(parsed.ok, false);
    assert.equal(parsed.reason, "youtube-first");
  });

  it("rejects empty", () => {
    assert.equal(parseSourceUrl("").ok, false);
  });
});
