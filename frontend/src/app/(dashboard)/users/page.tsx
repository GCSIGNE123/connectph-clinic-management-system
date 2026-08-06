"use client";

import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useUsers } from "@/features/users/hooks/use-users";
import { UsersTable } from "@/features/users/components/UsersTable";
import { UserFormDialog } from "@/features/users/components/UserFormDialog";
import { ResetPasswordDialog } from "@/features/users/components/ResetPasswordDialog";
import { ConfirmActionDialog } from "@/features/users/components/ConfirmActionDialog";
import type { ManagedUser } from "@/features/users/types";

const PAGE_SIZE = 10;

/**
 * User management page: search + pagination over `/api/v1/users`, with
 * create/edit, disable/enable and admin password reset actions.
 */
export default function UsersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const [formOpen, setFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);

  const [resetTarget, setResetTarget] = useState<ManagedUser | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{
    user: ManagedUser;
    action: "disable" | "enable";
  } | null>(null);

  const params = useMemo(
    () => ({ search: search || undefined, page, pageSize: PAGE_SIZE }),
    [search, page]
  );

  const { data, isLoading, isFetching } = useUsers(params);
  const users = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Users</h1>
          <p className="text-sm text-muted-foreground">
            Manage staff accounts, roles, and access for your clinic.
          </p>
        </div>
        <Button
          type="button"
          onClick={() => {
            setEditingUser(null);
            setFormOpen(true);
          }}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add user
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          type="search"
          placeholder="Search by name, email, or username"
          className="pl-8"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          aria-label="Search users"
        />
      </div>

      <UsersTable
        users={users}
        isLoading={isLoading}
        emptyMessage={
          search ? `No users match "${search}".` : "No users have been added to this clinic yet."
        }
        onEdit={(user) => {
          setEditingUser(user);
          setFormOpen(true);
        }}
        onDisable={(user) => setConfirmTarget({ user, action: "disable" })}
        onEnable={(user) => setConfirmTarget({ user, action: "enable" })}
        onResetPassword={(user) => setResetTarget(user)}
      />

      {meta && meta.totalPages > 1 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {meta.page} of {meta.totalPages} ({meta.total} total)
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page <= 1 || isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.totalPages || isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <UserFormDialog open={formOpen} onOpenChange={setFormOpen} user={editingUser} />

      <ResetPasswordDialog
        open={Boolean(resetTarget)}
        onOpenChange={(open) => {
          if (!open) setResetTarget(null);
        }}
        user={resetTarget}
      />

      <ConfirmActionDialog
        open={Boolean(confirmTarget)}
        onOpenChange={(open) => {
          if (!open) setConfirmTarget(null);
        }}
        user={confirmTarget?.user ?? null}
        action={confirmTarget?.action ?? null}
      />
    </div>
  );
}

