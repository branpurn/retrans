import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

describe("retransApi lock", () => {
  const src = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
  const vite = readFileSync(new URL("../vite.config.js", import.meta.url), "utf8");
  const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");

  it("targets the locked loopback proxy, never 0.0.0.0", () => {
    assert.match(vite, /target: BACKEND/);
    assert.match(vite, /const BACKEND = "http:\/\/127\.0\.0\.1:8788"/);
    assert.match(vite, /host: "127\.0\.0\.1"/);
    assert.doesNotMatch(vite, /host:\s*["']0\.0\.0\.0["']/);
    assert.doesNotMatch(vite, /target:\s*["'][^"']*0\.0\.0\.0/);
    assert.match(src, /\/api\/live\/start/);
    assert.match(src, /\/api\/live\/stop/);
    assert.match(src, /\/api\/live\/status/);
    assert.match(src, /\/api\/live\/credentials/);
    assert.match(src, /\/api\/live\/preview/);
    assert.match(src, /source_url/);
    assert.match(src, /rtmp_url/);
    assert.match(src, /rtmp_key/);
    assert.match(src, /method:\s*["']PUT["']/);
    assert.match(src, /method:\s*["']DELETE["']/);
    assert.doesNotMatch(src, /\/api\/clip/);
  });

  it("shell does not clip helpers with overflow:hidden", () => {
    assert.doesNotMatch(css, /html,\s*body\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /#app\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /\.body\s*\{[^}]*overflow:\s*hidden/s);
  });
});

