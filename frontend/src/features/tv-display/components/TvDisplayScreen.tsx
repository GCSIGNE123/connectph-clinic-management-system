"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Maximize, Minimize, Volume2, VolumeX, WifiOff } from "lucide-react";
import { useTvDisplayRealtime } from "@/features/tv-display/hooks/use-tv-display-realtime";
import { groupNowServing, groupWaiting } from "@/features/tv-display/lib/grouping";
import { enqueueAnnouncement } from "@/lib/queue-announcer";

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

const FONT_SIZE_CLASS: Record<string, string> = {
  Small: "text-4xl md:text-5xl lg:[font-size:clamp(2rem,4vw,4.5rem)]",
  Medium: "text-5xl md:text-6xl lg:[font-size:clamp(2.5rem,5vw,5.5rem)]",
  Large: "text-6xl md:text-7xl lg:[font-size:clamp(3rem,6vw,7rem)]",
  ExtraLarge: "text-7xl md:text-8xl lg:[font-size:clamp(3.5rem,7.5vw,9rem)]",
};

const CURSOR_IDLE_MS = 3000;

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

  const nowServingGroups = useMemo(() => groupNowServing(data?.nowServing ?? []), [data]);
  const waitingGroups = useMemo(() => groupWaiting(data?.nextWaiting ?? []), [data]);

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

        {/* Center: Now Serving. A single active destination (the original,
            still-common single-doctor-clinic case) renders as one flat grid
            with no group heading - unchanged from before this feature. Two
            or more simultaneous destinations (e.g. Dr. A, Dr. B, Laboratory)
            each get their own labeled card group so it's always clear which
            number belongs where, without ever shrinking the queue-number
            typography below the existing comfortable-viewing-distance size. */}
        <section className="flex flex-1 flex-col items-center justify-center gap-6 py-[2vw]">
          <p className="text-[clamp(1.1rem,1.5vw,2rem)] font-semibold uppercase tracking-widest text-white/60">
            Now Serving
          </p>
          {data && data.nowServing.length > 0 ? (
            nowServingGroups.length <= 1 ? (
              <div className="grid w-full grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {data.nowServing.map((entry) => (
                  <div key={entry.queueId} className="rounded-2xl bg-white/10 p-[1.5vw] text-center shadow-xl backdrop-blur">
                    <p className={`${fontSizeClass} font-extrabold tabular-nums`}>{entry.queueNumber}</p>
                    <p className="mt-2 text-[clamp(1rem,1.6vw,2rem)]">{entry.patientInitials}</p>
                    <p className="mt-1 text-[clamp(0.8rem,1.1vw,1.5rem)] text-white/70">
                      {entry.doctorName ? `Dr. ${entry.doctorName}` : entry.departmentName ?? ""}
                      {entry.roomName ? ` · ${entry.roomName}` : ""}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
                {nowServingGroups.map((group) => (
                  <div key={group.key} className="rounded-2xl bg-white/10 p-[1.2vw] shadow-xl backdrop-blur">
                    <p className="mb-2 text-center text-[clamp(0.9rem,1.1vw,1.4rem)] font-semibold uppercase tracking-wide text-white/70">
                      {group.label}
                    </p>
                    <div className="flex flex-col items-center gap-3">
                      {group.entries.map((entry) => (
                        <div key={entry.queueId} className="w-full text-center">
                          <p className={`${fontSizeClass} font-extrabold tabular-nums`}>{entry.queueNumber}</p>
                          <p className="text-[clamp(0.8rem,1.2vw,1.6rem)]">{entry.patientInitials}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            <p className="text-[clamp(1.3rem,2vw,3rem)] text-white/50">No one is currently being served</p>
          )}
        </section>

        {/* Next Queue */}
        <section className="border-t border-white/10 pt-[1.5vw]">
          <p className="mb-3 text-[clamp(1rem,1.3vw,1.8rem)] font-semibold uppercase tracking-widest text-white/60">
            Next in Queue
          </p>
          {data && data.nextWaiting.length > 0 ? (
            waitingGroups.length <= 1 ? (
              <div className="flex flex-wrap gap-3">
                {data.nextWaiting.map((entry) => (
                  <div key={entry.queueId} className="rounded-lg bg-white/5 px-5 py-3 text-center">
                    <p className="text-[clamp(1.1rem,1.8vw,2.2rem)] font-bold tabular-nums">{entry.queueNumber}</p>
                    <p className="text-[clamp(0.7rem,0.9vw,1.2rem)] text-white/60">{entry.patientInitials}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {waitingGroups.map((group) => (
                  <div key={group.key}>
                    <p className="mb-2 text-[clamp(0.8rem,1vw,1.2rem)] font-semibold uppercase tracking-wide text-white/50">
                      {group.label}
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {group.entries.map((entry) => (
                        <div key={entry.queueId} className="rounded-lg bg-white/5 px-5 py-3 text-center">
                          <p className="text-[clamp(1.1rem,1.8vw,2.2rem)] font-bold tabular-nums">{entry.queueNumber}</p>
                          <p className="text-[clamp(0.7rem,0.9vw,1.2rem)] text-white/60">{entry.patientInitials}</p>
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
