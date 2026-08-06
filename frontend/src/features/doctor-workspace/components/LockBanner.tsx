import { Lock, LockOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LockInfo } from "@/features/doctor-workspace/types";

/**
 * Visit-locking UI: when another user holds the lock, shows "Currently
 * being edited by Dr. ___" and callers are expected to disable action
 * buttons (view-only). When the current user holds it, shows normal
 * edit-access confirmation.
 */
export function LockBanner({ lock }: { lock: LockInfo | null | undefined }) {
  if (!lock || !lock.locked) return null;

  if (lock.isSelf) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
        <LockOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>You have this visit open for editing.</span>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      )}
      role="status"
    >
      <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        Currently being edited by {lock.lockedByName ? <strong>{lock.lockedByName}</strong> : "another user"}. You
        can view this visit but cannot perform doctor actions on it.
      </span>
    </div>
  );
}
