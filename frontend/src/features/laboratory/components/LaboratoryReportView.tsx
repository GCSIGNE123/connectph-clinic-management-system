import { FlaskConical } from "lucide-react";
import { FlagText } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratorySignatoryFooter } from "@/features/laboratory/components/LaboratorySignatoryFooter";
import {
  buildAgeSexLine,
  buildCategoryHeading,
  buildReportRows,
  compactReferenceLines,
  groupReportRowsBySection,
  isClinicalMicroscopyCategory,
  isQualitativeCategoricalRow,
  plainResultValue,
  reportResultValue,
  resolveSectionLayoutMode,
  type LaboratoryReportRow,
} from "@/features/laboratory/lib/report";
import { formatDateTime } from "@/lib/utils";
import { resolveMediaUrl } from "@/lib/api-url";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Every cell reads directly off the persisted `LaboratoryResult`
 * (`units`/`normalRange`/`interpretation`) - never recalculated from the
 * current template, so historical results keep printing exactly what was
 * true when they were released, even if the template's reference ranges
 * change later.
 *
 * 2026-09 (clinic manual-report reference): the report is no longer one
 * universal table for every test - see `StandardResultTable` and
 * `resolveSectionLayoutMode` for the three per-section layouts (Hematology
 * 5-column "detailed", Blood-Chemistry-style 3-column "compact", and the
 * bare 2-column "plain" for a test with no configured unit/range at all)
 * this now dispatches to, matching the clinic's own existing paper reports
 * for each test category instead of forcing every result into the same
 * five columns. */

/** Phase 4G: generic, template-driven read-only laboratory report body -
 * every field comes from the already-fetched `LaboratoryOrder` (via
 * `getOrder`, the only call site that populates `clinicName`), grouped and
 * type-rendered purely from `order.template`/`order.results` metadata. No
 * `if testType === "..."` branch anywhere - a future 7th/8th laboratory
 * test renders through this exact same component with zero changes.
 *
 * Round 2 (clinic-approved reference layout): compact clinical-document
 * spacing throughout (tight header, two-column info block, dense table
 * rows, navy header band) instead of the airier first-pass redesign -
 * still the exact same five columns/data sources, just laid out to use
 * the Letter page the way the clinic's own Word-based report already did. */
export function LaboratoryReportView({ order }: { order: LaboratoryOrder }) {
  // Qualitative Positive/Negative matrix layout (per-clinic sample: one row
  // per TEST, one column per Categorical parameter - "TEST | NS1 | IgM |
  // IgG" for Dengue Rapid Test, "TEST | HBsAg" for a single-parameter test)
  // vs. the existing five-column quantitative layout - decided PER ROW via
  // `isQualitativeCategoricalRow` (options + resultType, never a test-name
  // check), so a template that genuinely mixes both kinds of parameters
  // still prints each kind through its own correct layout. In every
  // template actually seeded/configured in this codebase a test is
  // entirely one kind or the other, so in practice exactly one of the two
  // tables below renders.
  // Fix (section-integrity defect found by the Phase 10 visual audit): group
  // ALL rows - standard AND qualitative-matrix alike - by section BEFORE
  // splitting each group's own rows into its standard table vs its matrix,
  // rather than pre-filtering categorical rows out into one report-wide
  // matrix rendered after every section. The old pre-filter approach lost a
  // section's own heading entirely whenever every one of that section's rows
  // happened to be Positive/Negative-valued (the section's row list went to
  // zero after the filter), and visually severed a Positive/Negative
  // parameter from the rest of its own section (it always re-appeared in one
  // shared matrix at the very end of the report, regardless of which section
  // it belonged to) - see LaboratoryReportView.test.tsx's "#2/#14" and "7"
  // section-heading tests, and the audit's "Mixed Type Stress Panel"
  // screenshot. Grouping first keeps every section's heading exactly where
  // its rows say it belongs, and its own matrix rows immediately beneath it.
  const allRows = buildReportRows(order);
  const groups = groupReportRowsBySection(allRows);
  // Round 5: clinic contact line - bullet-joins only the fields that are
  // actually configured (never a fake placeholder, never a dangling "•"
  // for a missing field), sourced entirely from the existing clinic
  // config carried on `order` alongside `clinicName`.
  const contactLine = [order.clinicAddress, order.clinicPhone, order.clinicEmail].filter(Boolean).join(" • ");
  // Round 7: the shared clinic branding logo, appearing BEFORE the clinic
  // name - same shared `Clinic.logo_url` value the TV Display header now
  // reads (see `TvDisplayScreen.tsx`). Falls back to the existing
  // `FlaskConical` icon when no logo is configured, exactly preserving the
  // prior text-only header rather than leaving a blank gap.
  const logoUrl = resolveMediaUrl(order.clinicLogoUrl);
  // Client requirement: an overall category heading ("HEMATOLOGY TEST",
  // "SEROLOGY TEST", ...) between the header and the results content -
  // see `buildCategoryHeading`'s own doc comment for the full rationale.
  // The de-dup guard only applies when the matrix layout is what's about
  // to render (it already prints the parent test name as its own first
  // cell/row label) - a standard report has no equivalent adjacent
  // duplicate to guard against.
  // The adjacent-label de-dup guard only matters when a matrix immediately
  // follows the overall heading with nothing in between - i.e. the report's
  // very first group has no section AND every one of its rows is a matrix
  // row. A sectioned report never has this adjacency (a section heading
  // always sits between the overall heading and any matrix), so it never
  // needs the guard, regardless of how many matrix rows exist elsewhere.
  const firstGroup = groups[0];
  const firstGroupIsPureMatrix =
    !!firstGroup && firstGroup.section === null && firstGroup.rows.length > 0 && firstGroup.rows.every(isQualitativeCategoricalRow);
  const categoryHeading = buildCategoryHeading(order.template?.testCategory, firstGroupIsPureMatrix ? order.testType : null);
  // Client requirement: report-header "Age / Sex" row (e.g. "22 yrs / M"),
  // above Status in the right column - see `buildAgeSexLine`'s own doc
  // comment for the missing-data/formatting rules. Sourced entirely from
  // the already-fetched `order.patientAge`/`patientSex` (computed by the
  // backend from the patient's existing birth date/gender - no new field,
  // no client-side date math).
  const ageSexLine = buildAgeSexLine(order.patientAge, order.patientSex);

  return (
    // Layout-only change: this root becomes a flex COLUMN so the signatory
    // footer below (`mt-auto`) can be pushed toward the bottom of the page
    // instead of sitting immediately after Notes. `flex-1` only takes
    // effect when an ancestor is itself `display:flex` (the on-screen
    // print-preview box and the print portal root both are now, scoped via
    // `LaboratoryReportDialog`'s own CSS - see its doc comments) - stretching
    // this root to that ancestor's full (at-least-one-page) height, which is
    // what gives `mt-auto` room to push into. Rendered anywhere else
    // (bare unit tests, any other embed with no flex ancestor), `flex-1`
    // is simply inert and this behaves exactly as before: the footer sits
    // right after Notes with no gap, since there's no extra height for
    // `mt-auto` to consume. No fixed/forced height anywhere - a report
    // whose content genuinely exceeds one page still grows naturally and
    // paginates, it just doesn't create a page for the footer alone.
    <div id="laboratory-report-body" className="flex w-full flex-1 flex-col text-[11px] leading-tight sm:text-xs">
      <div className="flex items-center justify-center gap-2 pb-1 pt-0.5 text-center">
        {logoUrl ? (
          // Round 7 follow-up: enlarged from h-8 (32px) to h-12/h-14
          // (48px/56px) - the original icon-sized rendering read as
          // visually insignificant next to the clinic name. Still
          // `object-contain` (never stretched/cropped) and still
          // vertically centered against the clinic name block via the
          // parent's `items-center` - only the size changed.
          // eslint-disable-next-line @next/next/no-img-element -- external/backend-relative logo, not a static/optimizable asset
          <img src={logoUrl} alt="" className="h-12 w-12 shrink-0 object-contain sm:h-14 sm:w-14" />
        ) : (
          <FlaskConical className="h-6 w-6 shrink-0 text-slate-700" aria-hidden />
        )}
        <div>
          {order.clinicName ? <p className="text-base font-bold uppercase tracking-wide text-slate-900 sm:text-lg">{order.clinicName}</p> : null}
          {contactLine ? <p className="text-[9px] text-muted-foreground sm:text-[10px]">{contactLine}</p> : null}
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground sm:text-xs">Laboratory Report</p>
        </div>
      </div>

      {/* Client feedback (header rearrange): the Test field is removed
          from the header entirely now, for EVERY report type - it was
          previously kept for a standard (non-matrix) report and only
          omitted for a qualitative matrix report (whose matrix already
          shows the parent test name as its own first cell/row label), but
          the client decided the report's own content/section heading
          below already identifies the test either way, so the header
          field is redundant in both cases. Left column is now Patient
          Name / Requesting Doctor / Visit # / Order No., in that order -
          Visit # is deliberately kept (a Visit represents the clinic
          encounter and exists even for a walk-in/direct-to-laboratory
          patient); Requesting Doctor legitimately reads "-" for one.
          Right column is Age / Sex / Collected / Completed / Released, in
          that order - Order No. simply moved out of it into the left
          column's fourth row.

          Client requirement (Age/Sex): a first row in this right column -
          see `buildAgeSexLine`'s own doc comment.

          Client requirement (remove Status row): the "Status : Released"
          row is gone entirely now - the report already carries the
          order's outcome via the "Released" DATE/TIME row immediately
          below (kept, unchanged) and the client considered the separate
          word-status label redundant with it. This removes only the
          `order.status` InfoRow - `order.releasedAt`'s own "Released"
          row (a timestamp, not a status word) is a completely different
          field/row and stays exactly as it was. */}
      <div className="grid min-w-0 grid-cols-2 gap-x-4 border-y-2 border-slate-800 py-1.5">
        <div>
          <InfoRow label="Patient Name" value={order.patientName} />
          <InfoRow label="Requesting Doctor" value={order.doctorName} />
          <InfoRow label="Visit #" value={order.visitNumber} />
          <InfoRow label="Order No." value={order.orderNumber} />
        </div>
        <div>
          <InfoRow label="Age / Sex" value={ageSexLine} />
          <InfoRow label="Collected" value={order.collectedAt ? formatDateTime(order.collectedAt) : null} />
          <InfoRow label="Completed" value={order.completedAt ? formatDateTime(order.completedAt) : null} />
          <InfoRow label="Released" value={order.releasedAt ? formatDateTime(order.releasedAt) : null} />
        </div>
      </div>

      {/* Client requirement: the overall category heading sits here -
          below the patient/order info block, above the results content
          (standard table or qualitative matrix, whichever renders) - and
          is centered, distinguishing it from the per-parameter subsection
          headings below (e.g. "Physical Examination"), which stay
          left-aligned with their own border-bottom rule. Omitted entirely
          (not a blank centered line) when the template has no
          `testCategory` configured, or for an untemplated order - never a
          fabricated label. */}
      {categoryHeading ? (
        <p className="mt-1.5 text-center text-[10px] font-bold uppercase tracking-wide text-slate-800 sm:text-[11px]">
          {categoryHeading}
        </p>
      ) : null}

      <div className="mt-2 space-y-2.5">
        {groups.map((group, groupIndex) => {
          // Working assumption (Blood Typing, 2026-09): a group can mix a
          // qualifying Positive/Negative Categorical row (e.g. Rh Factor)
          // with a NON-qualifying Categorical row (e.g. ABO Group's A/B/AB/O
          // - see report.test.ts's "Blood Type" fixture, which deliberately
          // asserts `isQualitativeCategoricalRow` stays false for it). Left
          // to `isQualitativeCategoricalRow` alone, that would split the two
          // sibling Categorical parameters into two visually mismatched
          // tables (Rh Factor's matrix row is labeled with the overall
          // `testType`, not "Rh Factor"). Detected purely from the row data
          // (any Categorical row in the group that ISN'T qualifying) - a
          // qualifying row only joins the matrix when every OTHER Categorical
          // row in its own group also qualifies, keeping same-family
          // Categorical parameters in one consistent table together. A
          // non-Categorical sibling (e.g. Titer) never triggers this - see
          // LaboratoryReportView.test.tsx's "#15" (Titer + multi-site
          // Categorical), which still needs each row rendered independently.
          const hasNonQualitativeCategorical = group.rows.some(
            (row) => row.results.some((r) => r.resultType === "Categorical") && !isQualitativeCategoricalRow(row)
          );
          // Medtech feedback (Blood Typing, real A4 print review): ABO Group
          // + Rh Factor must print as ONE combined line ("BLOOD TYPING" |
          // "O POSITIVE"), not two separate PARAMETER rows - real-world
          // blood typing is reported as a single combined designation, not
          // per-antigen rows. Detected purely from the data: MORE THAN ONE
          // row in the group (combining only makes sense for 2+ parameters -
          // a lone non-Positive/Negative Categorical result, e.g. an
          // unexpected/ad-hoc "ABO Group" with an Abnormal flag, still needs
          // its own ordinary row so its interpretation keeps printing - see
          // LaboratoryReportView.test.tsx's Categorical-Flag-'A' tests),
          // every row is Categorical (never a name check), and the group
          // already isn't matrix-eligible (`hasNonQualitativeCategorical`,
          // same condition the fix above uses) - a group mixing Categorical
          // with a genuinely different result type (e.g. Titer, see test
          // "#15") never qualifies, so those rows still print independently.
          const isCombinedCategoricalGroup =
            hasNonQualitativeCategorical &&
            group.rows.length > 1 &&
            group.rows.every((row) => row.results.every((r) => r.resultType === "Categorical"));
          const standardRows = isCombinedCategoricalGroup
            ? []
            : group.rows.filter((row) => !isQualitativeCategoricalRow(row) || hasNonQualitativeCategorical);
          const categoricalRows = isCombinedCategoricalGroup
            ? []
            : group.rows.filter((row) => isQualitativeCategoricalRow(row) && !hasNonQualitativeCategorical);
          const layoutMode = resolveSectionLayoutMode(order.template?.testCategory, standardRows);
          return (
            <div key={groupIndex}>
              {group.section ? (
                <h3 className="section-heading mb-0.5 mt-1.5 border-b border-slate-400 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-800 first:mt-0 sm:text-[11px]">
                  {group.section}
                </h3>
              ) : null}
              {isCombinedCategoricalGroup ? (
                <CombinedCategoricalRow testLabel={order.testType} rows={group.rows} />
              ) : (
                <>
                  {standardRows.length > 0 ? (
                    <StandardResultTable
                      mode={layoutMode}
                      rows={standardRows}
                      specimenType={order.template?.specimenType ?? null}
                      testCategory={order.template?.testCategory ?? null}
                    />
                  ) : null}
                  {categoricalRows.length > 0 ? (
                    <QualitativeResultMatrix
                      testLabel={order.testType}
                      rows={categoricalRows}
                      specimenType={order.template?.specimenType ?? null}
                      testCategory={order.template?.testCategory ?? null}
                    />
                  ) : null}
                </>
              )}
            </div>
          );
        })}
        {allRows.length === 0 ? <p className="py-2 text-muted-foreground">No results entered yet.</p> : null}
      </div>

      <div className="report-notes mt-3 rounded-sm border border-border px-2 py-1.5 text-[9px] text-muted-foreground sm:text-[10px]">
        <p className="mb-0.5 font-semibold uppercase tracking-wide text-slate-700">Note:</p>
        <ul className="list-disc space-y-0.5 pl-4">
          <li>This report is system-generated.</li>
          <li>Reference ranges may vary based on age, sex, and clinical condition.</li>
          {/* Medtech feedback (real A4 print review): all three note bullets
              on every report, not just ones with a qualitative Positive/
              Negative matrix - a purely quantitative report (CBC, Blood
              Chemistry, ...) gets the "refer to your doctor" line too now. */}
          <li>Please refer to your doctor for interpretation of the results.</li>
        </ul>
      </div>

      {/* Round 6 (Laboratory Report Signatories): Med Tech In Charge (left)
          + Pathologist (right), captured once at release - see
          `LaboratorySignatoryFooter`'s own docstring. Always the LAST
          thing in the report - after the result table and notes - never
          repeated per page/section.

          Client feedback (round 2): the "MED TECHNOLOGIST IN CHARGE" /
          "PATHOLOGIST" role headings above each signature are redundant on
          EVERY report - the name + license + role line beneath already
          identifies the signatory. Previously removed ONLY for a matrix
          report (a now-removed `showHeading` prop this call site set
          `false` for); `LaboratorySignatoryFooter` itself no longer ever
          renders the heading, for standard and matrix reports alike - one
          call site, no report-type-specific opt-in/out.

          Round 9 (true page footer): `mt-auto` is the entire mechanism -
          in the flex column this root now is, it consumes all leftover
          height above itself, pushing the footer down toward the bottom of
          the page for a short report while never overlapping the results/
          notes above (flexbox only ever gives it space that's actually
          free) and never forcing a page just for itself (a report that
          already fills/exceeds one page leaves no leftover height, so the
          footer simply follows immediately after Notes, exactly like
          before this change). `LaboratorySignatoryFooter` itself is
          completely unmodified - this is a wrapper `<div>` around the same
          call, not a change to the footer's own markup or logic. */}
      <div className="mt-auto">
        <LaboratorySignatoryFooter order={order} />
      </div>
    </div>
  );
}

/** Per-clinic manual-report reference table for non-categorical results -
 * see `resolveSectionLayoutMode`'s own doc comment for exactly which mode
 * a section gets and why. "detailed" is the prior 5-column table (kept
 * byte-for-byte, just extracted here), used only for a genuine Hematology
 * panel like CBC. "compact" is the clinic's own Blood Chemistry/Thyroid-
 * PSA/Clotting-Bleeding-Time 3-column TEST/RESULT/REFERENCE layout - no
 * Unit column, no Flag/Remarks column, `compactReferenceValue` folds the
 * unit into the REFERENCE cell when the range text doesn't already contain
 * it. "plain" drops the REFERENCE column entirely for a test with no
 * unit/range configured on any of its results at all (Stool Examination,
 * Gram Stain) - matching those tests' own paper reports, which have no
 * such column either. */
// Widths tuned so every header word fits on one line at real print width -
// "flag" was 8% (only wide enough for ~4 characters at this font size),
// which wrapped "REMARKS" mid-word in an actual A4 print (confirmed via a
// real print-pipeline PDF, not just the narrow on-screen preview box -
// see the medtech screenshot this was reported from). "reference" had
// substantial unused slack at 35% (its own header, "REFERENCE", is barely
// shorter than "REMARKS" and fits comfortably well under 35%), so this
// only redistributes existing width - still sums to exactly 100%.
// One shared shape (rather than 4 differently-keyed object literals) so
// `widths` below has a single consistent type - the four modes' widths
// otherwise form a union type that TypeScript correctly refuses to read
// `.unit`/`.reference`/`.flag`/`.specimen` off of (not every mode's literal
// has those keys), a real type error `tsc --noEmit` catches even though it
// silently passed through the dev server and test runner (both strip types
// without full type-checking). Each unused key is simply omitted per mode.
interface ColumnWidths {
  test: string;
  result: string;
  unit?: string;
  reference?: string;
  flag?: string;
  specimen?: string;
}

const DETAILED_COLUMN_WIDTHS: ColumnWidths = { test: "28%", result: "14%", unit: "13%", reference: "31%", flag: "14%" };
const COMPACT_COLUMN_WIDTHS: ColumnWidths = { test: "38%", result: "22%", reference: "40%" };
const PLAIN_COLUMN_WIDTHS: ColumnWidths = { test: "45%", result: "55%" };
// Medtech feedback (Gram Stain/Sputum Exam, real A4 print review): a
// single-parameter "plain" test (a free-text finding with no unit/range at
// all) must show its specimen, per the clinic's own "Miscellaneous" report
// family (TEST | SPECIMEN | RESULT). Only ever added for a SINGLE-row plain
// group (see `showSpecimen` below) - a multi-row plain test like Stool
// Exam (7 parameters under one specimen) keeps its existing plain TEST |
// RESULT columns unchanged, matching that family's own separate spec.
const PLAIN_WITH_SPECIMEN_COLUMN_WIDTHS: ColumnWidths = { test: "28%", specimen: "27%", result: "45%" };

function StandardResultTable({
  mode,
  rows,
  specimenType,
  testCategory,
}: {
  mode: "detailed" | "compact" | "plain";
  rows: LaboratoryReportRow[];
  specimenType?: string | null;
  testCategory?: string | null;
}) {
  const testHeader = mode === "detailed" ? "Parameter" : "Test";
  const showSpecimen =
    mode === "plain" && rows.length === 1 && !!specimenType?.trim() && isClinicalMicroscopyCategory(testCategory);
  // Medtech feedback (ALP/OGTT, real A4 print review): a compact-mode
  // table with NO row carrying a real configured `normalRange` (only a
  // bare unit, e.g. ALP's "U/L" or OGTT's "mg/dL" with no established
  // cutoff at all) must not label that column "REFERENCE" - there is no
  // reference being shown, only a unit ("*unit lng na ibutang sir kay wala
  // mi reference value"). A table with at least one real range (e.g.
  // FBS/RBS's Glucose Fasting) keeps the "REFERENCE" label even if a
  // sibling row in the same table has no range of its own.
  const hasAnyRealRange = rows.some((row) => row.results.some((r) => !!r.normalRange?.trim()));
  const referenceHeaderText = mode === "compact" && !hasAnyRealRange ? "Unit" : "Reference";
  const widths =
    mode === "detailed"
      ? DETAILED_COLUMN_WIDTHS
      : mode === "compact"
        ? COMPACT_COLUMN_WIDTHS
        : showSpecimen
          ? PLAIN_WITH_SPECIMEN_COLUMN_WIDTHS
          : PLAIN_COLUMN_WIDTHS;

  return (
    <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: widths.test }} />
        {showSpecimen ? <col style={{ width: widths.specimen }} /> : null}
        <col style={{ width: widths.result }} />
        {mode === "detailed" ? <col style={{ width: widths.unit }} /> : null}
        {mode !== "plain" ? <col style={{ width: widths.reference }} /> : null}
        {mode === "detailed" ? <col style={{ width: widths.flag }} /> : null}
      </colgroup>
      <thead>
        {/* `whitespace-normal break-words` on every header cell: without it,
            a single unbreakable word like "REFERENCE" simply overflows its
            `table-layout: fixed` column (browsers don't shrink the table to
            contain it, they let the text spill past the cell) - that
            overflow was the actual clipping bug, not the column width
            alone. Wrapping is the real fix. */}
        <tr className="report-table-head bg-slate-800 text-white">
          <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">{testHeader}</th>
          {showSpecimen ? (
            <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Specimen</th>
          ) : null}
          <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Result</th>
          {mode === "detailed" ? (
            <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Unit</th>
          ) : null}
          {mode !== "plain" ? (
            <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">
              {referenceHeaderText}
            </th>
          ) : null}
          {mode === "detailed" ? (
            // Medtech feedback (real A4 print review): this column's cell
            // content is an auto-computed Low/High/Abnormal indicator (see
            // `FlagText` below), never free-text remarks - "FLAG" is the
            // correct label for that, not "Remarks" (reverted from an
            // earlier terminology guess made against the manual-report
            // photo, since the medtech's own direct review of the actual
            // print output takes priority over that guess).
            <th className="whitespace-normal break-words py-1 pl-1 pr-2 text-center font-semibold uppercase tracking-wide">FLAG</th>
          ) : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) =>
          row.results.map((result, resultIndex) => (
            <tr key={`${row.parameterName}-${resultIndex}`} className="report-row border-b border-border/60 last:border-0">
              <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">
                {row.parameterName}
                {result.site ? <span className="text-muted-foreground"> ({result.site})</span> : null}
              </td>
              {showSpecimen ? (
                <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">{specimenType}</td>
              ) : null}
              <td className="whitespace-normal break-words px-1 py-1 text-center align-top font-medium">
                {(mode === "plain" ? plainResultValue(result) : reportResultValue(result)) ?? (
                  <span className="text-muted-foreground">-</span>
                )}
              </td>
              {mode === "detailed" ? (
                <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">{result.units ?? ""}</td>
              ) : null}
              {mode !== "plain" ? (
                <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">
                  {mode === "compact"
                    ? compactReferenceLines(result).map((line, lineIndex) => <div key={lineIndex}>{line}</div>)
                    : (result.normalRange ?? "")}
                </td>
              ) : null}
              {mode === "detailed" ? (
                <td className="whitespace-normal break-words py-1 pl-1 pr-2 text-center align-top">
                  <FlagText value={result.interpretation} resultType={result.resultType} />
                </td>
              ) : null}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

/** Medtech feedback (Blood Typing, real A4 print review): when every row in
 * a group is Categorical but the group isn't matrix-eligible (see
 * `isCombinedCategoricalGroup` above), the clinic wants ONE combined line -
 * the overall test name and every value joined together ("BLOOD TYPING" |
 * "O POSITIVE") - not one row per antigen/parameter. Values join in
 * `display_order` (the order `rows`/`row.results` already carry), so ABO
 * Group always prints before Rh Factor without a name-specific check. */
function CombinedCategoricalRow({ testLabel, rows }: { testLabel: string | null | undefined; rows: LaboratoryReportRow[] }) {
  const combinedValue = rows
    .flatMap((row) => row.results.map((result) => reportResultValue(result)))
    .filter((value): value is string => !!value)
    .join(" ");

  return (
    <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: "30%" }} />
        <col style={{ width: "70%" }} />
      </colgroup>
      <thead>
        <tr className="report-table-head bg-slate-800 text-white">
          <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">Test</th>
          <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Result</th>
        </tr>
      </thead>
      <tbody>
        <tr className="report-row border-b border-border/60 last:border-0">
          <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">{testLabel ?? "-"}</td>
          <td className="whitespace-normal break-words px-1 py-1 text-center align-top font-medium">
            {combinedValue || <span className="text-muted-foreground">-</span>}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

/** Qualitative Positive/Negative matrix - client reference format: the
 * parent test name as the first cell/row label ("DENGUE RAPID TEST"),
 * then one column per Categorical parameter, parameter names as the
 * column headings ("NS1 | IgM | IgG" for a 3-parameter test, just
 * "HBsAg" for a single-parameter one) with results directly beneath -
 * entirely dynamic on `rows.length`, never assuming 1/2/3 parameters.
 * The parent test name lives ONLY here (not repeated in the report
 * header's InfoRow block - see the `categoricalRows.length === 0` guard
 * around that "Test" row above) - the client's own serology reference
 * shows the parent test name inside the table itself, so this is the
 * one place it belongs for a qualitative report. Deliberately omits
 * Unit/Normal Values/Flag/Interpretation: none of those are meaningful
 * for a bare Positive/Negative result, matching the clinic's own
 * paper-report sample. The underlying `interpretation` value is
 * untouched in the data (still computed and stored exactly as before) -
 * this component simply never reads it.
 *
 * Fix (site-drop defect found by the Phase 10 visual audit): a
 * `requiresSite` parameter (e.g. KOH Mount) CAN carry multiple results
 * under one `parameterName`, one per collection site - the old
 * implementation silently kept only `row.results[0]`, so a second/third
 * site's result (and every site label) never printed at all, with no
 * visual indication a site was even collected. Each result now becomes
 * its own column, labeled with its site the same way the standard
 * five-column table already does (`parameterName` + a trailing
 * `(site)` span) - a single-site row (`results.length === 1`, the
 * overwhelming majority of real templates) renders byte-for-byte as
 * before, since its "site" span is simply absent when `site` is null. */
/** Per-clinic manual-report reference: a `requiresSite` test with more than
 * one collected site (KOH Mount is the only one seeded so far) is NOT
 * printed as one column per site on the clinic's own paper report - it's a
 * single TEST row with a numbered SITE list and a correspondingly numbered
 * RESULT list beneath it (see the clinic's own "KOH MOUNT / 1. ABDOMEN 2.
 * LEFT TRUNK / NEGATIVE NEGATIVE" sample). Detected purely from the data
 * (exactly one row, with more than one result, all carrying a site) so any
 * future multi-site test gets this layout automatically without a
 * test-name check; a single-site `requiresSite` test (`results.length ===
 * 1`) still goes through the ordinary matrix below unchanged. */
function isMultiSiteRow(rows: LaboratoryReportRow[]): boolean {
  return rows.length === 1 && rows[0].results.length > 1 && rows[0].results.every((r) => !!r.site);
}

function SiteListResultTable({ testLabel, row }: { testLabel: string | null | undefined; row: LaboratoryReportRow }) {
  return (
    <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: "30%" }} />
        <col style={{ width: "40%" }} />
        <col style={{ width: "30%" }} />
      </colgroup>
      <thead>
        <tr className="report-table-head bg-slate-800 text-white">
          <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">Test</th>
          <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Site</th>
          <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Result</th>
        </tr>
      </thead>
      <tbody>
        <tr className="report-row border-b border-border/60 last:border-0">
          <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">{testLabel ?? row.parameterName}</td>
          <td className="whitespace-normal break-words px-1 py-1 align-top">
            {row.results.map((result, index) => (
              <div key={`site-${index}`}>
                {index + 1}. {result.site}
              </div>
            ))}
          </td>
          <td className="whitespace-normal break-words px-1 py-1 align-top">
            {row.results.map((result, index) => (
              <div key={`result-${index}`}>{reportResultValue(result) ?? <span className="text-muted-foreground">-</span>}</div>
            ))}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

function QualitativeResultMatrix({
  testLabel,
  rows,
  specimenType,
  testCategory,
}: {
  testLabel: string | null | undefined;
  rows: LaboratoryReportRow[];
  specimenType?: string | null;
  testCategory?: string | null;
}) {
  if (isMultiSiteRow(rows)) {
    return <SiteListResultTable testLabel={testLabel} row={rows[0]} />;
  }

  const columns = rows.flatMap((row) =>
    row.results.map((result, resultIndex) => ({
      key: `${row.parameterName}-${resultIndex}`,
      parameterName: row.parameterName,
      site: result.site ?? null,
      result,
    }))
  );
  // Medtech feedback (Trichomonas Vaginalis Mount, real A4 print review):
  // a single-parameter matrix (Trichomonas, HBsAg, Fecal Occult Blood, ...)
  // in the "Clinical Microscopy" family needs a SPECIMEN column too - see
  // `isClinicalMicroscopyCategory`'s own doc comment for why this is the
  // right data-driven signal (matches this project's real category data,
  // never a test-name check). A genuinely multi-component matrix (Dengue's
  // NS1/IgM/IgG) never qualifies both because it's a different category
  // (SEROLOGY/IMMUNOLOGY) AND because `columns.length` is never 1 for it.
  const showSpecimen = columns.length === 1 && !!specimenType?.trim() && isClinicalMicroscopyCategory(testCategory);
  const testColumnWidth = showSpecimen ? 25 : 30;
  const specimenColumnWidth = showSpecimen ? 25 : 0;
  const resultColumnWidth = columns.length > 0 ? (100 - testColumnWidth - specimenColumnWidth) / columns.length : 0;

  return (
    <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: `${testColumnWidth}%` }} />
        {showSpecimen ? <col style={{ width: `${specimenColumnWidth}%` }} /> : null}
        {columns.map((column) => (
          <col key={column.key} style={{ width: `${resultColumnWidth}%` }} />
        ))}
      </colgroup>
      <thead>
        <tr className="report-table-head bg-slate-800 text-white">
          <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">Test</th>
          {showSpecimen ? (
            <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Specimen</th>
          ) : null}
          {columns.map((column) => (
            <th key={column.key} className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">
              {/* Medtech feedback (HBsAg, real A4 print review): a
                  single-component matrix must say "Result", not repeat the
                  parameter name (the TEST column/heading already identifies
                  the test) - a genuine multi-component matrix (Dengue's
                  NS1/IgM/IgG) still needs each column's own parameter name
                  to tell the components apart, so this only applies when
                  there's exactly one column. */}
              {columns.length === 1 ? "Result" : column.parameterName}
              {column.site ? <span> ({column.site})</span> : null}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        <tr className="report-row border-b border-border/60 last:border-0">
          <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">{testLabel ?? "-"}</td>
          {showSpecimen ? (
            <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">{specimenType}</td>
          ) : null}
          {columns.map((column) => (
            <td key={column.key} className="whitespace-normal break-words px-1 py-1 text-center align-top font-medium">
              {reportResultValue(column.result) ?? <span className="text-muted-foreground">-</span>}
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  );
}

/** Always renders label + value (falling back to "-" rather than hiding
 * the row) so the printed info block keeps its fixed, aligned shape even
 * when a field genuinely has nothing persisted for it (e.g. no requesting
 * doctor on a walk-in order) - matching the clinic-approved reference,
 * which shows "-" rather than a gap.
 *
 * Round 3 (clipping fix): the value `<span>` is a flex item, and flex
 * items default to `min-width: auto` - that floor means a long
 * unbreakable-looking string like "08/22/2026 10:19 AM" refuses to
 * shrink/wrap below its own natural width no matter how narrow the row
 * gets, so it silently overflows the row (and everything containing it)
 * instead of wrapping. `min-w-0` removes that floor so the value can wrap
 * onto a second line exactly like the spec allows, rather than overflow
 * and get visually cut off by the preview's scroll boundary. */
function InfoRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex gap-1 py-0.5">
      <span className="w-[88px] shrink-0 text-muted-foreground sm:w-28">{label}</span>
      <span className="shrink-0 text-muted-foreground">:</span>
      <span className="min-w-0 flex-1 whitespace-normal break-words font-medium text-foreground">{value ?? "-"}</span>
    </div>
  );
}
