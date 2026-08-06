"use client";

import { AlertDialog } from "@/components/ui/alert-dialog";
import { useDisableUser, useEnableUser } from "@/features/users/hooks/use-user-mutations";
import type { ManagedUser } from "@/features/users/types";

export interface ConfirmActionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: ManagedUser | null;
  action: "disable" | "enable" | null;
}

/** Confirms the disable/enable actions before they're sent to the API. */
export function ConfirmActionDialog({ open, onOpenChange, user, action }: ConfirmActionDialogProps) {
  const disableUser = useDisableUser();
  const enableUser = useEnableUser();

  if (!user || !action) return null;

  const isDisable = action === "disable";
  const mutation = isDisable ? disableUser : enableUser;
  const fullName = `${user.firstName} ${user.lastName}`;

  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
      title={isDisable ? "Disable this user?" : "Enable this user?"}
      description={
        isDisable
          ? `${fullName} will no longer be able to sign in until re-enabled.`
          : `${fullName} will regain access to sign in.`
      }
      confirmLabel={isDisable ? "Disable" : "Enable"}
      confirmVariant={isDisable ? "destructive" : "default"}
      isConfirming={mutation.isPending}
      onConfirm={() => {
        mutation.mutate(user.id, { onSuccess: () => onOpenChange(false) });
      }}
    />
  );
}
