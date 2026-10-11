const CACHE_NAME = "touchhelm-__TOUCHHELM_BUILD__";
const ASSETS = [
  "/",
  "/index.html",
  "/style.css",
  "/style.css?v=__TOUCHHELM_BUILD__",
  "/ui.css",
  "/ui.css?v=__TOUCHHELM_BUILD__",
  "/app.js",
  "/app.js?v=__TOUCHHELM_BUILD__",
  "/controls.js",
  "/controls.js?v=__TOUCHHELM_BUILD__",
  "/manifest.json",
  "/icons/icon.svg"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => ((k.startsWith("touchhelm-") || k.startsWith("phonepad-")) && k !== CACHE_NAME ? caches.delete(k) : null)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin ||
      url.pathname === "/ws" || url.pathname.startsWith("/api/")) {
    return;
  }
  // Network first, fallback to cache
  e.respondWith(
    fetch(e.request, { cache: "no-store" })
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          e.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(e.request, copy)).catch(() => {}));
        }
        return res;
      })
      .catch(async () => (await caches.match(e.request)) || Response.error())
  );
});
