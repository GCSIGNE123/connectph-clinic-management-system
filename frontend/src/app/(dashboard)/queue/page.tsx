"use client";

import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { useQueues, useQueueRealtime } from "@/features/queue/hooks/use-queues";
import { useCancelQueue } from "@/features/queue/hooks/use-queue-mutations";
import { NewQueueDialog } from "@/features/queue/components/NewQueueDialog";
import { QueueTable } from "@/features/queue/components/QueueTable";
import { QueueDetailsDialog } from "@/features/queue/components/QueueDetailsDialog";
import { QueueSlipDialog } from "@/features/queue/components/QueueSlipDialog";
import { ReceptionVitalsDialog } from "@/features/consultation/components/ReceptionVitalsDialog";
import { QUEUE_PRIORITY_LABELS, QUEUE_STATUS_LABELS, QueuePriority, QueueStatus, type QueueListItem } from "@/features/queue/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);
const TRANSITION_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist, Role.Doctor, Role.Nurse]);
// Phase 20 (items 3-5): who may enter Subjective/Objective/vitals via the
// new "Enter Vitals" Queue action - Receptionist (performing Nurse-type
// duties) and Nurse itself, plus the usual Owner/Administrator override.
const VITALS_ENTRY_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist, Role.Nurse]);

/**
 * Reception Dashboard: today's live queue, search + filters, New Queue
 * ticket creation, view/cancel/reprint actions. Realtime updates arrive via
 * `useQueueRealtime` (WebSocket) with a 30s poll fallback in `useQueues`.
 */
export default function QueuePage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const canTransition = Boolean(currentUser && TRANSITION_ROLES.has(currentUser.role));
  const canEnterVitals = Boolean(currentUser && VITALS_ENTRY_ROLES.has(currentUser.role));

  useQueueRealtime();

  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [status, setStatus] = useState<QueueStatus | "">("");
  const [priority, setPriority] = useState<QueuePriority | "">("");

  const [newQueueOpen, setNewQueueOpen] = useState(false);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [slipId, setSlipId] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<QueueListItem | null>(null);
  const [vitalsTarget, setVitalsTarget] = useState<QueueListItem | null>(null);

  const cancelQueue = useCancelQueue();

  const params = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: status || undefined,
      priority: priority || undefined,
      pageSize: 100,
      page: 1,
    }),
    [debouncedSearch, status, priority]
  );

  const { data, isLoading } = useQueues(params);
  const items = data?.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Reception Queue</h1>
          <p className="text-sm text-muted-foreground">Today&apos;s walk-in and queue tickets.</p>
        </div>
        {canManage ? (
          <Button onClick={() => setNewQueueOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> New Queue
          </Button>
        ) : null}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search queue number, patient name, number, or mobile"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
        <Select value={status} onChange={(e) => setStatus(e.target.value as QueueStatus | "")} className="sm:w-48">
          <option value="">All statuses</option>
          {Object.values(QueueStatus).map((s) => (
            <option key={s} value={s}>
              {QUEUE_STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        <Select value={priority} onChange={(e) => setPriority(e.target.value as QueuePriority | "")} className="sm:w-48">
          <option value="">All priorities</option>
          {Object.values(QueuePriority).map((p) => (
            <option key={p} value={p}>
              {QUEUE_PRIORITY_LABELS[p]}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        <QueueTable
          items={items}
          isLoading={isLoading}
          canManage={canManage}
          onView={(item) => setDetailsId(item.id)}
          onReprint={(item) => setSlipId(item.id)}
          onCancel={(item) => setCancelTarget(item)}
          onEnterVitals={canEnterVitals ? (item) => setVitalsTarget(item) : undefined}
        />
      </Card>

      <NewQueueDialog
        open={newQueueOpen}
        onOpenChange={setNewQueueOpen}
        defaultBranchId={currentUser?.branchId ?? undefined}
        onCreated={(id) => setSlipId(id)}
      />

      <QueueDetailsDialog queueId={detailsId} onOpenChange={(open) => !open && setDetailsId(null)} canTransition={canTransition} />
      <QueueSlipDialog queueId={slipId} onOpenChange={(open) => !open && setSlipId(null)} />
      {vitalsTarget && vitalsTarget.visitId ? (
        <ReceptionVitalsDialog
          open={Boolean(vitalsTarget)}
          onOpenChange={(open) => !open && setVitalsTarget(null)}
          visitId={vitalsTarget.visitId}
          patientName={vitalsTarget.patientName}
        />
      ) : null}

      {cancelTarget ? (
        <ConfirmCancelDialog
          queue={cancelTarget}
          onClose={() => setCancelTarget(null)}
          onConfirm={() => {
            cancelQueue.mutate(cancelTarget.id);
            setCancelTarget(null);
          }}
        />
      ) : null}
    </div>
  );
}

function ConfirmCancelDialog({
  queue,
  onClose,
  onConfirm,
}: {
  queue: QueueListItem;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-foreground">Cancel queue ticket {queue.queueNumber}?</h2>
        <p className="mt-1 text-sm text-muted-foreground">This cannot be undone.</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Keep ticket
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            Cancel ticket
          </Button>
        </div>
      </div>
    </div>
  );
}
