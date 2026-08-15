import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueueTable } from "./QueueTable";
import { QueuePriority, QueueStatus, VisitClassification, type QueueListItem } from "@/features/queue/types";

function buildQueue(overrides: Partial<QueueListItem> = {}): QueueListItem {
  return {
    id: "1",
    queueNumber: "A001",
    queueDate: new Date().toISOString().slice(0, 10),
    priority: QueuePriority.Normal,
    status: QueueStatus.Waiting,
    visitClassification: VisitClassification.Regular,
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
    vitalsTaken: false,
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

  it("shows the YAKAP/Regular classification for each ticket", () => {
    const items = [
      buildQueue({ visitClassification: VisitClassification.Yakap }),
      buildQueue({ id: "2", queueNumber: "A002", visitClassification: VisitClassification.Regular }),
    ];
    render(<QueueTable items={items} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);
    expect(screen.getByText("YAKAP")).toBeInTheDocument();
    expect(screen.getByText("Regular")).toBeInTheDocument();
  });

  it("shows a Call button only for Waiting tickets when the user can transition, and calls onCall", () => {
    const items = [buildQueue({ status: QueueStatus.Waiting })];
    let called: QueueListItem | null = null;
    render(
      <QueueTable
        items={items}
        isLoading={false}
        canManage
        onView={noop}
        onCancel={noop}
        onReprint={noop}
        canTransition
        onCall={(item) => {
          called = item;
        }}
        onReannounce={noop}
      />
    );
    const callButton = screen.getByRole("button", { name: "Call" });
    callButton.click();
    expect(called).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Re-announce" })).not.toBeInTheDocument();
  });

  it("shows a Re-announce button only for Called tickets when the user can transition", () => {
    const items = [buildQueue({ status: QueueStatus.Called })];
    render(
      <QueueTable
        items={items}
        isLoading={false}
        canManage
        onView={noop}
        onCancel={noop}
        onReprint={noop}
        canTransition
        onCall={noop}
        onReannounce={noop}
      />
    );
    expect(screen.getByRole("button", { name: "Re-announce" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Call" })).not.toBeInTheDocument();
  });

  it("hides Call/Re-announce entirely when the user cannot transition (e.g. Cashier)", () => {
    const items = [buildQueue({ status: QueueStatus.Waiting })];
    render(
      <QueueTable
        items={items}
        isLoading={false}
        canManage={false}
        onView={noop}
        onCancel={noop}
        onReprint={noop}
        canTransition={false}
        onCall={noop}
        onReannounce={noop}
      />
    );
    expect(screen.queryByRole("button", { name: "Call" })).not.toBeInTheDocument();
  });

  it("colors the Enter Vitals button green when vitals are taken and red when they are not", () => {
    const items = [
      buildQueue({ id: "1", visitId: "visit-1", vitalsTaken: true }),
      buildQueue({ id: "2", queueNumber: "A002", visitId: "visit-2", vitalsTaken: false }),
    ];
    render(
      <QueueTable
        items={items}
        isLoading={false}
        canManage
        onView={noop}
        onCancel={noop}
        onReprint={noop}
        onEnterVitals={noop}
      />
    );
    const buttons = screen.getAllByRole("button", { name: "Enter Vitals" });
    expect(buttons).toHaveLength(2);
    expect(buttons[0].className).toMatch(/bg-green-100/);
    expect(buttons[1].className).toMatch(/bg-red-100/);
  });

  // Reception Queue - Show Latest Queue at the Top: the actual newest-first
  // ordering is a backend query change (`QueueRepository.search`'s
  // `order_by` - real server-side pagination, so it has to be the query
  // order, not a client-side re-sort of an already-fetched page). These
  // tests cover what `QueueTable` itself is responsible for: rendering
  // whatever order it's given by default (no silent client-side re-sort of
  // its own), while its existing manual per-column sort controls keep
  // working exactly as before.
  it("renders rows in the exact order given (no default re-sort) - the backend's newest-first order passes straight through", () => {
    const items = [
      buildQueue({ id: "3", queueNumber: "A003" }),
      buildQueue({ id: "2", queueNumber: "A002" }),
      buildQueue({ id: "1", queueNumber: "A001" }),
    ];
    render(<QueueTable items={items} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(within(rows[0]).getByText("A003")).toBeInTheDocument();
    expect(within(rows[1]).getByText("A002")).toBeInTheDocument();
    expect(within(rows[2]).getByText("A001")).toBeInTheDocument();
  });

  it("existing manual column sort still works unchanged - clicking a header re-sorts the fetched page", async () => {
    const items = [
      buildQueue({ id: "3", queueNumber: "A003" }),
      buildQueue({ id: "1", queueNumber: "A001" }),
      buildQueue({ id: "2", queueNumber: "A002" }),
    ];
    render(<QueueTable items={items} isLoading={false} canManage onView={noop} onCancel={noop} onReprint={noop} />);

    await userEvent.click(screen.getByRole("button", { name: /sort by queue #/i }));
    let rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("A001")).toBeInTheDocument();
    expect(within(rows[1]).getByText("A002")).toBeInTheDocument();
    expect(within(rows[2]).getByText("A003")).toBeInTheDocument();

    // Clicking the same header again reverses direction (existing toggle behavior).
    await userEvent.click(screen.getByRole("button", { name: /sort by queue #/i }));
    rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("A003")).toBeInTheDocument();
    expect(within(rows[2]).getByText("A001")).toBeInTheDocument();
  });
});
