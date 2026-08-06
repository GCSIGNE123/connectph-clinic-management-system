import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueueTable } from "./QueueTable";
import { QueuePriority, QueueStatus, type QueueListItem } from "@/features/queue/types";

function buildQueue(overrides: Partial<QueueListItem> = {}): QueueListItem {
  return {
    id: "1",
    queueNumber: "A001",
    queueDate: new Date().toISOString().slice(0, 10),
    priority: QueuePriority.Normal,
    status: QueueStatus.Waiting,
    branchId: "branch-1",
    departmentId: "dept-1",
    departmentName: "General Medicine",
    doctorId: null,
    doctorName: null,
    serviceId: "service-1",
    serviceName: "Consultation",
    patientId: "patient-1",
    patientName: "Juan Dela Cruz",
    patientNumber: "PAT-000001",
    createdAt: new Date().toISOString(),
    calledAt: null,
    visitId: null,
    ...overrides,
  };
}

const noop = () => undefined;

describe("QueueTable", () => {
  it("renders a row per queue ticket with number, patient, and status badge", () => {
    const items = [
      buildQueue(),
      buildQueue({ id: "2", queueNumber: "A002", patientName: "Maria Santos", status: QueueStatus.Serving }),
    ];

    render(<QueueTable items={items} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);

    expect(screen.getByText("A001")).toBeInTheDocument();
    expect(screen.getByText("A002")).toBeInTheDocument();
    expect(screen.getByText("Juan Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("Maria Santos")).toBeInTheDocument();
    expect(screen.getByText("Waiting")).toBeInTheDocument();
    expect(screen.getByText("Serving")).toBeInTheDocument();
  });

  it("shows an empty state when there are no queue tickets", () => {
    render(<QueueTable items={[]} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);
    expect(screen.getByText(/no queue tickets/i)).toBeInTheDocument();
  });

  it("hides the Cancel action for completed/cancelled tickets", () => {
    const items = [buildQueue({ status: QueueStatus.Completed })];
    render(<QueueTable items={items} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });
});
