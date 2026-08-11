"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Maximize, Minimize, Volume2, VolumeX, WifiOff } from "lucide-react";
import { useTvDisplayRealtime } from "@/features/tv-display/hooks/use-tv-display-realtime";
import { InformationPanel } from "@/features/tv-display/components/InformationPanel";
import { groupWaiting } from "@/features/tv-display/lib/grouping";
import { getNowServingLayout } from "@/features/tv-display/lib/now-serving-layout";
import { splitPrimaryNowServing } from "@/features/tv-display/lib/now-serving-primary";
import { enqueueAnnouncement } from "@/lib/queue-announcer";
import type { TvDisplayWaitingEntry } from "@/features/tv-display/types";

/**
 * Shared TV Queue Display screen - extracted so both the slug-based
 * multi-tenant route (`/tv/[slug]`) and the bare single-display
 * convenience route (`/tv`) render identical realtime/announcement/
 * fullscreen/kiosk logic with zero duplication. See each route's
 * `page.tsx` for how `slug` is resolved.
 *
 * Kiosk-mode additions on top of the original `/tv/[slug]` implementation:
 * - `?fullscreen=true` auto-requests the Fullscreen API on mount (best
 *   effort - browsers may block a non-gesture-triggered request; the
 *   maximized visual treatment applies unconditionally regardless).
 * - cursor auto-hides after a few seconds of no mouse movement.
 * - `overflow: hidden` locked on the root so nothing ever scrolls.
 * - Screen Wake Lock requested on mount / released on unmount, fully
 *   feature-detected so unsupported browsers neither crash nor warn.
 */

// Post-RC1 (50/50 Queue + Information/Advertisement Panel): these were
// originally sized in `vw` (viewport width) units, which was correct when
// Now Serving had the full screen width to itself. Now that it lives in a
// `w-1/2` column alongside the new Information Panel, `vw` no longer tracks
// its actual available width - a 3-column grid of `6vw` text still assumes
// 100% of the screen's width, overflowing its now-halved container. `cqw`
// (container query width, relative to the nearest `[container-type:inline-size]`
// ancestor - see the `.now-serving-container` wrapper below) fixes this by
// scaling off the column's real width instead of the viewport's.
const FONT_SIZE_CLASS: Record<string, string> = {
  Small: "text-4xl md:text-5xl lg:[font-size:clamp(2rem,8cqw,4.5rem)]",
  Medium: "text-5xl md:text-6xl lg:[font-size:clamp(2.5rem,10cqw,5.5rem)]",
  Large: "text-6xl md:text-7xl lg:[font-size:clamp(3rem,12cqw,7rem)]",
  ExtraLarge: "text-7xl md:text-8xl lg:[font-size:clamp(3.5rem,15cqw,9rem)]",
};

const CURSOR_IDLE_MS = 3000;

// How many upcoming numbers to show per destination in "Next in Queue".
// Capped (rather than showing everyone waiting) so each group reliably
// reads as one compact line instead of wrapping into two - a full waiting
// list isn't the point of this section, a quick "who's coming up" glance
// is. Deliberately kept low enough to fit one line even in the narrowest
// (4-column) group layout; `flex-wrap` (not `nowrap`) is still used as a
// visible fallback rather than an invisible clip if a screen is ever too
// narrow for even this many.
const NEXT_IN_QUEUE_PER_GROUP = 4;

function useClock() {
  // Starts `null` (not `new Date()`) so the server-rendered markup and the
  // first client render match exactly - a documented Next.js hydration
  // pitfall (see docs/TESTING.md's Phase-1 hydration note for the same
  // class of bug found on the dashboard). The real clock only starts
  // ticking after mount.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function useIdleCursor(idleMs: number) {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      setIdle(false);
      clearTimeout(timer);
      timer = setTimeout(() => setIdle(true), idleMs);
    };
    reset();
    window.addEventListener("mousemove", reset);
    window.addEventListener("keydown", reset);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("mousemove", reset);
      window.removeEventListener("keydown", reset);
    };
  }, [idleMs]);
  return idle;
}

function useWakeLock() {
  useEffect(() => {
    if (!("wakeLock" in navigator)) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let sentinel: any = null;
    let cancelled = false;

    const request = async () => {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sentinel = await (navigator as any).wakeLock.request("screen");
      } catch {
        // Denied/unsupported at runtime (e.g. tab not visible, battery
        // saver) - non-fatal, the display just won't force-stay-awake.
      }
    };

    void request();

    // Re-acquire if the tab regains visibility - most browsers release
    // the lock automatically when the page is hidden.
    const onVisibility = () => {
      if (!cancelled && document.visibilityState === "visible" && !sentinel) {
        void request();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      void sentinel?.release().catch(() => undefined);
    };
  }, []);
}

export function TvDisplayScreen({ slug }: { slug: string }) {
  const searchParams = useSearchParams();
  const autoFullscreen = searchParams.get("fullscreen") === "true";

  const now = useClock();
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  // Keyed by queueId -> the `calledAt` timestamp last seen for that ticket,
  // not just a Set of ids. A Recall re-stamps `called_at` server-side
  // without changing `queueId`, so keying on id alone (the original
  // implementation) silently swallowed the re-announcement on Recall -
  // the ticket was already a "known" id, so the new Call/Recall event
  // never looked new. Tracking the timestamp lets a changed `calledAt`
  // on an already-known id re-trigger the announcement too.
  const prevCalledAtRef = useRef<Map<string, string | null>>(new Map());
  const idle = useIdleCursor(CURSOR_IDLE_MS);

  useWakeLock();

  const { data, error, connectionStatus } = useTvDisplayRealtime(slug, 30);

  useEffect(() => {
    if (!data) return;
    const currentCalledAt = new Map(data.nowServing.map((n) => [n.queueId, n.calledAt]));
    if (soundEnabled) {
      // Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): announce
      // EVERY entry whose calledAt is new/changed this fetch cycle, not just
      // the first one found - fixes the original single-doctor-era `break`
      // silently dropping a second doctor/department's call that lands in
      // the same poll window. `enqueueAnnouncement` sequences them (spoken
      // one after another) rather than clobbering via `.cancel()`.
      for (const entry of data.nowServing) {
        const prev = prevCalledAtRef.current.get(entry.queueId);
        const isNewOrRecalled = !prevCalledAtRef.current.has(entry.queueId) || prev !== entry.calledAt;
        if (isNewOrRecalled) {
          enqueueAnnouncement(entry.queueNumber, {
            doctorName: entry.doctorName,
            departmentName: entry.departmentName,
            roomName: entry.roomName,
          });
        }
      }
    }
    prevCalledAtRef.current = currentCalledAt;
  }, [data, soundEnabled]);

  useEffect(() => {
    const handler = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const toggleFullscreen = async () => {
    try {
      if (!document.fullscreenElement) {
        await containerRef.current?.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch {
      // Fullscreen can be denied by the browser/OS - non-fatal.
    }
  };

  // Best-effort auto-fullscreen from `?fullscreen=true`. Most browsers
  // require a user gesture to grant `requestFullscreen()`; when called
  // straight from a `useEffect` on mount (no click in the call stack) it
  // is commonly silently rejected. We still attempt it (some kiosk
  // browsers / PWA contexts allow it), but the TV-mode visual treatment
  // below does not depend on this succeeding - see docs/TESTING.md for
  // what was actually observed in a live browser test.
  useEffect(() => {
    if (!autoFullscreen) return;
    const t = setTimeout(() => {
      void containerRef.current?.requestFullscreen?.().catch(() => undefined);
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoFullscreen]);

  // Post-RC1 (single-active-ticket display rule): a doctor/department only
  // ever gets ONE Now Serving card, even if the backend has more than one
  // Called/Serving ticket for that same destination simultaneously - the
  // rest are folded into "Next in Queue" instead (shown first within their
  // group, ahead of tickets that haven't been called at all yet). This does
  // NOT affect the announcer, which still reacts to the full unfiltered
  // `data.nowServing` below - a demoted ticket was still really called.
  const { primary: primaryNowServing, overflow: overflowNowServing } = useMemo(
    () => splitPrimaryNowServing(data?.nowServing ?? []),
    [data]
  );
  const waitingGroups = useMemo(() => {
    const overflowAsWaiting: TvDisplayWaitingEntry[] = overflowNowServing.map((entry) => ({
      queueId: entry.queueId,
      queueNumber: entry.queueNumber,
      patientInitials: entry.patientInitials,
      doctorName: entry.doctorName,
      departmentId: entry.departmentId,
      departmentName: entry.departmentName,
      priority: "Normal",
      visitClassification: entry.visitClassification,
    }));
    return groupWaiting([...overflowAsWaiting, ...(data?.nextWaiting ?? [])]);
  }, [overflowNowServing, data]);

  const theme = data?.theme ?? "ClinicBranded";
  const fontSizeClass = FONT_SIZE_CLASS[data?.fontSize ?? "Large"] ?? FONT_SIZE_CLASS.Large;
  const themeClasses = useMemo(() => {
    if (theme === "Dark") return "bg-slate-950 text-white";
    if (theme === "Light") return "bg-white text-slate-900";
    return "bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white";
  }, [theme]);

  if (error && !data) {
    return (
      <div className="flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 text-white">
        <div className="text-center">
          <p className="text-2xl font-semibold">Display not available</p>
          <p className="mt-2 text-slate-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`h-screen max-h-screen w-full select-none overflow-hidden ${themeClasses} ${idle ? "cursor-none" : ""}`}
    >
      {/* Connection status + fullscreen/sound controls - unobtrusive,
          revealed clearly but not distracting for continuous kiosk use. */}
      <div className="fixed right-4 top-4 z-10 flex items-center gap-3 opacity-70 hover:opacity-100">
        {connectionStatus !== "open" ? (
          <span className="flex items-center gap-1.5 rounded-full bg-red-600/80 px-3 py-1 text-xs font-medium text-white">
            <WifiOff className="h-3.5 w-3.5" />
            {connectionStatus === "reconnecting" ? "Reconnecting..." : "Connecting..."}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setSoundEnabled((s) => !s)}
          className="rounded-full bg-black/30 p-2 text-white hover:bg-black/50"
          aria-label={soundEnabled ? "Disable sound" : "Enable sound"}
        >
          {soundEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => void toggleFullscreen()}
          className="rounded-full bg-black/30 p-2 text-white hover:bg-black/50"
          aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        >
          {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
        </button>
      </div>

      {!soundEnabled ? (
        <button
          type="button"
          onClick={() => setSoundEnabled(true)}
          className="fixed bottom-6 right-6 z-10 rounded-full bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-blue-500"
        >
          Enable Sound
        </button>
      ) : null}

      <div className="mx-auto flex h-screen max-h-screen max-w-[3840px] flex-col p-[2vw]">
        {/* Top: logo, clinic/branch name, live clock/date */}
        <header className="flex items-center justify-between border-b border-white/10 pb-[1.5vw]">
          <div className="flex items-center gap-4">
            {data?.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={data.logoUrl} alt="" className="h-[5vw] w-[5vw] max-h-24 max-w-24 rounded-lg object-contain" />
            ) : null}
            <div>
              <h1 className="text-[clamp(1.5rem,2.5vw,3rem)] font-bold">{data?.clinicName ?? "Clinic"}</h1>
              {data?.branchName ? (
                <p className="text-[clamp(0.9rem,1.2vw,1.5rem)] text-white/70">{data.branchName}</p>
              ) : null}
            </div>
          </div>
          <div className="text-right">
            <p className="text-[clamp(1.5rem,3vw,3.5rem)] font-mono font-semibold tabular-nums">
              {now ? now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--:--:--"}
            </p>
            <p className="text-[clamp(0.9rem,1.2vw,1.5rem)] text-white/70">
              {now ? now.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" }) : ""}
            </p>
          </div>
        </header>

        {/* Post-RC1 (50/50 Queue + Information/Advertisement Panel): the
            body splits into two equal-width halves - LEFT keeps the entire
            existing queue display (Now Serving + Next in Queue) completely
            unchanged, RIGHT is the new admin-configurable rotating info/ad
            panel. `min-h-0` on both the row and the left column preserves
            the exact same flexbox discipline already required for Now
            Serving/Next in Queue not to get cropped (see that section's own
            comment below) - now also needed one level up so the halved
            width doesn't reintroduce the same overflow bug. */}
        <div className="flex min-h-0 flex-1 gap-[1.5vw]">
        <div className="now-serving-container flex min-h-0 w-1/2 flex-col [container-type:inline-size]">
        {/* Center: Now Serving. Post-RC1 layout correction: every currently-
            serving ticket is ALWAYS its own individual card - one card, one
            ticket, one destination - never grouped into a stacked per-doctor/
            per-department column. A single active ticket renders as one
            large centered card; more tickets flow into a responsive grid
            that gets progressively denser as more are simultaneously active
            (see `getNowServingLayout`), so "Next in Queue" below never gets
            pushed off-screen. `min-h-0` is required here: a `flex-1` child
            otherwise refuses to shrink below its own content's height
            (flexbox's `min-height: auto` default), which was the actual bug
            - the section just grew to fit every card, silently pushing Next
            in Queue past the viewport where the page's deliberate
            `overflow-hidden` (nothing should ever require scrolling on a TV
            kiosk) clipped it out of view entirely. `overflow-y-auto` on the
            grid itself is a last-resort safety net for ticket counts beyond
            what any real clinic would realistically have simultaneously
            active - it does not kick in at normal counts. */}
        <section className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 py-[1.2cqw]">
          <p className="text-[clamp(1.1rem,4cqw,2rem)] font-semibold uppercase tracking-widest text-white/60">
            Now Serving
          </p>
          {data && primaryNowServing.length > 0 ? (
            (() => {
              const layout = getNowServingLayout(primaryNowServing.length, fontSizeClass);
              return (
                <div className={`min-h-0 overflow-y-auto ${layout.gridClassName}`}>
                  {primaryNowServing.map((entry) => (
                    <div
                      key={entry.queueId}
                      className={`rounded-2xl bg-white/10 text-center shadow-xl backdrop-blur ${layout.cardClassName}`}
                    >
                      <p className={`${layout.numberSizeClassName} font-extrabold tabular-nums`}>{entry.queueNumber}</p>
                      {/* Phase 2.7 (YAKAP Patient Classification): safe to
                          show publicly - queue number, classification,
                          doctor/department/room only. Never the patient's
                          name; `patientInitials` below remains the only
                          patient-identifying field on this public screen,
                          unchanged from the pre-existing design. */}
                      <p
                        className={`${layout.lineSpacingClassName} ${layout.initialsSizeClassName} font-semibold uppercase tracking-wide text-white/80`}
                      >
                        {entry.visitClassification === "Yakap" ? "YAKAP" : "Regular"}
                      </p>
                      <p className={`${layout.lineSpacingClassName} ${layout.initialsSizeClassName}`}>{entry.patientInitials}</p>
                      <p className={`${layout.lineSpacingClassName} ${layout.detailSizeClassName} text-white/70`}>
                        {entry.doctorName ? `Dr. ${entry.doctorName}` : entry.departmentName ?? ""}
                        {entry.roomName ? ` · ${entry.roomName}` : ""}
                      </p>
                    </div>
                  ))}
                </div>
              );
            })()
          ) : (
            <p className="text-[clamp(1.3rem,5cqw,3rem)] text-white/50">No one is currently being served</p>
          )}
        </section>

        {/* Next Queue - `shrink-0`: must never be compressed away by its
            flex sibling above, regardless of how many Now Serving cards
            there are. Each group's upcoming numbers are capped to
            `NEXT_IN_QUEUE_PER_GROUP` and shown WITHOUT the patient-initials
            subtitle (per explicit feedback) so they read as one compact
            single line instead of wrapping into two - this also keeps this
            section's natural height small and predictable regardless of how
            many tickets are actually waiting, which is what was starving
            "Now Serving" of its flex space and making its cards look
            cropped/scrolled. */}
        <section className="shrink-0 border-t border-white/10 pt-[1.5cqw]">
          <p className="mb-3 text-[clamp(1rem,3.2cqw,1.8rem)] font-semibold uppercase tracking-widest text-white/60">
            Next in Queue
          </p>
          {data && waitingGroups.some((g) => g.entries.length > 0) ? (
            waitingGroups.length <= 1 ? (
              <div className="flex flex-wrap gap-3">
                {(waitingGroups[0]?.entries ?? []).slice(0, NEXT_IN_QUEUE_PER_GROUP).map((entry) => (
                  <div key={entry.queueId} className="rounded-lg bg-white/5 px-5 py-3 text-center">
                    <p className="text-[clamp(1.1rem,4.4cqw,2.2rem)] font-bold tabular-nums">{entry.queueNumber}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {waitingGroups.map((group) => (
                  <div key={group.key}>
                    <p className="mb-2 text-[clamp(0.8rem,2.4cqw,1.2rem)] font-semibold uppercase tracking-wide text-white/50">
                      {group.label}
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {group.entries.slice(0, NEXT_IN_QUEUE_PER_GROUP).map((entry) => (
                        <div key={entry.queueId} className="rounded-lg bg-white/5 px-5 py-3 text-center">
                          <p className="text-[clamp(1.1rem,4.4cqw,2.2rem)] font-bold tabular-nums">{entry.queueNumber}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <p className="text-white/50">Queue is empty</p>
          )}
        </section>
        </div>

        <div className="w-1/2 [container-type:inline-size]">
          <InformationPanel items={data?.infoContent ?? []} />
        </div>
        </div>

        {/* Bottom: announcement ticker */}
        {data && data.announcements.length > 0 ? (
          <footer className="mt-6 overflow-hidden whitespace-nowrap rounded-lg bg-black/30 py-3">
            <div className="inline-block animate-[marquee_30s_linear_infinite] text-[clamp(0.9rem,1.2vw,1.5rem)]">
              {data.announcements.map((a) => (
                <span key={a.id} className="mx-8">
                  {a.message}
                </span>
              ))}
            </div>
          </footer>
        ) : null}
      </div>

      <style jsx global>{`
        @keyframes marquee {
          0% {
            transform: translateX(100%);
          }
          100% {
            transform: translateX(-100%);
          }
        }
      `}</style>
    </div>
  );
}
