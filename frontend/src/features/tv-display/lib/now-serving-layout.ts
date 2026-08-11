/**
 * Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display - overflow fix):
 * picks a density tier for the "Now Serving" one-card-per-ticket grid based
 * on how many tickets are simultaneously active.
 *
 * Root cause this fixes: the Now Serving `<section>` is a `flex-1` flex
 * item. Flex items default to `min-height: auto`, which means they refuse
 * to shrink below their own content's intrinsic height - so as more ticket
 * cards were added, the section just grew taller instead of respecting its
 * allotted space, pushing "Next in Queue" below the viewport where the
 * page's own `overflow-hidden` (deliberate for a TV kiosk - nothing should
 * ever require scrolling/interaction) silently clipped it out of view
 * entirely. The component pairs this tiering with `min-h-0` on the section
 * and a bounded, internally-scrollable grid wrapper as a last-resort safety
 * net - see `TvDisplayScreen.tsx`.
 *
 * Extracted as a pure function (matching `grouping.ts`'s pattern) so the
 * tier thresholds are independently testable without rendering the component.
 */
export interface NowServingLayout {
  gridClassName: string;
  cardClassName: string;
  numberSizeClassName: string;
}

// Used from 5 tickets up, where the admin-configured font size
// (Small/Medium/Large/ExtraLarge, passed in as `baseNumberSizeClassName`)
// no longer leaves enough room for 2+ rows of cards within the section's
// bounded height without cropping/scrolling - only the 1-4 tier uses the
// admin's own configured size at full size. `MODERATE` is used for 5-8
// (still comfortably readable, just not as huge); `COMPACT` for 9+ (denser
// grid, needs to be smaller still).
// `cqw` (container query width), not `vw` - see `TvDisplayScreen.tsx`'s
// `FONT_SIZE_CLASS` comment: Now Serving lives in a halved-width column
// (Post-RC1 50/50 Queue + Information Panel layout), so sizing must track
// that column's real width, not the full viewport's.
const MODERATE_NUMBER_SIZE = "text-5xl md:text-6xl lg:[font-size:clamp(2.2rem,8.4cqw,5rem)]";
const COMPACT_NUMBER_SIZE = "text-4xl md:text-5xl lg:[font-size:clamp(1.8rem,7cqw,4rem)]";

export function getNowServingLayout(count: number, baseNumberSizeClassName: string): NowServingLayout {
  if (count <= 1) {
    return {
      gridClassName: "flex w-full justify-center",
      cardClassName: "w-full max-w-2xl p-[1.5cqw]",
      numberSizeClassName: baseNumberSizeClassName,
    };
  }
  if (count <= 4) {
    return {
      gridClassName: "grid w-full grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3",
      cardClassName: "p-[1.5cqw]",
      numberSizeClassName: baseNumberSizeClassName,
    };
  }
  if (count <= 8) {
    return {
      gridClassName: "grid w-full grid-cols-2 gap-3 lg:grid-cols-4",
      cardClassName: "p-[0.5cqw]",
      numberSizeClassName: MODERATE_NUMBER_SIZE,
    };
  }
  // 9+ simultaneous tickets: denser grid (up to 6 columns), smaller padding,
  // and a capped queue-number size so more rows fit within the section's
  // bounded height without needing to scroll in realistic clinic scenarios.
  // The grid wrapper itself is still given `overflow-y-auto` by the caller
  // as a safety net for pathological ticket counts beyond what any
  // reasonable clinic would have simultaneously active.
  return {
    gridClassName: "grid w-full grid-cols-3 gap-3 lg:grid-cols-4 2xl:grid-cols-6",
    cardClassName: "p-[0.6cqw]",
    numberSizeClassName: COMPACT_NUMBER_SIZE,
  };
}
