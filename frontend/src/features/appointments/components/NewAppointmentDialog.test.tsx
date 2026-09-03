import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewAppointmentDialog } from "./NewAppointmentDialog";

// `Label`/`Select` in this codebase are plain sibling elements (no
// `htmlFor`/`id` association) - scope by the label's parent, same fix used
// by `queue/components/NewQueueDialog.test.tsx` and `EditQueueDialog.test.tsx`.
function getSelectByLabel(labelText: string): HTMLElement {
  const label = screen.getByText(labelText, { selector: "label" });
  return within(label.parentElement as HTMLElement).getByRole("combobox");
}

// Mutable per-test service catalog - "mock"-prefixed so Vitest hoists it
// alongside the `vi.mock` factory below that reads it (see
// EditQueueDialog.test.tsx's `mockServiceDeptId` for the same pattern).
let mockServices: Array<{ id: string; service_name: string; name: string; department_id: string | null }> = [];

vi.mock("@/features/patients/api/patients-api", () => ({
  patientsApi: { list: () => Promise.resolve({ data: [], meta: { page: 1, pageSize: 8, total: 0, totalPages: 0 } }) },
}));

vi.mock("@/features/patients/hooks/use-patients", () => ({
  useDebouncedValue: (value: string) => value,
}));

vi.mock("@/features/appointments/hooks/use-appointment-mutations", () => ({
  useCreateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/features/appointments/hooks/use-appointments", () => ({
  useAvailableSlots: () => ({ data: [], isFetching: false }),
}));

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: (path: string) => ({
    list: () => {
      if (path === "/departments") {
        return Promise.resolve({
          items: [
            { id: "dept-1", name: "Internal Medicine" },
            { id: "dept-2", name: "Laboratory" },
          ],
        });
      }
      if (path === "/doctors") {
        return Promise.resolve({ items: [{ id: "doc-1", first_name: "Jose", last_name: "Rizal", department_id: null }] });
      }
      if (path === "/services") {
        return Promise.resolve({ items: mockServices });
      }
      if (path === "/branches") {
        return Promise.resolve({ items: [{ id: "branch-1", name: "Main Branch" }] });
      }
      return Promise.resolve({ items: [] });
    },
  }),
}));

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NewAppointmentDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>
  );
}

describe("NewAppointmentDialog - department-aware Service filtering", () => {
  it("only offers services matching the selected Department, plus unassigned ones", async () => {
    mockServices = [
      { id: "svc-dept1", service_name: "Follow-up Visit", name: "Follow-up Visit", department_id: "dept-1" },
      { id: "svc-shared", service_name: "Medical Certificate", name: "Medical Certificate", department_id: null },
    ];
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-2"); // Laboratory - no assigned service

    const serviceSelect = getSelectByLabel("Service (optional)") as HTMLSelectElement;
    // svc-dept1 belongs to dept-1, not offered here; svc-shared (NULL) always is.
    expect(within(serviceSelect).queryByText("Follow-up Visit")).not.toBeInTheDocument();
    expect(within(serviceSelect).getByText("Medical Certificate")).toBeInTheDocument();
  });

  it("shows the department-specific empty state when no service (assigned or shared) matches", async () => {
    mockServices = [
      { id: "svc-dept1", service_name: "Follow-up Visit", name: "Follow-up Visit", department_id: "dept-1" },
    ];
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-2"); // no service assigned, none shared

    const serviceSelect = getSelectByLabel("Service (optional)") as HTMLSelectElement;
    expect(within(serviceSelect).getByText("No services available for this department.")).toBeInTheDocument();
  });

  it("clears the selected Service when it no longer belongs to the newly selected Department", async () => {
    mockServices = [
      { id: "svc-dept1", service_name: "Follow-up Visit", name: "Follow-up Visit", department_id: "dept-1" },
      { id: "svc-shared", service_name: "Medical Certificate", name: "Medical Certificate", department_id: null },
    ];
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-1");
    const serviceSelect = getSelectByLabel("Service (optional)") as HTMLSelectElement;
    await user.selectOptions(serviceSelect, "svc-dept1");
    expect(serviceSelect.value).toBe("svc-dept1");

    await user.selectOptions(getSelectByLabel("Department"), "dept-2");

    expect(serviceSelect.value).toBe("");
  });

  it("keeps an unassigned (department_id = NULL) Service selected across a Department change", async () => {
    mockServices = [
      { id: "svc-dept1", service_name: "Follow-up Visit", name: "Follow-up Visit", department_id: "dept-1" },
      { id: "svc-shared", service_name: "Medical Certificate", name: "Medical Certificate", department_id: null },
    ];
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-1");
    const serviceSelect = getSelectByLabel("Service (optional)") as HTMLSelectElement;
    await user.selectOptions(serviceSelect, "svc-shared");

    await user.selectOptions(getSelectByLabel("Department"), "dept-2");

    expect(serviceSelect.value).toBe("svc-shared");
  });
});
