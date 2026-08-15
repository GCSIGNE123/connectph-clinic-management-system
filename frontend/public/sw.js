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
  // Only intercept same-origin requests (the app's own pages/assets) - a
  // fetch handler existing at all is what browsers check for "Add to Home
  // Screen" eligibility, but proxying EVERY request through the service
  // worker, including cross-origin API calls to the backend (a different
  // port - localhost:8000 vs this app's localhost:3000/<LAN-IP>:3000),
  // adds a fragile extra network hop with no benefit (no caching strategy
  // exists here anyway). Confirmed live: real-world "Failed to fetch"
  // errors on a large sequential CSV import persisted even after a hard
  // refresh - a hard refresh cannot remove an already-installed, still-
  // running service worker, so this double-hop kept happening regardless.
  // Ignoring cross-origin requests lets the browser fetch them directly,
  // exactly as if no service worker were installed at all.
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(fetch(event.request));
});
