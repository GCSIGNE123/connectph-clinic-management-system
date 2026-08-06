"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rolesApi, usersApi } from "@/features/users/api/users-api";
import { usersKeys } from "@/features/users/hooks/use-users";
import type { AdminResetPasswordInput, CreateUserInput, EditUserInput } from "@/features/users/schemas/users-schemas";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Resolves the role name chosen in the form (e.g. "Owner") to the backend's
 * `role_id`, since `POST/PATCH /users` require the id, not the name. */
async function resolveRoleId(roleName: string): Promise<string> {
  const roles = await rolesApi.list();
  const match = roles.find((r) => r.name === roleName);
  if (!match) {
    throw new Error(`Unknown role "${roleName}"`);
  }
  return match.id;
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: async (input: CreateUserInput) => {
      const roleId = await resolveRoleId(input.role);
      return usersApi.create({ ...input, roleId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast({ title: "User created", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not create user",
        description: errorMessage(error, "Please check the form and try again."),
        variant: "error",
      });
    },
  });
}

export function useUpdateUser(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: async (input: EditUserInput) => {
      const roleId = await resolveRoleId(input.role);
      return usersApi.update(id, { ...input, roleId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast({ title: "User updated", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not update user",
        description: errorMessage(error, "Please check the form and try again."),
        variant: "error",
      });
    },
  });
}

export function useDisableUser() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (id: string) => usersApi.disable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast({ title: "User disabled", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not disable user",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useEnableUser() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (id: string) => usersApi.enable(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      toast({ title: "User enabled", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not enable user",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useAdminResetPassword(id: string) {
  const { toast } = useToast();

  return useMutation({
    mutationFn: (input: AdminResetPasswordInput) => usersApi.adminResetPassword(id, input),
    onSuccess: () => {
      toast({ title: "Password reset", description: "The user's password has been changed.", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not reset password",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}
