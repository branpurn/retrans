const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
  "www.youtu.be",
]);

function asUrl(raw) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return null;
  try {
    return new URL(trimmed);
  } catch {
    try {
      return new URL(`https://${trimmed}`);
    } catch {
      return null;
    }
  }
}

function videoIdFromPath(pathname, index) {
  const part = pathname.split("/").filter(Boolean)[index];
  return part || null;
}

export function parseSourceUrl(raw) {
  const url = asUrl(raw);
  if (!url) {
    return { ok: false, reason: String(raw ?? "").trim() ? "invalid" : "empty" };
  }

  const host = url.hostname.toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) {
    return { ok: false, reason: "youtube-first", href: url.href, host };
  }

  let videoId = null;
  let isLive = url.pathname.includes("/live");

  if (host === "youtu.be" || host === "www.youtu.be") {
    videoId = videoIdFromPath(url.pathname, 0);
  } else if (url.pathname.startsWith("/watch")) {
    videoId = url.searchParams.get("v");
  } else if (url.pathname.startsWith("/live/")) {
    videoId = videoIdFromPath(url.pathname, 1);
    isLive = true;
  } else if (url.pathname.startsWith("/embed/")) {
    videoId = videoIdFromPath(url.pathname, 1);
  } else if (url.pathname.startsWith("/shorts/")) {
    videoId = videoIdFromPath(url.pathname, 1);
  } else if (url.pathname.endsWith("/live")) {
    isLive = true;
  }

  const title = videoId
    ? isLive
      ? `YouTube live ${videoId}`
      : `YouTube source ${videoId}`
    : isLive
      ? "YouTube live"
      : "YouTube source";

  return {
    ok: true,
    href: url.href,
    host,
    videoId,
    isLive,
    title,
    thumbnail: videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "",
  };
}
