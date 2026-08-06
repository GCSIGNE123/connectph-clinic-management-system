"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  createUserSchema,
  editUserSchema,
  type CreateUserInput,
  type EditUserInput,
} from "@/features/users/schemas/users-schemas";
import { useCreateUser, useUpdateUser } from "@/features/users/hooks/use-user-mutations";
import type { ManagedUser } from "@/features/users/types";
import { Role, UserStatus } from "@/types";

export interface UserFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided, the dialog edits this user; otherwise it creates a new one. */
  user?: ManagedUser | null;
}

type FormValues = CreateUserInput & Partial<Pick<EditUserInput, "status">>;

/**
 * Add/Edit user dialog. Renders the create form (with password) when
 * `user` is not provided, or the edit form (with status, no password)
 * when it is.
 */
export function UserFormDialog({ open, onOpenChange, user }: UserFormDialogProps) {
  const isEdit = Boolean(user);
  const schema = isEdit ? editUserSchema : createUserSchema;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema as never),
    defaultValues: {
      firstName: "",
      middleName: "",
      lastName: "",
      email: "",
      mobileNumber: "",
      username: "",
      role: Role.Receptionist,
      branchId: "",
      password: "",
      status: UserStatus.Active,
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        firstName: user?.firstName ?? "",
        middleName: user?.middleName ?? "",
        lastName: user?.lastName ?? "",
        email: user?.email ?? "",
        mobileNumber: user?.mobileNumber ?? "",
        username: user?.username ?? "",
        role: user?.role ?? Role.Receptionist,
        branchId: user?.branchId ?? "",
        password: "",
        status: user?.status ?? UserStatus.Active,
      });
    }
  }, [open, user, reset]);

  const createUser = useCreateUser();
  const updateUser = useUpdateUser(user?.id ?? "");
  const mutation = isEdit ? updateUser : createUser;

  const onSubmit = handleSubmit((values) => {
    const onDone = () => onOpenChange(false);
    if (isEdit && user) {
      updateUser.mutate(values as EditUserInput, { onSuccess: onDone });
    } else {
      createUser.mutate(values as CreateUserInput, { onSuccess: onDone });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit user" : "Add user"}</DialogTitle>
        </DialogHeader>

        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="firstName">First name</Label>
              <Input id="firstName" invalid={Boolean(errors.firstName)} {...register("firstName")} />
              {errors.firstName ? (
                <p className="text-xs text-destructive">{errors.firstName.message}</p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="middleName">Middle name</Label>
              <Input id="middleName" {...register("middleName")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lastName">Last name</Label>
              <Input id="lastName" invalid={Boolean(errors.lastName)} {...register("lastName")} />
              {errors.lastName ? (
                <p className="text-xs text-destructive">{errors.lastName.message}</p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" invalid={Boolean(errors.email)} {...register("email")} />
              {errors.email ? <p className="text-xs text-destructive">{errors.email.message}</p> : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mobileNumber">Mobile number</Label>
              <Input
                id="mobileNumber"
                invalid={Boolean(errors.mobileNumber)}
                {...register("mobileNumber")}
              />
              {errors.mobileNumber ? (
                <p className="text-xs text-destructive">{errors.mobileNumber.message}</p>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="username">Username</Label>
              <Input id="username" invalid={Boolean(errors.username)} {...register("username")} />
              {errors.username ? (
                <p className="text-xs text-destructive">{errors.username.message}</p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role">Role</Label>
              <Select id="role" invalid={Boolean(errors.role)} {...register("role")}>
                {Object.values(Role).map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </Select>
              {errors.role ? <p className="text-xs text-destructive">{errors.role.message}</p> : null}
            </div>
          </div>

          {isEdit ? (
            <div className="space-y-1.5">
              <Label htmlFor="status">Status</Label>
              <Select id="status" {...register("status")}>
                {Object.values(UserStatus).map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </Select>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="password">Temporary password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                invalid={Boolean(errors.password)}
                {...register("password")}
              />
              {errors.password ? (
                <p className="text-xs text-destructive">{errors.password.message}</p>
              ) : null}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isSubmitting || mutation.isPending}>
              {isEdit ? "Save changes" : "Create user"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
