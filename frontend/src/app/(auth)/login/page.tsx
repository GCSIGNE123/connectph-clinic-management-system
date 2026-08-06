import type { Metadata } from "next";
import { LoginForm } from "@/features/auth/components/LoginForm";

export const metadata: Metadata = {
  title: "Sign in",
};

export default function LoginPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1 text-center">
        <h2 className="text-base font-semibold text-foreground">Sign in to your account</h2>
        <p className="text-sm text-muted-foreground">
          Enter your clinic credentials to continue.
        </p>
      </div>
      <LoginForm />
    </div>
  );
}
