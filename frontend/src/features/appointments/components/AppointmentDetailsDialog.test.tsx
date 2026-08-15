import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppointmentDetailsDialog } from "./AppointmentDetailsDialog";
import { AppointmentStatus, AppointmentType } from "@/features/appointments/types";
import { Role } from "@/types";
import type { AppointmentDetail } from "@/features/appointments/types";

const get = vi.fn();
const reschedule = vi.fn();
const cancel = vi.fn();
let currentUserRole: Role | null = Role.Receptionist;

vi.mock("@/features/appointments/api/appointments-api", () => ({
  appointmentsApi: {
    get: (...args: unknown[]) => get(...args),
    reschedule: (...args: unknown[]) => reschedule(...args),
    cancel: (...args: unknown[]) => cancel(...args),
    availableSlots: () => Promise.resolve([{ startTime: "09:00:00", endTime: "09:30:00", isAvailable: true, reason: null }]),
  },
}));

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: currentUserRole ? { id: "user-1", role: currentUserRole } : undefined }),
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

function detail(overrides: Partial<AppointmentDetail> = {}): AppointmentDetail {
  return {
    id: "appt-1",
    appointmentNumber: "APT-000001",
    appointmentDate: "2026-08-20",
    startTime: "14:00:00",
    endTime: "14:30:00",
    status: AppointmentStatus.Booked,
    appointmentType: AppointmentType.NewConsultation,
    patientId: "patient-1",
    patientName: "Juana dela Cruz",
    patientNumber: "PAT-000001",
    doctorId: "doctor-1",
    doctorName: "Jose Rizal",
    departmentName: "General Medicine",
    branchId: "branch-1",
    clinicId: "clinic-1",
    departmentId: "dept-1",
    serviceId: "service-1",
    serviceName: "Consultation",
    branchName: "Main Branch",
    queueId: null,
    visitId: null,
    notes: "Follow-up on lab results",
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-01T00:00:00Z",
    history: [{ id: "h1", action: "Created", fromValue: null, toValue: "Booked", changedBy: null, changedAt: "2026-08-01T00:00:00Z", note: null }],
    ...overrides,
  };
}

function renderWithClient(appointmentId: string | null, onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppointmentDetailsDialog appointmentId={appointmentId} onOpenChange={onOpenChange} />
    </QueryClientProvider>
  );
}

describe("AppointmentDetailsDialog", () => {
  afterEach(() => {
    vi.clearAllMocks();
    currentUserRole = Role.Receptionist;
  });

  it("shows the important appointment fields", async () => {
    get.mockResolvedValueOnce(rawFrom(detail()));
    renderWithClient("appt-1");

    expect(await screen.findByRole("heading", { name: "Appointment Details" })).toBeInTheDocument();
    expect(screen.getByText(/Juana dela Cruz/)).toBeInTheDocument();
    expect(screen.getByText("Jose Rizal")).toBeInTheDocument();
    expect(screen.getByText("General Medicine")).toBeInTheDocument();
    expect(screen.getByText("Main Branch")).toBeInTheDocument();
    expect(screen.getByText("08/20/2026")).toBeInTheDocument();
    expect(screen.getByText("14:00 – 14:30")).toBeInTheDocument();
    expect(screen.getByText("Follow-up on lab results")).toBeInTheDocument();
    expect(screen.getByText("Booked")).toBeInTheDocument();
  });

  it("shows Edit and Cancel Appointment for a manage-role user on a reschedulable/cancellable status", async () => {
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Booked })));
    renderWithClient("appt-1");

    expect(await screen.findByRole("button", { name: "Edit Appointment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel Appointment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("hides Edit and Cancel for a non-manage role (e.g. Doctor) - view only", async () => {
    currentUserRole = Role.Doctor;
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Booked })));
    renderWithClient("appt-1");

    await screen.findByText(/Juana dela Cruz/);
    expect(screen.queryByRole("button", { name: "Edit Appointment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel Appointment" })).not.toBeInTheDocument();
  });

  it("hides Edit Appointment (not cancellable->reschedulable) once the appointment is Completed, and hides Cancel too", async () => {
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Completed })));
    renderWithClient("appt-1");

    await screen.findByText(/Juana dela Cruz/);
    expect(screen.queryByRole("button", { name: "Edit Appointment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel Appointment" })).not.toBeInTheDocument();
  });

  it("still allows Cancel (but not Edit) for a CheckedIn appointment - mirrors the backend's real transition table", async () => {
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.CheckedIn })));
    renderWithClient("appt-1");

    await screen.findByText(/Juana dela Cruz/);
    expect(screen.queryByRole("button", { name: "Edit Appointment" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel Appointment" })).toBeInTheDocument();
  });

  it("clicking Edit Appointment opens the reschedule form (existing edit flow, reused)", async () => {
    get.mockResolvedValueOnce(rawFrom(detail()));
    renderWithClient("appt-1");

    await userEvent.click(await screen.findByRole("button", { name: "Edit Appointment" }));
    expect(screen.getByRole("heading", { name: "Edit Appointment" })).toBeInTheDocument();
    expect(screen.getByText("New Date")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
  });

  it("submitting a new date/time reschedules and closes the dialog, notifying the caller", async () => {
    get.mockResolvedValueOnce(rawFrom(detail()));
    // Refetched after the mutation invalidates `appointmentKeys.all` - the
    // dialog closes before this resolves, but React Query still refetches
    // the (still-mounted-until-unmount) query in the background.
    get.mockResolvedValueOnce(rawFrom(detail()));
    reschedule.mockResolvedValueOnce(rawFrom(detail({ id: "appt-2", appointmentDate: "2026-08-21", startTime: "09:00:00" })));
    const onOpenChange = vi.fn();
    renderWithClient("appt-1", onOpenChange);

    await userEvent.click(await screen.findByRole("button", { name: "Edit Appointment" }));
    const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement;
    await userEvent.type(dateInput, "2026-08-21");
    await userEvent.click(await screen.findByRole("button", { name: "09:00" }));
    await userEvent.click(screen.getByRole("button", { name: "Save New Date/Time" }));

    await waitFor(() => {
      expect(reschedule).toHaveBeenCalledWith(
        "appt-1",
        expect.objectContaining({ appointmentDate: "2026-08-21", startTime: "09:00:00" })
      );
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("Cancel Appointment requires confirmation - declining the confirm dialog does not cancel", async () => {
    get.mockResolvedValueOnce(rawFrom(detail()));
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithClient("appt-1");

    await userEvent.click(await screen.findByRole("button", { name: "Cancel Appointment" }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(cancel).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("confirming cancellation calls the existing cancel API and refreshes (refetches) the detail", async () => {
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Booked })));
    cancel.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Cancelled })));
    get.mockResolvedValueOnce(rawFrom(detail({ status: AppointmentStatus.Cancelled })));
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWithClient("appt-1");

    await userEvent.click(await screen.findByRole("button", { name: "Cancel Appointment" }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith("appt-1", undefined));

    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
    confirmSpy.mockRestore();
  });
});

/** `appointmentsApi` itself is mocked (not the underlying `apiClient`), so
 * these resolve values are already the camelCase `AppointmentDetail` shape
 * the component consumes - no snake_case conversion involved here. Named
 * identity helper purely for readability at each call site. */
function rawFrom(d: AppointmentDetail) {
  return d;
}
