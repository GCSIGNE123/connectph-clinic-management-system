"use client";

import { useEffect } from "react";

/**
 * Phase 20 (item 13): registers the minimal pass-through service worker
 * (`public/sw.js`) needed for PWA installability - no offline caching, just
 * the baseline "a fetch handler exists" requirement most browsers check
 * before allowing "Add to Home Screen". Renders nothing.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      // Never block the app on a failed SW registration (e.g. plain HTTP
      // in some dev setups, where service workers are unavailable).
      console.warn("Service worker registration failed:", error);
    });
  }, []);

  return null;
}
