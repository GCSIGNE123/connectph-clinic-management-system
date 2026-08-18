import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { buildReportRows, groupReportRowsBySection, reportResultValue } from "@/features/laboratory/lib/report";
import { formatDateTime } from "@/lib/utils";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Phase 4G: generic, template-driven read-only laboratory report body -
 * every field comes from the already-fetched `LaboratoryOrder` (via
 * `getOrder`, the only call site that populates `clinicName`), grouped and
 * type-rendered purely from `order.template`/`order.results` metadata. No
 * `if testType === "..."` branch anywhere - a future 7th/8th laboratory
 * test renders through this exact same component with zero changes. */
export function LaboratoryReportView({ order }: { order: LaboratoryOrder }) {
  const groups = groupReportRowsBySection(buildReportRows(order));

  return (
    <div className="space-y-4">
      <div className="text-center">
        {order.clinicName ? <p className="text-base font-semibold">{order.clinicName}</p> : null}
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">Laboratory Report</p>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-y border-border py-2 text-xs">
        <Field label="Patient" value={order.patientName} />
        <Field label="Test" value={order.testType} />
        <Field label="Visit #" value={order.visitNumber} />
        <Field label="Order #" value={order.orderNumber} />
        <Field label="Doctor" value={order.doctorName} />
        <Field label="Status" value={order.status} />
        <Field label="Collected" value={order.collectedAt ? formatDateTime(order.collectedAt) : null} />
        <Field label="Completed" value={order.completedAt ? formatDateTime(order.completedAt) : null} />
        <Field label="Released" value={order.releasedAt ? formatDateTime(order.releasedAt) : null} />
      </div>

      <div className="space-y-3">
        {groups.map((group, groupIndex) => (
          <div key={groupIndex} className="space-y-1">
            {group.section ? (
              <h3 className="border-b border-border pb-0.5 text-xs font-semibold uppercase tracking-wide">{group.section}</h3>
            ) : null}
            <table className="w-full text-sm">
              <tbody>
                {group.rows.map((row) =>
                  row.results.map((result, resultIndex) => (
                    <tr key={`${row.parameterName}-${resultIndex}`} className="border-b border-border/50 last:border-0">
                      <td className="py-1 pr-2 align-top">
                        {row.parameterName}
                        {result.site ? <span className="text-muted-foreground"> ({result.site})</span> : null}
                      </td>
                      <td className="py-1 pr-2 align-top">
                        {reportResultValue(result) ?? <span className="text-muted-foreground">-</span>}
                        {result.units ? ` ${result.units}` : ""}
                      </td>
                      <td className="py-1 pr-2 align-top text-muted-foreground">{result.normalRange ?? ""}</td>
                      <td className="py-1 align-top">{result.interpretation ? <InterpretationBadge value={result.interpretation} /> : null}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ))}
        {groups.length === 0 ? <p className="text-sm text-muted-foreground">No results entered yet.</p> : null}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <p>
      <span className="text-muted-foreground">{label}: </span>
      <span className="font-medium">{value}</span>
    </p>
  );
}
