import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DoctorQueueTable } from "./DoctorQueueTable";
import type { DoctorQueueItem } from "@/features/doctor-workspace/types";
import { ToastProvider } from "@/components/ui/toast";

function buildItem(overrides: Partial<DoctorQueueItem> = {}): DoctorQueueItem {
  return {
    visitId: "visit-1",
    visitNumber: "VIS-20260726-000001",
    queueId: "queue-1",
    queueNumber: "A001",
    patientId: "patient-1",
    patientName: "Juan Dela Cruz",
    patientNumber: "PAT-000001",
    age: 36,
    gender: "Male",
    priority: "Normal",
    status: "Waiting",
    visitType: "WalkIn",
    arrivalTime: new Date().toISOString(),
    calledTime: null,
    consultationStart: null,
    waitingSeconds: 125,
    isLocked: false,
    lockedByName: null,
    lockedBySelf: false,
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("DoctorQueueTable", () => {
  it("renders a row with waiting-time formatting", () => {
    renderWithClient(<DoctorQueueTable items={[buildItem()]} />);
    expect(screen.getByText("A001")).toBeInTheDocument();
    expect(screen.getByText("Juan Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("2 min")).toBeInTheDocument();
  });

  it("shows an empty state when there are no visits", () => {
    renderWithClient(<DoctorQueueTable items={[]} />);
    expect(screen.getByText(/no visits today/i)).toBeInTheDocument();
  });

  it("shows the Call action only for Waiting visits", () => {
    renderWithClient(<DoctorQueueTable items={[buildItem({ status: "Waiting" })]} />);
    expect(screen.getByRole("button", { name: /call/i })).toBeInTheDocument();
  });

  it("shows Start/Recall for Called visits and no Call button", () => {
    renderWithClient(<DoctorQueueTable items={[buildItem({ status: "Called" })]} />);
    expect(screen.getByRole("button", { name: /^start$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recall/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^call$/i })).not.toBeInTheDocument();
  });

  it("renders view-only actions cell when readOnly is set", () => {
    renderWithClient(<DoctorQueueTable items={[buildItem({ status: "Waiting" })]} readOnly />);
    expect(screen.getByText(/view only/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /call/i })).not.toBeInTheDocument();
  });
});
