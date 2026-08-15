import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppointmentCalendar } from "./AppointmentCalendar";
import { AppointmentStatus, AppointmentType } from "@/features/appointments/types";
import { Role } from "@/types";
import type { AppointmentDetail, AppointmentListItem } from "@/features/appointments/types";

const calendar = vi.fn();
const get = vi.fn();

vi.mock("@/features/appointments/api/appointments-api", () => ({
  appointmentsApi: {
    calendar: (...args: unknown[]) => calendar(...args),
    get: (...args: unknown[]) => get(...args),
    reschedule: vi.fn(),
    cancel: vi.fn(),
    availableSlots: () => Promise.resolve([]),
  },
}));

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({ list: () => Promise.resolve({ items: [], total: 0 }) }),
}));

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { id: "user-1", role: Role.Receptionist } }),
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function calendarItem(overrides: Partial<AppointmentListItem> = {}): AppointmentListItem {
  return {
    id: "appt-1",
    appointmentNumber: "APT-000001",
    appointmentDate: todayIso(),
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
    ...overrides,
  };
}

function detailFor(item: AppointmentListItem): AppointmentDetail {
  return {
    ...item,
    clinicId: "clinic-1",
    departmentId: "dept-1",
    serviceId: "service-1",
    serviceName: "Consultation",
    branchName: "Main Branch",
    queueId: null,
    visitId: null,
    notes: null,
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-01T00:00:00Z",
    history: [],
  };
}

function renderWithClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppointmentCalendar />
    </QueryClientProvider>
  );
}

describe("AppointmentCalendar", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders an appointment entry as a real, clickable button (not plain text)", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    renderWithClient();

    const entry = await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i });
    expect(entry.tagName).toBe("BUTTON");
    expect(entry).not.toBeDisabled();
  });

  it("clicking an appointment entry opens Appointment Details with the reused dialog", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    get.mockResolvedValueOnce(detailFor(calendarItem()));
    renderWithClient();

    const entry = await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i });
    await userEvent.click(entry);

    const heading = await screen.findByRole("heading", { name: "Appointment Details" });
    const dialog = heading.closest('[role="dialog"]') as HTMLElement;
    expect(within(dialog).getByText(/Juana dela Cruz/)).toBeInTheDocument();
    expect(within(dialog).getByText("Jose Rizal")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("appt-1");
  });

  it("opens Appointment Details via keyboard activation (Enter), not just mouse click", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    get.mockResolvedValueOnce(detailFor(calendarItem()));
    renderWithClient();

    const entry = await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i });
    entry.focus();
    expect(entry).toHaveFocus();
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { name: "Appointment Details" })).toBeInTheDocument();
  });

  it("Edit Appointment from the calendar-opened dialog reuses the same reschedule flow", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    get.mockResolvedValueOnce(detailFor(calendarItem()));
    renderWithClient();

    await userEvent.click(await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Edit Appointment" }));
    expect(screen.getByRole("heading", { name: "Edit Appointment" })).toBeInTheDocument();
  });

  it("closing the details dialog clears selection, and reopening re-fetches fresh detail", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    get.mockResolvedValueOnce(detailFor(calendarItem()));
    renderWithClient();

    await userEvent.click(await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i }));
    await screen.findByRole("heading", { name: "Appointment Details" });
    await userEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Appointment Details" })).not.toBeInTheDocument();
    });

    get.mockResolvedValueOnce(detailFor(calendarItem()));
    await userEvent.click(await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i }));
    expect(await screen.findByRole("heading", { name: "Appointment Details" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("existing view-mode navigation (Day/Week/Month/Agenda) still works", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    renderWithClient();
    await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i });

    await userEvent.click(screen.getByRole("button", { name: "agenda" }));
    expect(await screen.findByRole("button", { name: /14:00.*Juana dela Cruz/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "day" }));
    expect(await screen.findByRole("button", { name: /14:00.*Juana dela Cruz/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "week" }));
    expect(await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i })).toBeInTheDocument();
  });

  it("existing Today/prev/next navigation still works without errors", async () => {
    calendar.mockResolvedValue([calendarItem()]);
    renderWithClient();
    await screen.findByRole("button", { name: /14:00 Juana dela Cruz/i });

    const todayButton = screen.getByRole("button", { name: "Today" });
    const buttons = screen.getAllByRole("button");
    const prevButton = buttons[buttons.indexOf(todayButton) - 1];
    await userEvent.click(prevButton);
    await userEvent.click(todayButton);

    // Calendar still renders (no crash) and re-fetched for the new range.
    expect(calendar.mock.calls.length).toBeGreaterThan(1);
  });
});
