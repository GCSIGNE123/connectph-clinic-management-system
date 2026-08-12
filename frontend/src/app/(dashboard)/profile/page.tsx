"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser, authKeys } from "@/features/auth/hooks/use-current-user";
import { authApi } from "@/features/auth/api/auth-api";
import { ApiError } from "@/lib/api-client";

const MOBILE_NUMBER_PATTERN = /^\+?[0-9]{7,15}$/;

/**
 * Self-service account page for the logged-in user (any role, not just
 * Owner/Administrator) - wired up from the account dropdown's previously
 * dead "Profile"/"Settings" stubs (`UserMenu.tsx`). Two independent forms:
 * name/mobile number (via `PATCH /auth/me`) and password change (via
 * `POST /auth/me/change-password`, which requires the current password and
 * revokes every other session on success - deliberately not this page's own
 * session, which stays logged in). Deliberately does not expose role,
 * branch, email, or username - those are Owner/Administrator-only fields
 * managed via the separate `/users` admin page (`UserUpdate`, a different,
 * privilege-gated schema from this page's `UpdateOwnProfileRequest`).
 */
export default function ProfilePage() {
  const { data: user } = useCurrentUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [profileForm, setProfileForm] = useState({
    firstName: "",
    middleName: "",
    lastName: "",
    mobileNumber: "",
  });

  useEffect(() => {
    if (!user) return;
    setProfileForm({
      firstName: user.firstName,
      middleName: user.middleName ?? "",
      lastName: user.lastName,
      mobileNumber: user.mobileNumber ?? "",
    });
  }, [user]);

  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });

  const displayName = user ? `${user.firstName} ${user.lastName}` : "Signed in user";

  const saveProfile = useMutation({
    mutationFn: () => {
      if (!profileForm.firstName.trim() || !profileForm.lastName.trim()) {
        throw new Error("First and last name are required.");
      }
      if (profileForm.mobileNumber && !MOBILE_NUMBER_PATTERN.test(profileForm.mobileNumber)) {
        throw new Error("Mobile number must be 7-15 digits, optionally prefixed with '+'.");
      }
      return authApi.updateProfile({
        firstName: profileForm.firstName.trim(),
        middleName: profileForm.middleName.trim() || null,
        lastName: profileForm.lastName.trim(),
        mobileNumber: profileForm.mobileNumber.trim() || null,
      });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(authKeys.currentUser, updated);
      toast({ title: "Profile updated", variant: "success" });
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      toast({ title: "Update failed", description: message, variant: "error" });
    },
  });

  const changePassword = useMutation({
    mutationFn: () => {
      if (!passwordForm.currentPassword) {
        throw new Error("Current password is required.");
      }
      if (passwordForm.newPassword.length < 8) {
        throw new Error("New password must be at least 8 characters.");
      }
      if (passwordForm.newPassword !== passwordForm.confirmPassword) {
        throw new Error("New password and confirmation do not match.");
      }
      return authApi.changePassword({
        currentPassword: passwordForm.currentPassword,
        newPassword: passwordForm.newPassword,
      });
    },
    onSuccess: () => {
      setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
      toast({
        title: "Password changed",
        description: "You've been signed out of every other device/browser.",
        variant: "success",
      });
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      toast({ title: "Password change failed", description: message, variant: "error" });
    },
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="text-sm text-muted-foreground">
          Your own account details. Role, branch, and login email/username are managed by an
          Owner/Administrator via the Users page.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Avatar name={displayName} src={user?.avatarUrl} size="lg" />
            <div>
              <p className="font-medium">{displayName}</p>
              <p className="text-sm text-muted-foreground">{user?.email}</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="first-name">First name</Label>
              <Input
                id="first-name"
                value={profileForm.firstName}
                onChange={(e) => setProfileForm((f) => ({ ...f, firstName: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last-name">Last name</Label>
              <Input
                id="last-name"
                value={profileForm.lastName}
                onChange={(e) => setProfileForm((f) => ({ ...f, lastName: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="middle-name">Middle name</Label>
              <Input
                id="middle-name"
                value={profileForm.middleName}
                onChange={(e) => setProfileForm((f) => ({ ...f, middleName: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mobile-number">Mobile number</Label>
              <Input
                id="mobile-number"
                value={profileForm.mobileNumber}
                onChange={(e) => setProfileForm((f) => ({ ...f, mobileNumber: e.target.value }))}
                placeholder="e.g. +639171234567"
              />
            </div>
          </div>

          <Button
            type="button"
            isLoading={saveProfile.isPending}
            onClick={() => saveProfile.mutate()}
          >
            Save changes
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="current-password">Current password</Label>
            <Input
              id="current-password"
              type="password"
              value={passwordForm.currentPassword}
              onChange={(e) => setPasswordForm((f) => ({ ...f, currentPassword: e.target.value }))}
              className="max-w-sm"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              value={passwordForm.newPassword}
              onChange={(e) => setPasswordForm((f) => ({ ...f, newPassword: e.target.value }))}
              className="max-w-sm"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">Confirm new password</Label>
            <Input
              id="confirm-password"
              type="password"
              value={passwordForm.confirmPassword}
              onChange={(e) => setPasswordForm((f) => ({ ...f, confirmPassword: e.target.value }))}
              className="max-w-sm"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            isLoading={changePassword.isPending}
            onClick={() => changePassword.mutate()}
          >
            Change password
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
