/**
 * Beat 3 outbound player. HTML5 <video> + audio on same-origin 8788.
 * Attaches while Retrans is starting/live. Src is the named Backend tee only.
 * No YouTube embed. No preview thumbnail. No invented /api routes.
 */

const LIVEISH = new Set(["starting", "live"]);

/** Locked JSON / control routes — never a media src. Preview stays title/is_live only. */
const NOT_MEDIA = new Set([
  "/api/live/preview",
  "/api/live/status",
  "/api/live/keys",
  "/api/live/start",
  "/api/live/stop",
  "/api/live/credentials",
]);

/** Same-origin tee path. Empty until Backend names one. Never YouTube. */
export const NAMED_TEE = "";

/** Designer lock — visual label on Beat 3. Not Preview, Monitor, or Clip. */
export const OUTBOUND_LABEL = "Outbound";

export function playerShouldAttach({ backend, sessions = [] } = {}) {
  if (LIVEISH.has(backend)) return true;
  return sessions.some((sess) => LIVEISH.has(sess.state));
}

/**
 * Media src for <video>. Only a same-origin path (named tee).
 * Never YouTube page/embed URLs. Never preview thumbnails. Never 0.0.0.0.
 */
export function outboundSrc(namedTee = NAMED_TEE) {
  const raw = typeof namedTee === "string" ? namedTee.trim() : "";
  if (!raw) return "";
  if (/youtube\.com|youtu\.be|ytimg\.com/i.test(raw)) return "";
  if (/^https?:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      if (url.hostname !== "127.0.0.1") return "";
      if (url.port && url.port !== "8788") return "";
      return `${url.pathname}${url.search}`;
    } catch {
      return "";
    }
  }
  if (!raw.startsWith("/") || raw.startsWith("//")) return "";
  const path = raw.split("?")[0];
  if (NOT_MEDIA.has(path) || path.startsWith("/api/live/keys/")) return "";
  return raw;
}

export function attachPlayer(video, { attach, src } = {}) {
  if (!video) return { attached: false, src: "" };
  const media = attach ? outboundSrc(src) : "";
  if (!attach) {
    if (typeof video.pause === "function") video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    if (typeof video.load === "function") video.load();
    video.classList.add("hidden");
    return { attached: false, src: "" };
  }
  video.classList.remove("hidden");
  if (media) {
    if (video.getAttribute("src") !== media) video.setAttribute("src", media);
  } else {
    video.removeAttribute("src");
  }
  video.removeAttribute("poster");
  return { attached: true, src: media };
}
