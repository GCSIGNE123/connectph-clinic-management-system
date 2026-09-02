import { FlaskConical } from "lucide-react";
import { FlagText } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratorySignatoryFooter } from "@/features/laboratory/components/LaboratorySignatoryFooter";
import {
  buildAgeSexLine,
  buildCategoryHeading,
  buildReportRows,
  groupReportRowsBySection,
  isQualitativeCategoricalRow,
  reportResultValue,
  type LaboratoryReportRow,
} from "@/features/laboratory/lib/report";
import { formatDateTime } from "@/lib/utils";
import { resolveMediaUrl } from "@/lib/api-url";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Med-tech-requested print redesign: five columns (TEST / RESULT / UNIT /
 * NORMAL VALUES / FLAG), Result and Unit split into separate cells
 * (previously one combined "14 g/dL" string), sized for the full width of
 * a Letter/Short-Bond page via `table-layout: fixed` + explicit column
 * percentages (`COLUMN_WIDTHS` below) rather than the narrow auto-sized
 * table this replaces. Every cell still reads directly off the persisted
 * `LaboratoryResult` (`units`/`normalRange`/`interpretation`) - never
 * recalculated from the current template, so historical results keep
 * printing exactly what was true when they were released, even if the
 * template's reference ranges change later.
 *
 * Round 4 (Assessment -> Flag, matching the clinic's existing paper
 * report convention): the last column now prints a bare "L"/"H"/"A" (or
 * blank) instead of the full word/icon - see `FlagText`. FLAG only ever
 * holds a single character, so its column shrank from 19% to 8%; that
 * freed width went mostly to NORMAL VALUES (27% -> 35%), which is the
 * column most likely to hold a long persisted range string. */
const COLUMN_WIDTHS = { test: "30%", result: "14%", unit: "13%", normalValues: "35%", flag: "8%" };

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
  const allRows = buildReportRows(order);
  const categoricalRows = allRows.filter(isQualitativeCategoricalRow);
  const standardRows = allRows.filter((row) => !isQualitativeCategoricalRow(row));
  const groups = groupReportRowsBySection(standardRows);
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
  const categoryHeading = buildCategoryHeading(order.template?.testCategory, categoricalRows.length > 0 ? order.testType : null);
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
        {groups.map((group, groupIndex) => (
          <div key={groupIndex}>
            {group.section ? (
              <h3 className="section-heading mb-0.5 mt-1.5 border-b border-slate-400 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-800 first:mt-0 sm:text-[11px]">
                {group.section}
              </h3>
            ) : null}
            <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
              <colgroup>
                <col style={{ width: COLUMN_WIDTHS.test }} />
                <col style={{ width: COLUMN_WIDTHS.result }} />
                <col style={{ width: COLUMN_WIDTHS.unit }} />
                <col style={{ width: COLUMN_WIDTHS.normalValues }} />
                <col style={{ width: COLUMN_WIDTHS.flag }} />
              </colgroup>
              <thead>
                {/* `whitespace-normal break-words` on every header cell:
                    without it, a single unbreakable word like "NORMAL
                    VALUES" simply overflows its `table-layout: fixed`
                    column (browsers don't shrink the table to contain it,
                    they let the text spill past the cell) - that overflow
                    was the actual clipping bug, not the column width
                    alone. Wrapping is the real fix. */}
                <tr className="report-table-head bg-slate-800 text-white">
                  <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">Test</th>
                  <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Result</th>
                  <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Unit</th>
                  <th className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">Normal Values</th>
                  <th className="whitespace-normal break-words py-1 pl-1 pr-2 text-center font-semibold uppercase tracking-wide">Flag</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((row) =>
                  row.results.map((result, resultIndex) => (
                    <tr key={`${row.parameterName}-${resultIndex}`} className="report-row border-b border-border/60 last:border-0">
                      <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">
                        {row.parameterName}
                        {result.site ? <span className="text-muted-foreground"> ({result.site})</span> : null}
                      </td>
                      <td className="whitespace-normal break-words px-1 py-1 text-center align-top font-medium">
                        {reportResultValue(result) ?? <span className="text-muted-foreground">-</span>}
                      </td>
                      <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">
                        {result.units ?? ""}
                      </td>
                      <td className="whitespace-normal break-words px-1 py-1 text-center align-top text-muted-foreground">
                        {result.normalRange ?? ""}
                      </td>
                      <td className="whitespace-normal break-words py-1 pl-1 pr-2 text-center align-top">
                        <FlagText value={result.interpretation} resultType={result.resultType} />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ))}
        {categoricalRows.length > 0 ? (
          <QualitativeResultMatrix testLabel={order.testType} rows={categoricalRows} />
        ) : null}
        {groups.length === 0 && categoricalRows.length === 0 ? (
          <p className="py-2 text-muted-foreground">No results entered yet.</p>
        ) : null}
      </div>

      <div className="report-notes mt-3 rounded-sm border border-border px-2 py-1.5 text-[9px] text-muted-foreground sm:text-[10px]">
        <p className="mb-0.5 font-semibold uppercase tracking-wide text-slate-700">Note:</p>
        <ul className="list-disc space-y-0.5 pl-4">
          <li>This report is system-generated.</li>
          <li>Reference ranges may vary based on age, sex, and clinical condition.</li>
          {/* Client sample's "OTHERS: Please refer to your doctor for
              interpretation of the results." - added as one more bullet in
              this ALREADY-EXISTING note box (reused, not duplicated as a
              separate "OTHERS" block) and only for a report that actually
              contains a qualitative Positive/Negative matrix - a purely
              quantitative report keeps exactly its prior two bullets. */}
          {categoricalRows.length > 0 ? <li>Please refer to your doctor for interpretation of the results.</li> : null}
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
 * this component simply never reads it. A `requiresSite` parameter
 * (multiple results sharing one parameter name) is not a real-world
 * Positive/Negative case in this codebase's own templates, so only the
 * first result is shown per column; documented here rather than silently
 * dropped. */
function QualitativeResultMatrix({ testLabel, rows }: { testLabel: string | null | undefined; rows: LaboratoryReportRow[] }) {
  const testColumnWidth = 30;
  const resultColumnWidth = rows.length > 0 ? (100 - testColumnWidth) / rows.length : 0;

  return (
    <table className="w-full max-w-full border-collapse" style={{ tableLayout: "fixed" }}>
      <colgroup>
        <col style={{ width: `${testColumnWidth}%` }} />
        {rows.map((row) => (
          <col key={row.parameterName} style={{ width: `${resultColumnWidth}%` }} />
        ))}
      </colgroup>
      <thead>
        <tr className="report-table-head bg-slate-800 text-white">
          <th className="whitespace-normal break-words py-1 pl-2 pr-1 text-left font-semibold uppercase tracking-wide">Test</th>
          {rows.map((row) => (
            <th key={row.parameterName} className="whitespace-normal break-words px-1 py-1 text-center font-semibold uppercase tracking-wide">
              {row.parameterName}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        <tr className="report-row border-b border-border/60 last:border-0">
          <td className="whitespace-normal break-words py-1 pl-2 pr-1 align-top">{testLabel ?? "-"}</td>
          {rows.map((row) => (
            <td key={row.parameterName} className="whitespace-normal break-words px-1 py-1 text-center align-top font-medium">
              {reportResultValue(row.results[0]) ?? <span className="text-muted-foreground">-</span>}
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
