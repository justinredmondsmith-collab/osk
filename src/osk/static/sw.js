const CACHE_PREFIX = "osk-member-";
const CACHE_VERSION = "osk-member-v2";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const NAV_CACHE = `${CACHE_VERSION}-nav`;
const STATIC_ASSETS = [
  "/manifest.webmanifest",
  "/static/member.css",
  "/static/member.js",
  "/static/audio-capture.js",
  "/static/frame-sampler.js",
  "/static/sampling-worker.js",
  "/static/observer-media.js",
  "/static/member-outbox.js",
  "/static/pwa-runtime.js",
  "/static/icon.svg",
];
const NAVIGATION_PATHS = new Set(["/join", "/member"]);
const OFFLINE_HTML = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#07101b" />
    <title>Osk Offline</title>
    <style>
      :root {
        color-scheme: dark;
        --bg: #07101b;
        --panel: rgba(10, 24, 38, 0.92);
        --line: rgba(143, 173, 209, 0.18);
        --ink: #edf5ff;
        --muted: #8ca2be;
        --accent: #5be0ce;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 1.25rem;
        color: var(--ink);
        font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top, rgba(91, 224, 206, 0.16), transparent 28%),
          linear-gradient(180deg, #09111c 0%, #07101b 56%, #050c14 100%);
      }

      main {
        width: min(32rem, 100%);
        padding: 1.2rem 1.1rem;
        border: 1px solid var(--line);
        border-radius: 1.4rem;
        background: var(--panel);
        box-shadow: 0 24px 60px rgba(1, 8, 16, 0.52);
      }

      p {
        margin: 0;
        line-height: 1.55;
      }

      .eyebrow {
        margin-bottom: 0.35rem;
        color: var(--accent);
        font-size: 0.78rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
      }

      h1 {
        margin: 0 0 0.55rem;
        font-size: clamp(2rem, 9vw, 3.2rem);
        line-height: 0.95;
        letter-spacing: -0.06em;
      }

      .muted {
        margin-top: 0.9rem;
        color: var(--muted);
      }
    </style>
  </head>
  <body>
    <main>
      <p class="eyebrow">Osk Offline</p>
      <h1>Waiting for the hub</h1>
      <p>The cached member shell is available, but the live hub connection is currently offline. Reconnect to the local coordinator network to resume alerts, reports, and media upload.</p>
      <p class="muted">Queued field notes and manual media stay in the browser outbox until the local hub comes back. If this is a fresh browser with no cached shell yet, reopen the QR join link once the hub is reachable again.</p>
    </main>
  </body>
</html>`;

async function clearOfflineCaches() {
  const keys = await caches.keys();
  await Promise.all(
    keys
      .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX))
      .map((cacheName) => caches.delete(cacheName)),
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX) && ![SHELL_CACHE, NAV_CACHE].includes(cacheName))
          .map((cacheName) => caches.delete(cacheName)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "clear_member_offline_state") {
    event.waitUntil(clearOfflineCaches());
  }
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(SHELL_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

async function navigationResponse(request) {
  const navCache = await caches.open(NAV_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && NAVIGATION_PATHS.has(new URL(request.url).pathname)) {
      navCache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await navCache.match(request);
    if (cached) {
      return cached;
    }
    const cachedMember = await navCache.match("/member");
    if (cachedMember) {
      return cachedMember;
    }
    const cachedJoin = await navCache.match("/join");
    if (cachedJoin) {
      return cachedJoin;
    }
    return new Response(OFFLINE_HTML, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(navigationResponse(request));
    return;
  }

  if (
    url.pathname === "/manifest.webmanifest" ||
    url.pathname === "/sw.js" ||
    url.pathname.startsWith("/static/")
  ) {
    event.respondWith(cacheFirst(request));
  }
});
