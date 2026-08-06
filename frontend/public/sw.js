// Phase 20 (item 13): minimal service worker for PWA installability only -
// no offline caching, no background sync. A pass-through fetch handler is
// the baseline requirement most browsers check for "Add to Home Screen"
// eligibility alongside the manifest.
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass-through only - no caching strategy implemented (out of scope for
  // this phase per the client's request: installability only).
  event.respondWith(fetch(event.request));
});
