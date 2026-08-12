/**
 * Resolves the backend API base URL at runtime from the page's own
 * hostname, instead of trusting a single value baked in at build/dev-
 * server-start time.
 *
 * Root cause this fixes: `NEXT_PUBLIC_*` env vars are fixed once, but this
 * app's local-clinic deployment (see `docs/LOCAL_DEPLOYMENT.md`) is reached
 * two different ways from the SAME machine - `http://localhost:3000` (this
 * machine itself) and `http://<LAN-IP>:3000` (a LAN device, e.g. the
 * waiting-room TV) - and each needs the API calls to go to a DIFFERENT
 * backend hostname (`localhost:8010` vs `<LAN-IP>:8010`). A single baked
 * `NEXT_PUBLIC_API_URL` can only ever be right for one of the two: pointing
 * it at the LAN IP (needed for the TV to work at all) means `localhost`
 * access now depends on this machine's own LAN-facing network adapter
 * being up, instead of the always-reliable loopback interface - a brief
 * Wi-Fi/adapter hiccup then breaks every in-flight request with a generic
 * "Failed to fetch", even though the backend itself never went down.
 * Confirmed live: a real 98-row CSV import failed exactly this way.
 *
 * Fix: at runtime, substitute the browser's OWN hostname (whatever
 * successfully loaded this page) in place of the configured one, keeping
 * only the port/path from `NEXT_PUBLIC_API_URL`. Only does this when the
 * configured host is itself a local/LAN address - a real cloud/production
 * domain (Phase 2.5's separately-hosted deployment, e.g. Vercel + a
 * distinct API domain) is left completely untouched, since substituting
 * there would be wrong (the frontend and backend are genuinely different
 * hosts, not the same LAN box on two different addresses).
 */

function isLocalNetworkHost(hostname: string): boolean {
  if (hostname === "localhost" || hostname === "127.0.0.1") return true;
  // RFC 1918 private ranges - covers the clinic's own LAN regardless of
  // which private block its router happens to use.
  return (
    /^10\.\d+\.\d+\.\d+$/.test(hostname) ||
    /^192\.168\.\d+\.\d+$/.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(hostname)
  );
}

const DEFAULT_API_URL = "http://localhost:8010/api/v1";

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
  // No `window` during SSR/build - nothing to substitute against, and no
  // real request is being made yet anyway.
  if (typeof window === "undefined") return configured;

  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    return configured;
  }

  if (!isLocalNetworkHost(parsed.hostname)) return configured;

  const port = parsed.port || (parsed.protocol === "https:" ? "443" : "80");
  return `${window.location.protocol}//${window.location.hostname}:${port}${parsed.pathname}`;
}
