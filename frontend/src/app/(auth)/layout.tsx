import type { ReactNode } from "react";
import { Stethoscope } from "lucide-react";

/**
 * Centered layout shared by /login, /forgot-password and /reset-password.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Stethoscope className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              {process.env.NEXT_PUBLIC_APP_NAME ?? "CONNECT.PH Clinic Platform"}
            </h1>
            <p className="text-sm text-muted-foreground">Clinic management, simplified.</p>
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">{children}</div>
      </div>
    </div>
  );
}
