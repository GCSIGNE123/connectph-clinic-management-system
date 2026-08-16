import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PaymentDialog } from "./PaymentDialog";

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function renderWithClient(open: boolean) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PaymentDialog open={open} onOpenChange={vi.fn()} invoiceId="invoice-1" balanceDue={400} />
    </QueryClientProvider>
  );
}

describe("PaymentDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** Regression test for BUG-040: `InvoiceDetailPage` always mounts
   * `<PaymentDialog>` (only its own internal `<Dialog>` bails out when
   * `open` is false), so this dialog's `useState` initializer runs on
   * every single invoice-detail page load - previously it called
   * `crypto.randomUUID()` there unconditionally. `randomUUID()` is only
   * exposed by the Web Crypto API in a secure context (`https:` or
   * `http://localhost`); this app's production deployment
   * (`docker/docker-compose.prod.yml`'s default `NEXT_PUBLIC_API_URL`,
   * `http://<LAN IP>:8000`) serves the frontend over plain HTTP at a LAN
   * IP, which browsers do NOT treat as secure - `crypto.randomUUID` is
   * `undefined` there, so calling it threw a render-time `TypeError`
   * inside `<PaymentDialog>` on every invoice-detail page load, caught by
   * the root `app/error.tsx` boundary as "Something went wrong" - live
   * production impact confirmed via a real browser session with
   * `crypto.randomUUID` deleted (reproducing an insecure-context
   * `Crypto` instance) before this fix, and via the same simulation
   * after the fix. This test reproduces that exact condition directly:
   * deletes `crypto.randomUUID` before mounting, and asserts the dialog
   * renders successfully instead of throwing - whether `open` is true or
   * false, since the crash happened on mount regardless of visibility. */
  it("mounts without crypto.randomUUID (insecure-context / plain-HTTP LAN deployment) when closed", () => {
    const original = window.crypto.randomUUID;
    // @ts-expect-error - simulating an insecure context where the Web Crypto API doesn't expose randomUUID
    delete window.crypto.randomUUID;
    try {
      expect(() => renderWithClient(false)).not.toThrow();
    } finally {
      window.crypto.randomUUID = original;
    }
  });

  it("mounts without crypto.randomUUID (insecure-context / plain-HTTP LAN deployment) when open, and is fully usable", async () => {
    const original = window.crypto.randomUUID;
    // @ts-expect-error - simulating an insecure context where the Web Crypto API doesn't expose randomUUID
    delete window.crypto.randomUUID;
    try {
      renderWithClient(true);
      expect(await screen.findByRole("heading", { name: "Record payment" })).toBeInTheDocument();
      expect(screen.getByText(/Balance due:/)).toBeInTheDocument();
    } finally {
      window.crypto.randomUUID = original;
    }
  });
});
