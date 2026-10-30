const CACHE_NAME = "touchhelm-__TOUCHHELM_BUILD__";
const ASSETS = [
  "/",
  "/index.html",
  "/style.css",
  "/style.css?v=__TOUCHHELM_BUILD__",
  "/ui.css",
  "/ui.css?v=__TOUCHHELM_BUILD__",
  "/app.js",
  "/files.js?v=__TOUCHHELM_BUILD__",
  "/files.css?v=__TOUCHHELM_BUILD__",
  "/app.js?v=__TOUCHHELM_BUILD__",
  "/text-sync.js?v=__TOUCHHELM_BUILD__",
  "/remote.js?v=__TOUCHHELM_BUILD__",
  "/remote.css?v=__TOUCHHELM_BUILD__",
  "/screens.css?v=__TOUCHHELM_BUILD__",
  "/controls.js",
  "/controls.js?v=__TOUCHHELM_BUILD__",
  "/themes.css?v=__TOUCHHELM_BUILD__",
  "/themes.js?v=__TOUCHHELM_BUILD__",
  "/theme-gl.css?v=__TOUCHHELM_BUILD__",
  "/theme-scenes.js?v=__TOUCHHELM_BUILD__",
  "/theme-gl.js?v=__TOUCHHELM_BUILD__",
  "/motion.css?v=__TOUCHHELM_BUILD__",
  "/motion.js?v=__TOUCHHELM_BUILD__",
  "/media-clock.js?v=__TOUCHHELM_BUILD__",
  "/haptics.js?v=__TOUCHHELM_BUILD__",
  "/experience.js?v=__TOUCHHELM_BUILD__",
  "/demo.js?v=__TOUCHHELM_BUILD__",
  "/themes/ink.css?v=__TOUCHHELM_BUILD__",
  "/manifest.json",
  "/icons/icon.svg"
];

self.addEventListener('message',e=>{
  if(e.data?.type!=='cache_theme'||!Array.isArray(e.data.paths))return;
  const paths=e.data.paths.slice(0,8).filter(path=>typeof path==='string'&&/^\/themes\/(?:[a-z]+\.css|assets\/[a-z0-9-]+\.(?:webp|woff2))(?:\?v=[a-z0-9_]+)?$/i.test(path));
  if(paths.length)e.waitUntil(caches.open(CACHE_NAME).then(cache=>cache.addAll(paths)).catch(()=>{}));
});

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
