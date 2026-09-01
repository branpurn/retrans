/**
 * One compact pane switcher. Three panes, one at a time.
 * 1 Keys / 2 Drop link / 3 Outbound. No settings maze.
 */

export const PANE_KEYS = 1;
export const PANE_DROP = 2;
export const PANE_OUTBOUND = 3;

export const PANE_LABELS = {
  [PANE_KEYS]: "Keys",
  [PANE_DROP]: "Drop link",
  [PANE_OUTBOUND]: "Outbound",
};

/** Drop link still needs a selected named key. No maze — stay on Keys. */
export function canOpenDropLink(selectedKeyId) {
  return typeof selectedKeyId === "string" && selectedKeyId.trim() !== "";
}

/** Menu click → pane. Drop link with no key stays on Keys. Never Stop. */
export function paneAfterMenu(want, selectedKeyId, current = PANE_KEYS) {
  const n = Number(want);
  if (n !== PANE_KEYS && n !== PANE_DROP && n !== PANE_OUTBOUND) {
    return clampPane(current);
  }
  if (n === PANE_DROP && !canOpenDropLink(selectedKeyId)) return PANE_KEYS;
  return n;
}

export function clampPane(n) {
  const pane = Number(n);
  if (pane === PANE_DROP || pane === PANE_OUTBOUND) return pane;
  return PANE_KEYS;
}

/** Mark the active menu button. Buttons use data-pane="1|2|3". */
export function paintPaneMenu(root, pane) {
  const active = clampPane(pane);
  if (!root) return active;
  for (const btn of root.querySelectorAll("[data-pane]")) {
    const on = btn.getAttribute("data-pane") === String(active);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }
  return active;
}

export function paneFromClick(target) {
  if (!target) return 0;
  const btn = typeof target.closest === "function" ? target.closest("[data-pane]") : target;
  const raw = btn?.getAttribute?.("data-pane");
  if (raw === "1" || raw === "2" || raw === "3") return Number(raw);
  return 0;
}
