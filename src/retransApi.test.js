import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

describe("retransApi lock", () => {
  const src = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
  const vite = readFileSync(new URL("../vite.config.js", import.meta.url), "utf8");
  const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");

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

  it("operator is 8788 same-origin /api; Vite 5173 is DEV ONLY", () => {
    assert.match(src, /const START = "\/api\/live\/start"/);
    assert.match(src, /const STOP = "\/api\/live\/stop"/);
    assert.match(src, /const STATUS = "\/api\/live\/status"/);
    assert.match(src, /const CREDENTIALS = "\/api\/live\/credentials"/);
    assert.match(src, /const PREVIEW = "\/api\/live\/preview"/);
    assert.match(src, /fetch\(START/);
    assert.match(src, /fetch\(STOP/);
    assert.match(src, /fetch\(STATUS/);
    assert.match(src, /fetch\(CREDENTIALS/);
    assert.match(src, /fetch\(`\$\{PREVIEW\}\?\$\{qs\}`/);
    assert.doesNotMatch(src, /http:\/\/127\.0\.0\.1:5173/);
    assert.doesNotMatch(src, /http:\/\/127\.0\.0\.1:8788\/api/);
    assert.doesNotMatch(html, /:5173/);
    assert.doesNotMatch(html, /http:\/\/127\.0\.0\.1:8788\/api/);
    assert.match(vite, /base:\s*["']\.\/["']/);
    assert.match(vite, /const BACKEND = "http:\/\/127\.0\.0\.1:8788"/);
    assert.match(readme, /Open http:\/\/127\.0\.0\.1:8788/);
    assert.match(readme, /Operator open path is \*\*http:\/\/127\.0\.0\.1:8788\*\* only/);
    assert.match(readme, /DEV ONLY/);
    assert.match(readme, /proxies \/api → http:\/\/127\.0\.0\.1:8788/);
    assert.doesNotMatch(readme, /Open http:\/\/127\.0\.0\.1:5173/);
    assert.doesNotMatch(readme, /open the Vite URL/);
  });

  it("shell does not clip helpers with overflow:hidden", () => {
    assert.doesNotMatch(css, /html,\s*body\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /#app\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /\.body\s*\{[^}]*overflow:\s*hidden/s);
  });
});

