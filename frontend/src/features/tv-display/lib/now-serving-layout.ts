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
  /** Patient-initials line. Post-RC1 (overflow fix #2): previously a single
   * fixed size shared by every tier - fine at 1-4 tickets, but at 5+ it
   * kept every card's second line the same height regardless of how many
   * rows had to fit in the section's bounded height, contributing to the
   * grid genuinely overflowing (not just visually tight) at realistic
   * multi-department ticket counts (verified live: 8 simultaneous tickets
   * at 1600x900 measured 444px of required grid height against only 336px
   * available). Now tier-aware like `numberSizeClassName`. */
  initialsSizeClassName: string;
  /** Doctor-name/department/room line - same tier-aware fix as above. */
  detailSizeClassName: string;
  /** Vertical gap above the initials/detail lines - also tightened at
   * higher tiers so line-spacing doesn't eat back the savings from
   * shrinking the text itself. */
  lineSpacingClassName: string;
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
const MODERATE_NUMBER_SIZE = "text-4xl md:text-5xl lg:[font-size:clamp(1.8rem,6.3cqw,3.75rem)]";
const COMPACT_NUMBER_SIZE = "text-3xl md:text-4xl lg:[font-size:clamp(1.4rem,5cqw,2.75rem)]";

const MODERATE_INITIALS_SIZE = "text-[clamp(0.85rem,3.4cqw,1.4rem)]";
const COMPACT_INITIALS_SIZE = "text-[clamp(0.75rem,2.6cqw,1.1rem)]";

const MODERATE_DETAIL_SIZE = "text-[clamp(0.7rem,2.2cqw,1.05rem)]";
const COMPACT_DETAIL_SIZE = "text-[clamp(0.65rem,1.8cqw,0.85rem)]";

export function getNowServingLayout(count: number, baseNumberSizeClassName: string): NowServingLayout {
  if (count <= 1) {
    return {
      gridClassName: "flex w-full justify-center",
      cardClassName: "w-full max-w-2xl p-[1.5cqw]",
      numberSizeClassName: baseNumberSizeClassName,
      initialsSizeClassName: "text-[clamp(1rem,4.5cqw,2rem)]",
      detailSizeClassName: "text-[clamp(0.8rem,3cqw,1.5rem)]",
      lineSpacingClassName: "mt-2",
    };
  }
  if (count <= 4) {
    return {
      gridClassName: "grid w-full grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3",
      cardClassName: "p-[1.5cqw]",
      numberSizeClassName: baseNumberSizeClassName,
      initialsSizeClassName: "text-[clamp(1rem,4.5cqw,2rem)]",
      detailSizeClassName: "text-[clamp(0.8rem,3cqw,1.5rem)]",
      lineSpacingClassName: "mt-2",
    };
  }
  if (count <= 8) {
    return {
      gridClassName: "grid w-full grid-cols-2 gap-2 lg:grid-cols-4",
      cardClassName: "p-[0.4cqw]",
      numberSizeClassName: MODERATE_NUMBER_SIZE,
      initialsSizeClassName: MODERATE_INITIALS_SIZE,
      detailSizeClassName: MODERATE_DETAIL_SIZE,
      lineSpacingClassName: "mt-1",
    };
  }
  // 9+ simultaneous tickets: denser grid (up to 6 columns), smaller padding,
  // and a capped queue-number size so more rows fit within the section's
  // bounded height without needing to scroll in realistic clinic scenarios.
  // The grid wrapper itself is still given `overflow-y-auto` by the caller
  // as a last-resort safety net for pathological ticket counts beyond what
  // any real clinic would have simultaneously active - it should not
  // normally engage at realistic counts now that every tier's sizing is
  // actually budgeted to fit rather than just "smaller than the last tier".
  return {
    gridClassName: "grid w-full grid-cols-3 gap-2 lg:grid-cols-4 2xl:grid-cols-6",
    cardClassName: "p-[0.35cqw]",
    numberSizeClassName: COMPACT_NUMBER_SIZE,
    initialsSizeClassName: COMPACT_INITIALS_SIZE,
    detailSizeClassName: COMPACT_DETAIL_SIZE,
    lineSpacingClassName: "mt-0.5",
  };
}
