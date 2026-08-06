"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { TvDisplayScreen } from "@/features/tv-display/components/TvDisplayScreen";

/**
 * Standalone, layout-independent public TV Queue Display, keyed by a
 * clinic's unguessable `public_slug`.
 *
 * Deliberately lives outside both the `(auth)` and `(dashboard)` route
 * groups - it renders with NO sidebar/topnav/authentication requirement.
 * `src/middleware.ts`'s `PROTECTED_PREFIXES` only matches `/dashboard` and
 * `/users`, so `/tv/*` was already reachable with zero session cookie with
 * no middleware change needed; this file supplies its own full-bleed
 * layout instead of using `(dashboard)/layout.tsx`'s `DashboardShell`.
 *
 * All actual realtime/announcement/fullscreen/kiosk logic lives in the
 * shared `TvDisplayScreen` component (also used by the bare `/tv` route)
 * so the two routes never diverge in behavior - this file's only job is
 * resolving `slug` from the URL param.
 */
export default function TvPublicDisplayPage() {
  const params = useParams<{ slug: string }>();
  return (
    <Suspense fallback={null}>
      <TvDisplayScreen slug={params.slug} />
    </Suspense>
  );
}
