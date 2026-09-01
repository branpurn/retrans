import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

describe("primary-flow chrome lock", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
  const enablement = readFileSync(new URL("./enablement.js", import.meta.url), "utf8");
  const vite = readFileSync(new URL("../vite.config.js", import.meta.url), "utf8");

  it("is a 480px one-beat console, not the 720px five-block stack", () => {
    assert.match(css, /max-width:\s*480px/);
    assert.doesNotMatch(css, /720px/);
    assert.match(html, /id="beat-1"/);
    assert.match(html, /id="beat-2"/);
    assert.match(html, /id="beat-3"/);
    assert.match(css, /\.beat\b/);
    assert.doesNotMatch(html, /id="clear-creds-btn"/);
    assert.doesNotMatch(html, /Create Broadcast/);
    assert.doesNotMatch(html, /Transport/);
    assert.doesNotMatch(html, /Permission/);
  });

  it("does not clip helpers on html, body, #app, or .body", () => {
    assert.doesNotMatch(css, /html,\s*body\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /#app\s*\{[^}]*overflow:\s*hidden/s);
    assert.doesNotMatch(css, /\.body\s*\{[^}]*overflow:\s*hidden/s);
  });

  it("locks Beat 1 Sign in copy and Save → PUT credentials", () => {
    assert.match(html, />Sign in</);
    assert.match(html, /Save Media Studio RTMP once\. Not X OAuth\./);
    assert.match(html, /id="rtmp_url"[^>]*type="text"/s);
    assert.match(html, /id="rtmp_key"[^>]*type="password"/s);
    assert.match(html, /id="rtmp_url"[^>]*autocomplete="off"/s);
    assert.match(html, /id="rtmp_key"[^>]*autocomplete="off"/s);
    assert.doesNotMatch(html, /id="rtmp_url"[^>]*placeholder=/s);
    assert.doesNotMatch(html, /id="rtmp_key"[^>]*placeholder=/s);
    assert.match(html, /id="save-btn"[^>]*>Save</s);
    assert.match(main, /saveCredentials\(\{\s*rtmp_url,\s*rtmp_key\s*\}\)/);
    assert.match(main, /clearDestFields/);
    assert.match(main, /showBeat\(2\)/);
    assert.doesNotMatch(html, /Sign in with X/);
  });

  it("locks Beat 2 Drop link, preview, ack, Continue, Change destination", () => {
    assert.match(html, />Drop link</);
    assert.match(html, /id="source_url"[^>]*type="text"/s);
    assert.match(html, /placeholder="Paste YouTube live URL"/);
    assert.match(html, /id="source_url"[^>]*autocomplete="off"/s);
    assert.doesNotMatch(html, /id="source_url"[^>]*type="url"/s);
    assert.match(html, /I have permission or fair use to retransmit this live\./);
    assert.match(html, /id="continue-btn"[^>]*>Continue</s);
    assert.match(html, /id="change-dest"[^>]*>Change destination</s);
    assert.match(html, /YouTube first/);
    assert.match(main, /showBeat\(3\)/);
    assert.match(main, /canContinue/);
    assert.match(main, /retransApi\.preview\(/);
  });

  it("locks Beat 3 Retrans start/stop and helpers", () => {
    const beat3 = html.slice(html.indexOf('id="beat-3"'));
    assert.match(html, /Start live retrans/);
    assert.match(html, /id="stop-btn"[^>]*>Stop</s);
    assert.match(html, /Idle until ready/);
    assert.match(enablement, /Idle until ready/);
    assert.match(enablement, /Retransmitting live to X/);
    assert.match(main, /retransApi\.start\(\s*\{\s*source_url:/);
    assert.doesNotMatch(main, /payload\.rtmp_url/);
    assert.doesNotMatch(main, /retransApi\.start\([\s\S]*rtmp_url/);
    assert.doesNotMatch(beat3, /id="rtmp_url"/);
    assert.doesNotMatch(beat3, /id="rtmp_key"/);
  });

  it("does not paint parseSourceUrl as display before preview API", () => {
    const chrome = readFileSync(new URL("./previewChrome.js", import.meta.url), "utf8");
    assert.doesNotMatch(main, /applyPreview\(\s*parseSourceUrl/);
    assert.match(main, /writeSourceIfNeeded\(els\.source, result\.source_url\)/);
    assert.match(main, /runPreview\(\)/);
    assert.match(main, /retransApi\.preview\(/);
    assert.match(chrome, /result\.is_live === true/);
    assert.doesNotMatch(main, /YouTube source/);
    assert.doesNotMatch(main, /YouTube live/);
    assert.doesNotMatch(chrome, /YouTube source/);
  });

  it("consumes primary-flow 502 chrome: helper as-is, hide card, Idle pill", () => {
    const design = readFileSync(new URL("../design/primary-flow.md", import.meta.url), "utf8");
    assert.match(design, /502.*ok:\s*false.*error/s);
    assert.match(design, /Error helper/);
    assert.match(design, /as-is/);
    assert.match(main, /previewPaint/);
    assert.match(main, /isPreviewProbeFail/);
    assert.match(main, /Never Error pill/);
    assert.doesNotMatch(main, /error\s*=\s*["']status failed["']/);
    assert.match(main, /applyPreview\(parsed, result\)/);
  });

  it("Start sends source_url only; no clip UI; Vite loopback 8788", () => {
    const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    assert.match(main, /retransApi\.start\(\s*\{\s*source_url:\s*readField\(els\.source\)\.trim\(\)\s*,?\s*\}\s*\)/);
    assert.doesNotMatch(main, /\/api\/clip/);
    assert.doesNotMatch(html, /\/api\/clip/);
    assert.doesNotMatch(html, /\b[Cc]lip\b/);
    assert.match(vite, /const BACKEND = "http:\/\/127\.0\.0\.1:8788"/);
    assert.match(vite, /host: "127\.0\.0\.1"/);
    assert.match(vite, /base:\s*["']\.\/["']/);
    assert.doesNotMatch(vite, /host:\s*["']0\.0\.0\.0["']/);
    assert.match(api, /\/api\/live\/start/);
    assert.doesNotMatch(api, /http:\/\/127\.0\.0\.1:5173/);
    assert.doesNotMatch(main, /http:\/\/127\.0\.0\.1:5173/);
    assert.doesNotMatch(html, /:5173/);
    assert.match(readme, /Open http:\/\/127\.0\.0\.1:8788/);
    assert.doesNotMatch(readme, /Open http:\/\/127\.0\.0\.1:5173/);
  });

  it("boot routes configured → Beat 2; poll fail stays Idle", () => {
    assert.match(main, /retransApi\.credentials\(\)/);
    assert.match(main, /configured/);
    assert.match(main, /showBeat\(2\)/);
    assert.match(main, /isUsableStatus/);
    assert.doesNotMatch(main, /error\s*=\s*["']status failed["']/);
  });

  it("Error sticks until Stop; idle status poll does not wipe", () => {
    assert.match(enablement, /export function nextChrome/);
    assert.match(main, /nextChrome/);
    assert.match(main, /applyStatus/);
    assert.match(enablement, /state === "live" \|\| state === "error"/);
    assert.match(css, /::placeholder/);
    assert.match(css, /:not\(:placeholder-shown\)/);
    const fields = readFileSync(new URL("./fields.js", import.meta.url), "utf8");
    assert.match(fields, /export function readField/);
    assert.match(fields, /export function writeField/);
    assert.match(main, /from "\.\/fields\.js"/);
    assert.doesNotMatch(main, /els\.source\.value\s*=\s*["']Paste YouTube live URL["']/);
    assert.doesNotMatch(main, /\.placeholder\s*=/);
    assert.doesNotMatch(css, /input\[type="url"\]/);
  });
});
