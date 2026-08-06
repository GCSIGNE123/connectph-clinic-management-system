"use client";

import { MoreHorizontal } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { UserStatus } from "@/types";
import type { ManagedUser } from "@/features/users/types";

export interface UsersTableProps {
  users: ManagedUser[];
  isLoading?: boolean;
  onEdit: (user: ManagedUser) => void;
  onDisable: (user: ManagedUser) => void;
  onEnable: (user: ManagedUser) => void;
  onResetPassword: (user: ManagedUser) => void;
  emptyMessage?: string;
}

const STATUS_BADGE: Record<UserStatus, { label: string; variant: "success" | "secondary" | "destructive" }> = {
  [UserStatus.Active]: { label: "Active", variant: "success" },
  [UserStatus.Disabled]: { label: "Disabled", variant: "secondary" },
  [UserStatus.Locked]: { label: "Locked", variant: "destructive" },
};

/**
 * Paginated user management table with row actions (edit / disable /
 * enable / reset password). Pagination controls live in the parent page
 * since they're shared with the search bar.
 */
export function UsersTable({
  users,
  isLoading,
  onEdit,
  onDisable,
  onEnable,
  onResetPassword,
  emptyMessage,
}: UsersTableProps) {
  if (isLoading) {
    return <SkeletonList rows={6} />;
  }

  if (users.length === 0) {
    return (
      <EmptyState
        title="No users found"
        description={emptyMessage ?? "Try adjusting your search or add a new user."}
      />
    );
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Username</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Mobile</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Branch</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => {
            const status = STATUS_BADGE[user.status];
            const fullName = [user.firstName, user.middleName, user.lastName]
              .filter(Boolean)
              .join(" ");

            return (
              <TableRow key={user.id}>
                <TableCell className="font-medium text-foreground">{fullName}</TableCell>
                <TableCell className="text-muted-foreground">{user.username}</TableCell>
                <TableCell className="text-muted-foreground">{user.email}</TableCell>
                <TableCell className="text-muted-foreground">{user.mobileNumber}</TableCell>
                <TableCell>{user.role}</TableCell>
                <TableCell className="text-muted-foreground">{user.branchName ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={status.variant}>{status.label}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger>
                      <Button type="button" variant="ghost" size="icon" aria-label="Row actions">
                        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem onClick={() => onEdit(user)}>Edit</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onResetPassword(user)}>
                        Reset password
                      </DropdownMenuItem>
                      {user.status === UserStatus.Active ? (
                        <DropdownMenuItem destructive onClick={() => onDisable(user)}>
                          Disable
                        </DropdownMenuItem>
                      ) : (
                        <DropdownMenuItem onClick={() => onEnable(user)}>Enable</DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
