"use client";

import { useEffect, useState } from "react";
import { resolveTvMediaUrl } from "@/features/tv-display/api/tv-display-api";
import { getRotationIndex } from "@/features/tv-display/lib/info-panel-rotation";
import type { TvInfoContentItem } from "@/features/tv-display/types";

/**
 * Post-RC1 (50/50 Queue + Information/Advertisement Panel): the right half
 * of the TV Display. Purely presentational - all rotation timing math lives
 * in the pure, unit-tested `getRotationIndex` (see `lib/info-panel-rotation.ts`);
 * this component just re-derives "which index is current" on a fixed tick
 * and cross-fades between items (`transition-opacity`, no slide/bounce/
 * distracting motion - a waiting-room requirement from the spec).
 *
 * Content is entirely admin-configured (`items` comes straight from
 * `TvDisplayData.infoContent`, already active-only + ordered by the
 * backend) - no hardcoded clinic content here, and nothing here depends on
 * any network/cloud service, so it keeps working offline exactly like the
 * rest of the TV Display.
 */

const TICK_MS = 500;

const CONTENT_TYPE_LABEL: Record<TvInfoContentItem["contentType"], string> = {
  ServicePricing: "Services & Pricing",
  DoctorInfo: "Meet Our Doctors",
  HealthTip: "Health Tip",
  PreventiveReminder: "Preventive Health",
  Announcement: "Announcement",
  Promotion: "Promotion",
  Motivational: "",
};

export function InformationPanel({ items }: { items: TvInfoContentItem[] }) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    setElapsedMs(0);
    const start = Date.now();
    const t = setInterval(() => setElapsedMs(Date.now() - start), TICK_MS);
    return () => clearInterval(t);
  }, [items]);

  const index = getRotationIndex(items, elapsedMs);
  const current = index >= 0 ? items[index] : null;

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl bg-white/5 p-[4cqw]">
      <p className="mb-[3cqw] text-[clamp(1.1rem,4cqw,2rem)] font-semibold uppercase tracking-widest text-white/60">
        Clinic Information
      </p>
      {current ? (
        <div key={current.id} className="flex min-h-0 flex-1 flex-col items-center justify-center text-center animate-[info-fade-in_0.6s_ease]">
          {CONTENT_TYPE_LABEL[current.contentType] ? (
            <p className="mb-[2cqw] text-[clamp(0.9rem,2.8cqw,1.4rem)] font-semibold uppercase tracking-wide text-white/50">
              {CONTENT_TYPE_LABEL[current.contentType]}
            </p>
          ) : null}
          {current.imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolveTvMediaUrl(current.imageUrl) ?? undefined}
              alt=""
              className="mb-[3cqw] max-h-[30vh] max-w-full rounded-xl object-contain"
            />
          ) : null}
          <h2 className="text-[clamp(1.8rem,8.5cqw,4rem)] font-bold">{current.title}</h2>
          <p className="mt-[2.5cqw] max-w-[90%] whitespace-pre-line text-[clamp(1.1rem,4.8cqw,2.2rem)] text-white/80">
            {current.body}
          </p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <p className="text-[clamp(1.1rem,4cqw,2rem)] text-white/40">No information to display</p>
        </div>
      )}
      {items.length > 1 ? (
        <div className="mt-[3cqw] flex shrink-0 items-center justify-center gap-2">
          {items.map((item, i) => (
            <span
              key={item.id}
              className={`h-2 w-2 rounded-full transition-colors ${i === index ? "bg-white" : "bg-white/25"}`}
            />
          ))}
        </div>
      ) : null}
      <style jsx global>{`
        @keyframes info-fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}</style>
    </section>
  );
}
