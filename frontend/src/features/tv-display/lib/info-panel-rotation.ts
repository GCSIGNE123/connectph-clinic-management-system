import type { TvInfoContentItem } from "@/features/tv-display/types";

/**
 * Post-RC1 (50/50 Queue + Information/Advertisement Panel): pure function
 * mapping "how many milliseconds has the panel been mounted" to "which item
 * should be showing right now", given each item's own `durationSeconds`.
 * Kept pure/framework-free (no timers, no React) so rotation logic is
 * directly unit-testable without mocking `setInterval` - the component
 * (`InformationPanel.tsx`) just re-derives the index on a fixed tick.
 *
 * Only active items participate; the list passed in should already be
 * filtered/sorted by the caller (server already returns active-only,
 * ordered by `display_order` - see `TvDisplayService.list_active_for_clinic`).
 */
export function getRotationIndex(items: TvInfoContentItem[], elapsedMs: number): number {
  if (items.length === 0) return -1;
  const totalMs = items.reduce((sum, item) => sum + item.durationSeconds * 1000, 0);
  if (totalMs <= 0) return 0;
  let offset = ((elapsedMs % totalMs) + totalMs) % totalMs;
  for (let i = 0; i < items.length; i++) {
    const durationMs = items[i].durationSeconds * 1000;
    if (offset < durationMs) return i;
    offset -= durationMs;
  }
  return items.length - 1;
}
