import { Clock } from "lucide-react";
import { EmptyState } from "@/components/layout/EmptyState";
import { formatDateTime } from "@/lib/utils";
import { VISIT_TIMELINE_EVENT_LABELS, type VisitTimelineEntry } from "@/features/visits/types";

export function VisitTimeline({ events }: { events: VisitTimelineEntry[] }) {
  if (events.length === 0) {
    return <EmptyState title="No timeline events yet" description="Events appear here as the visit progresses." />;
  }

  const sorted = [...events].sort((a, b) => new Date(a.occurredAt).getTime() - new Date(b.occurredAt).getTime());

  return (
    <ol className="space-y-4">
      {sorted.map((event, index) => (
        <li key={event.id} className="relative flex gap-3 pl-1">
          <div className="flex flex-col items-center">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
            {index < sorted.length - 1 ? <span className="mt-1 w-px flex-1 bg-border" /> : null}
          </div>
          <div className="pb-4">
            <p className="text-sm font-medium text-foreground">
              {VISIT_TIMELINE_EVENT_LABELS[event.eventType] ?? event.eventType}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatDateTime(event.occurredAt)}
            </p>
            {event.note ? <p className="mt-1 text-sm text-muted-foreground">{event.note}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
