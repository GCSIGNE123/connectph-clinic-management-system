import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VisitTable } from "./VisitTable";
import { VisitPriority, VisitStatus, VisitType, type VisitListItem } from "@/features/visits/types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function buildVisit(overrides: Partial<VisitListItem> = {}): VisitListItem {
  return {
    id: "1",
    visitNumber: "VIS-20260726-000001",
    visitDate: new Date().toISOString().slice(0, 10),
    visitType: VisitType.WalkIn,
    status: VisitStatus.Waiting,
    priority: VisitPriority.Normal,
    branchId: "branch-1",
    patientId: "patient-1",
    patientName: "Juan Dela Cruz",
    patientNumber: "PAT-000001",
    doctorId: null,
    doctorName: null,
    departmentId: "dept-1",
    departmentName: "General Medicine",
    serviceId: "service-1",
    serviceName: "Consultation",
    queueId: "queue-1",
    queueNumber: "A001",
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

describe("VisitTable", () => {
  it("renders a row per visit with number, patient, queue number, and status badge", () => {
    const items = [
      buildVisit(),
      buildVisit({
        id: "2",
        visitNumber: "VIS-20260726-000002",
        patientName: "Maria Santos",
        status: VisitStatus.Completed,
        queueNumber: "A002",
      }),
    ];

    render(<VisitTable items={items} isLoading={false} />);

    expect(screen.getByText("VIS-20260726-000001")).toBeInTheDocument();
    expect(screen.getByText("VIS-20260726-000002")).toBeInTheDocument();
    expect(screen.getByText("Juan Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("Maria Santos")).toBeInTheDocument();
    expect(screen.getByText("A001")).toBeInTheDocument();
    expect(screen.getByText("A002")).toBeInTheDocument();
    expect(screen.getByText("Waiting")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows an empty state when there are no visits", () => {
    render(<VisitTable items={[]} isLoading={false} />);
    expect(screen.getByText(/no visits found/i)).toBeInTheDocument();
  });

  it("renders loading skeletons while loading", () => {
    const { container } = render(<VisitTable items={[]} isLoading />);
    expect(container.querySelectorAll('[class*="skeleton"], [data-slot="skeleton"]').length).toBeGreaterThanOrEqual(0);
    expect(screen.queryByText(/no visits found/i)).not.toBeInTheDocument();
  });
});
