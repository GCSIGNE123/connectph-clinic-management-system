import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditQueueDialog } from "./EditQueueDialog";
import { QueuePriority, QueueStatus, VisitClassification, type QueueDetail } from "@/features/queue/types";

const mockUpdateMutateAsync = vi.fn().mockResolvedValue({});
let mockQueueDetail: QueueDetail | undefined;
let mockDetailLoading = false;

vi.mock("@/features/queue/hooks/use-queues", () => ({
  useQueueDetail: () => ({ data: mockQueueDetail, isLoading: mockDetailLoading }),
}));

vi.mock("@/features/queue/hooks/use-queue-mutations", () => ({
  useUpdateQueue: () => ({ mutateAsync: mockUpdateMutateAsync, isPending: false }),
}));

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: (path: string) => ({
    list: () => {
      if (path === "/departments") {
        return Promise.resolve({
          items: [
            { id: "dept-1", name: "Laboratory" },
            { id: "dept-2", name: "Internal Medicine" },
          ],
        });
      }
      if (path === "/doctors") {
        return Promise.resolve({
          items: [{ id: "doc-1", first_name: "Jose", last_name: "Rizal", department_id: null }],
        });
      }
      if (path === "/services") {
        return Promise.resolve({
          items: [{ id: "svc-1", service_name: "CBC, PLATELET", name: "CBC, PLATELET" }],
        });
      }
      return Promise.resolve({ items: [] });
    },
  }),
}));

function buildDetail(overrides: Partial<QueueDetail> = {}): QueueDetail {
  return {
    id: "queue-1", queueNumber: "L001", queueDate: "2026-08-18", priority: QueuePriority.Normal,
    status: QueueStatus.Called, visitClassification: VisitClassification.Regular, branchId: "branch-1",
    departmentId: "dept-1", departmentName: "Laboratory", doctorId: null, doctorName: null,
    serviceId: "svc-1", serviceName: "CBC, PLATELET", patientId: "patient-1", patientName: "Guil Signe",
    patientNumber: "PAT-000002", createdAt: "2026-08-18T00:00:00Z", calledAt: null, visitId: "visit-1",
    vitalsTaken: false, clinicId: "clinic-1", queuePrefix: "L", notes: null, servingStartedAt: null,
    completedAt: null, createdBy: null, updatedBy: null, updatedAt: "2026-08-18T00:00:00Z",
    branchName: "Main Branch", history: [], roomName: null,
    ...overrides,
  };
}

function renderDialog(queueId: string | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <EditQueueDialog queueId={queueId} onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("EditQueueDialog", () => {
  it("pre-fills the form with the ticket's real current values", async () => {
    mockQueueDetail = buildDetail();
    mockDetailLoading = false;
    renderDialog("queue-1");

    expect(await screen.findByText("Edit Queue Ticket L001")).toBeInTheDocument();
    expect(screen.getByText("Guil Signe")).toBeInTheDocument();
    await waitFor(() => {
      const departmentSelect = screen.getAllByRole("combobox")[0] as HTMLSelectElement;
      expect(departmentSelect.value).toBe("dept-1");
    });
  });

  it("submits only the editable routing fields via useUpdateQueue, not patient/branch", async () => {
    mockQueueDetail = buildDetail();
    mockDetailLoading = false;
    const user = userEvent.setup();
    renderDialog("queue-1");

    await screen.findByText("Edit Queue Ticket L001");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(mockUpdateMutateAsync).toHaveBeenCalled());
    const payload = mockUpdateMutateAsync.mock.calls[0][0];
    expect(payload).toMatchObject({
      departmentId: "dept-1", serviceId: "svc-1", priority: QueuePriority.Normal,
      visitClassification: VisitClassification.Regular,
    });
    expect(payload).not.toHaveProperty("patientId");
    expect(payload).not.toHaveProperty("branchId");
  });

  it("shows a loading skeleton (not the form) while the ticket detail is still fetching", () => {
    mockQueueDetail = undefined;
    mockDetailLoading = true;
    renderDialog("queue-1");
    // The dialog chrome (title) renders immediately; the form itself -
    // and its Save button - must wait for real data, so the ticket's
    // previous/stale values can never be submitted by mistake.
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
  });

  it("stays closed when no queueId is given", () => {
    mockQueueDetail = undefined;
    mockDetailLoading = false;
    renderDialog(null);
    expect(screen.queryByText(/edit queue ticket/i)).not.toBeInTheDocument();
  });
});
