import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueueSlipDialog } from "./QueueSlipDialog";
import type { QueueSlip } from "@/features/queue/types";
import { QueuePriority } from "@/features/queue/types";

const mockGetSlip = vi.fn();
vi.mock("@/features/queue/api/queue-api", () => ({
  queueApi: {
    getSlip: (...args: unknown[]) => mockGetSlip(...args),
  },
}));

function buildSlip(overrides: Partial<QueueSlip> = {}): QueueSlip {
  return {
    queueId: "queue-1",
    queueNumber: "L001",
    clinicName: "Canora Medical Clinic",
    branchName: "Main Branch",
    patientName: "Maria Santos",
    departmentName: "Laboratory",
    doctorName: null,
    serviceName: "BLOOD CHEMISTRY",
    priority: QueuePriority.Normal,
    queueDate: "2026-08-18",
    createdAt: "2026-08-18T08:00:00Z",
    qrToken: "token",
    vitalsTaken: false,
    isPaid: false,
    ...overrides,
  };
}

function renderDialog(queueId: string | null = "queue-1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <QueueSlipDialog queueId={queueId} onOpenChange={vi.fn()} />
    </QueryClientProvider>
  );
}

// `SlipContent` intentionally renders twice - once for the on-screen dialog
// preview, once portaled to `document.body` for @media print (see
// `QueueSlipPrintPortal`'s doc comment) - so every assertion here uses
// `findAllByText`/`queryAllByText` rather than the singular `getByText`,
// which would throw on the expected duplicate.
describe("QueueSlipDialog", () => {
  it("G: renders PAID when the backend reports isPaid === true", async () => {
    mockGetSlip.mockReset().mockResolvedValue(buildSlip({ isPaid: true }));
    renderDialog();

    const paidNodes = await screen.findAllByText("PAID");
    expect(paidNodes.length).toBeGreaterThan(0);
  });

  it("H: does not render PAID when isPaid === false, even for a Laboratory ticket", async () => {
    mockGetSlip.mockReset().mockResolvedValue(buildSlip({ departmentName: "Laboratory", isPaid: false }));
    renderDialog();

    await screen.findAllByText("L001");
    expect(screen.queryAllByText("PAID")).toHaveLength(0);
  });

  it("does not render PAID for a non-Laboratory, unpaid ticket (regression: existing slip behavior unchanged)", async () => {
    mockGetSlip.mockReset().mockResolvedValue(
      buildSlip({ departmentName: "Internal Medicine", vitalsTaken: true, isPaid: false, doctorName: "Ana Reyes" })
    );
    renderDialog();

    await screen.findAllByText("L001");
    expect(screen.queryAllByText("VITALS TAKEN").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("PAID")).toHaveLength(0);
  });
});
