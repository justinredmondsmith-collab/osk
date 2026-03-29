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

// Service Worker resilience metrics
let swMetrics = {
  installTime: null,
  activateTime: null,
  fetchCount: 0,
  errorCount: 0,
  lastError: null,
};

function logError(context, error) {
  const entry = {
    context,
    message: error?.message || String(error),
    timestamp: new Date().toISOString(),
  };
  swMetrics.errorCount++;
  swMetrics.lastError = entry;
  console.error(`[SW] ${context}:`, error);
}
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
  try {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX))
        .map((cacheName) => caches.delete(cacheName)),
    );
    return { success: true, cleared: keys.length };
  } catch (error) {
    logError("clearOfflineCaches", error);
    return { success: false, error: error?.message };
  }
}

async function clearMemberOfflineState() {
  await clearOfflineCaches();
  return {
    cleared: true,
    unregistered: (await self.registration.unregister()) === true,
  };
}

self.addEventListener("install", (event) => {
  swMetrics.installTime = new Date().toISOString();
  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open(SHELL_CACHE);
        // Use individual puts instead of addAll for better error handling
        const results = await Promise.allSettled(
          STATIC_ASSETS.map(async (url) => {
            try {
              const response = await fetch(url, { cache: "no-cache" });
              if (!response.ok) {
                throw new Error(`HTTP ${response.status} for ${url}`);
              }
              await cache.put(url, response);
              return { url, success: true };
            } catch (error) {
              logError(`cache populate: ${url}`, error);
              return { url, success: false, error: error?.message };
            }
          }),
        );
        const failures = results.filter((r) => !r.value?.success);
        if (failures.length > 0) {
          console.warn(`[SW] ${failures.length} assets failed to cache`);
        }
        await self.skipWaiting();
        return { cached: results.length - failures.length, failed: failures.length };
      } catch (error) {
        logError("install", error);
        // Still skip waiting to avoid blocking
        await self.skipWaiting();
        throw error;
      }
    })(),
  );
});

self.addEventListener("activate", (event) => {
  swMetrics.activateTime = new Date().toISOString();
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        const deletions = await Promise.allSettled(
          keys
            .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX) && ![SHELL_CACHE, NAV_CACHE].includes(cacheName))
            .map(async (cacheName) => {
              try {
                await caches.delete(cacheName);
                return { cacheName, deleted: true };
              } catch (error) {
                logError(`cache delete: ${cacheName}`, error);
                return { cacheName, deleted: false, error: error?.message };
              }
            }),
        );
        const failed = deletions.filter((d) => d.status === "rejected" || !d.value?.deleted);
        if (failed.length > 0) {
          console.warn(`[SW] ${failed.length} old caches could not be deleted`);
        }
        await self.clients.claim();
        return { cleaned: deletions.length - failed.length };
      } catch (error) {
        logError("activate", error);
        // Still claim clients to avoid blocking
        await self.clients.claim();
        throw error;
      }
    })(),
  );
});

self.addEventListener("message", (event) => {
  const replyPort = event.ports?.[0] || null;
  const messageType = event.data?.type;
  
  if (messageType === "clear_member_offline_state") {
    event.waitUntil(
      (async () => {
        let payload = {
          cleared: false,
          unregistered: false,
        };
        try {
          payload = await clearMemberOfflineState();
        } catch (error) {
          logError("clear_member_offline_state", error);
          payload = {
            cleared: false,
            unregistered: false,
            error: "offline-clear-failed",
            errorDetail: error?.message,
          };
        }
        replyPort?.postMessage(payload);
      })(),
    );
  } else if (messageType === "sw_health_check") {
    // Health check for diagnostics
    event.waitUntil(
      (async () => {
        const health = {
          type: "sw_health",
          healthy: true,
          metrics: { ...swMetrics },
          timestamp: new Date().toISOString(),
        };
        replyPort?.postMessage(health);
      })(),
    );
  } else if (messageType === "sw_clear_metrics") {
    // Reset metrics for testing
    swMetrics = {
      installTime: swMetrics.installTime,
      activateTime: swMetrics.activateTime,
      fetchCount: 0,
      errorCount: 0,
      lastError: null,
    };
    replyPort?.postMessage({ type: "sw_metrics_cleared", metrics: swMetrics });
  }
});

async function cacheFirst(request) {
  swMetrics.fetchCount++;
  try {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    const response = await fetch(request);
    if (response.ok) {
      try {
        const cache = await caches.open(SHELL_CACHE);
        await cache.put(request, response.clone());
      } catch (cacheError) {
        logError(`cache put: ${request.url}`, cacheError);
        // Return response even if caching fails
      }
    }
    return response;
  } catch (error) {
    logError(`cacheFirst: ${request.url}`, error);
    // Return a 503 response for network failures
    return new Response("Network error", {
      status: 503,
      statusText: "Service Unavailable",
      headers: { "Content-Type": "text/plain" },
    });
  }
}

async function navigationResponse(request) {
  const url = new URL(request.url);
  const pathname = url.pathname;
  
  try {
    const navCache = await caches.open(NAV_CACHE);
    try {
      const response = await fetch(request);
      if (response.ok && NAVIGATION_PATHS.has(pathname)) {
        try {
          await navCache.put(request, response.clone());
        } catch (cacheError) {
          logError(`nav cache put: ${pathname}`, cacheError);
        }
      }
      return response;
    } catch (networkError) {
      // Network failed - try cache
      logError(`nav fetch: ${pathname}`, networkError);
      
      const cached = await navCache.match(request);
      if (cached) {
        return cached;
      }
      
      // Try fallback pages
      const fallbackPaths = ["/member", "/join"];
      for (const fallbackPath of fallbackPaths) {
        const cachedFallback = await navCache.match(fallbackPath);
        if (cachedFallback) {
          console.log(`[SW] Serving ${fallbackPath} as fallback for ${pathname}`);
          return cachedFallback;
        }
      }
      
      // No cached fallback - return offline HTML
      return new Response(OFFLINE_HTML, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
        },
      });
    }
  } catch (error) {
    logError(`navigationResponse: ${pathname}`, error);
    // Ultimate fallback
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
