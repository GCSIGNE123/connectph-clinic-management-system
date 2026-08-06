"use client";

import { Suspense } from "react";
import { TvDisplayScreen } from "@/features/tv-display/components/TvDisplayScreen";

/**
 * Bare, zero-configuration TV Queue Display route for the "one clinic, one
 * physical TV, on-prem server" deployment case: the TV's browser is just
 * pointed at `http://<server>/tv` (optionally `?fullscreen=true`) with no
 * slug to type in, remember, or mis-key on a remote control.
 *
 * Slug resolution priority:
 *   1. `NEXT_PUBLIC_DEFAULT_TV_SLUG` (frontend env var, see `.env.example`)
 *      - the clinic's admin sets this once when the on-prem box is
 *      provisioned. This is a *build-time-baked* Next.js public env var,
 *      which fits this deployment shape exactly: a single clinic running
 *      its own frontend build for its own TV, not a shared multi-tenant
 *      SaaS frontend serving many clinics from one build.
 *   2. A backend-resolved "default display for this clinic" - NOT
 *      implemented in this round. The public display endpoint
 *      (`GET /public/tv-display/{public_slug}`) intentionally has no
 *      clinic-identifying parameter at all (see
 *      `backend/app/api/v1/tv_display.py`'s module docstring) - the slug
 *      *is* the only credential/scope selector, by design, for security
 *      (unguessable-token access rather than clinic-id + auth). There is
 *      also no tenant-resolution-by-hostname layer in this app (no
 *      subdomain-per-clinic routing) that a public, unauthenticated `/tv`
 *      request could use to figure out "which clinic". Layering that in
 *      would be a materially larger, security-sensitive change (a new
 *      public "give me your default display" endpoint would need its own
 *      anti-enumeration protection), so it's intentionally left out here -
 *      see docs/BUGS.md for the explicit follow-up entry.
 *   3. Neither resolves -> a clear "No display configured" message
 *      instead of a crash/blank page (below).
 */
export default function TvDefaultDisplayPage() {
  const defaultSlug = process.env.NEXT_PUBLIC_DEFAULT_TV_SLUG;

  if (!defaultSlug) {
    return (
      <div className="flex h-screen max-h-screen w-full items-center justify-center overflow-hidden bg-slate-950 text-white">
        <div className="max-w-xl text-center">
          <p className="text-3xl font-semibold">No display configured</p>
          <p className="mt-4 text-lg text-slate-400">
            This TV isn&apos;t linked to a queue display yet. Set{" "}
            <code className="rounded bg-white/10 px-2 py-1 font-mono">NEXT_PUBLIC_DEFAULT_TV_SLUG</code> in this
            server&apos;s environment to the clinic&apos;s TV display public slug, or open the display&apos;s
            direct <code className="rounded bg-white/10 px-2 py-1 font-mono">/tv/&lt;slug&gt;</code> URL instead.
          </p>
        </div>
      </div>
    );
  }

  return (
    <Suspense fallback={null}>
      <TvDisplayScreen slug={defaultSlug} />
    </Suspense>
  );
}
