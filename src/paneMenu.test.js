import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  PANE_DROP,
  PANE_KEYS,
  PANE_LABELS,
  PANE_OUTBOUND,
  canOpenDropLink,
  clampPane,
  paintPaneMenu,
  paneAfterMenu,
  paneFromClick,
} from "./paneMenu.js";

function fakeMenu() {
  const buttons = [1, 2, 3].map((id) => {
    const attrs = { "data-pane": String(id), "aria-pressed": "false" };
    return {
      getAttribute(name) {
        return attrs[name] ?? null;
      },
      setAttribute(name, value) {
        attrs[name] = String(value);
      },
    };
  });
  return {
    querySelectorAll() {
      return buttons;
    },
    buttons,
  };
}

describe("pane menu", () => {
  it("is one 3-pane switcher: Keys, Drop link, Outbound", () => {
    assert.equal(PANE_KEYS, 1);
    assert.equal(PANE_DROP, 2);
    assert.equal(PANE_OUTBOUND, 3);
    assert.equal(PANE_LABELS[1], "Keys");
    assert.equal(PANE_LABELS[2], "Drop link");
    assert.equal(PANE_LABELS[3], "Outbound");
    assert.equal(clampPane(2), 2);
    assert.equal(clampPane(3), 3);
    assert.equal(clampPane(9), 1);
    assert.equal(canOpenDropLink(""), false);
    assert.equal(canOpenDropLink("key-a"), true);
    assert.equal(paneAfterMenu(2, ""), 1);
    assert.equal(paneAfterMenu(2, "key-a"), 2);
    assert.equal(paneAfterMenu(3, ""), 3);
    assert.equal(paneAfterMenu(0, "key-a", 2), 2);
  });

  it("paints one pressed pane and reads clicks", () => {
    const root = fakeMenu();
    assert.equal(paintPaneMenu(root, 2), 2);
    assert.equal(root.buttons[0].getAttribute("aria-pressed"), "false");
    assert.equal(root.buttons[1].getAttribute("aria-pressed"), "true");
    assert.equal(root.buttons[2].getAttribute("aria-pressed"), "false");
    assert.equal(paneFromClick(root.buttons[2]), 3);
    assert.equal(paneFromClick(null), 0);
  });

  it("chrome is one menu on the 480px console; no Sign-in, OAuth, or clip", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    const css = readFileSync(new URL("./style.css", import.meta.url), "utf8");
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    assert.match(html, /id="pane-menu"/);
    assert.match(html, /data-pane="1"[^>]*>Keys</);
    assert.match(html, /data-pane="2"[^>]*>Drop link</);
    assert.match(html, /data-pane="3"[^>]*>Outbound</);
    assert.equal((html.match(/id="pane-menu"/g) || []).length, 1);
    assert.match(css, /max-width:\s*480px/);
    assert.match(css, /\.pane-menu\b/);
    assert.match(main, /paintPaneMenu/);
    assert.match(main, /paneAfterMenu/);
    assert.doesNotMatch(html, /Sign in/);
    assert.doesNotMatch(html, /Sign in with X/);
    assert.doesNotMatch(html, /OAuth/);
    assert.doesNotMatch(html, /\b[Cc]lip\b/);
    assert.match(html, />Keys \/ Configuration</);
    assert.match(html, /id="playlist"/);
    assert.match(html, /id="playlist-now"/);
  });
});
