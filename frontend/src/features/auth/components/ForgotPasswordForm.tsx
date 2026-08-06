"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/features/auth/api/auth-api";
import {
  forgotPasswordSchema,
  type ForgotPasswordInput,
} from "@/features/auth/schemas/auth-schemas";
import { ApiError } from "@/lib/api-client";

/**
 * TODO(backend): the /auth/forgot-password endpoint is not implemented yet.
 * This form is fully wired on the frontend so it can go live as soon as the
 * backend ships the route; today it will surface a clear error instead of
 * silently failing.
 */
export function ForgotPasswordForm() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  const mutation = useMutation({
    mutationFn: (input: ForgotPasswordInput) => authApi.forgotPassword(input),
    onSuccess: (_data, variables) => setSubmittedEmail(variables.email),
  });

  if (submittedEmail) {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-success/10 text-success">
          <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
        </span>
        <p className="text-sm text-muted-foreground">
          If an account exists for <strong>{submittedEmail}</strong>, a reset link has been sent.
        </p>
      </div>
    );
  }

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error
        ? "This feature isn't available yet. Please contact your clinic administrator."
        : null;

  return (
    <form
      onSubmit={handleSubmit((values) => mutation.mutate(values))}
      noValidate
      className="space-y-5"
    >
      <p className="text-sm text-muted-foreground">
        Enter the email associated with your account and we&apos;ll send you a link to reset
        your password.
      </p>

      {errorMessage ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage}
        </p>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@clinic.com"
          invalid={Boolean(errors.email)}
          {...register("email")}
        />
        {errors.email ? <p className="text-xs text-destructive">{errors.email.message}</p> : null}
      </div>

      <Button type="submit" className="w-full" isLoading={mutation.isPending}>
        Send reset link
      </Button>
    </form>
  );
}
