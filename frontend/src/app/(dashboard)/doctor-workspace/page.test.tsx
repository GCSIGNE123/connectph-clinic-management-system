import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { DoctorQueueItem } from "@/features/doctor-workspace/types";
import DoctorWorkspacePage from "./page";

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: "Doctor", clinicId: "clinic-1" }, isLoading: false }),
}));

vi.mock("@/features/doctor-workspace/hooks/use-doctor-dashboard", () => ({
  useDoctorDashboard: () => ({
    data: { doctorName: "Rafael Canora", branchName: null, departmentName: null, stats: {} },
    isLoading: false,
  }),
  doctorWorkspaceKeys: { all: ["doctor-workspace"], queue: (id?: string) => ["doctor-workspace", "queue", id] },
}));

vi.mock("@/features/doctor-workspace/hooks/use-doctor-session", () => ({
  useDoctorSession: () => ({ data: { active: false } }),
  useStartDoctorSession: () => ({ mutate: vi.fn(), isPending: false }),
  useNextPatient: () => ({ mutate: vi.fn(), isPending: false }),
}));

let mockQueueItems: DoctorQueueItem[] = [];
vi.mock("@/features/doctor-workspace/hooks/use-doctor-queue", () => ({
  useDoctorQueue: () => ({ data: mockQueueItems, isLoading: false }),
  useDoctorWorkspaceRealtime: () => undefined,
}));

vi.mock("@/features/doctor-workspace/components/DoctorQueueTable", () => ({
  DoctorQueueTable: () => null,
}));

function queueItem(overrides: Partial<DoctorQueueItem> = {}): DoctorQueueItem {
  return {
    visitId: "visit-1", visitNumber: "VIS-1", queueId: "queue-1", queueNumber: "A001",
    patientId: "patient-1", patientName: "Juan Dela Cruz", patientNumber: "PAT-1",
    age: 30, gender: "Male", priority: "Normal", status: "Waiting", visitType: "WalkIn",
    arrivalTime: null, calledTime: null, consultationStart: null, waitingSeconds: null,
    isLocked: false, lockedByName: null, lockedBySelf: false,
    ...overrides,
  };
}

describe("DoctorWorkspacePage header: Called-in #", () => {
  it("shows the neutral empty state when no patient is currently called", () => {
    mockQueueItems = [queueItem({ status: "Waiting" }), queueItem({ visitId: "visit-2", status: "Waiting" })];
    render(<DoctorWorkspacePage />);
    expect(screen.getByText("Called-in #:")).toBeInTheDocument();
    expect(screen.getByTestId("called-in-queue-number")).toHaveTextContent("—");
  });

  it("displays the real queue number of the currently called patient", () => {
    mockQueueItems = [
      queueItem({ visitId: "visit-1", queueNumber: "A009", status: "Called" }),
      queueItem({ visitId: "visit-2", queueNumber: "A010", status: "Waiting" }),
    ];
    render(<DoctorWorkspacePage />);
    expect(screen.getByTestId("called-in-queue-number")).toHaveTextContent("A009");
  });

  it("updates to the newly-called patient when the called visit changes", () => {
    mockQueueItems = [queueItem({ visitId: "visit-1", queueNumber: "A009", status: "Called" })];
    const { rerender } = render(<DoctorWorkspacePage />);
    expect(screen.getByTestId("called-in-queue-number")).toHaveTextContent("A009");

    mockQueueItems = [
      queueItem({ visitId: "visit-1", queueNumber: "A009", status: "InConsultation" }),
      queueItem({ visitId: "visit-2", queueNumber: "A010", status: "Called" }),
    ];
    rerender(<DoctorWorkspacePage />);
    expect(screen.getByTestId("called-in-queue-number")).toHaveTextContent("A010");
  });
});
