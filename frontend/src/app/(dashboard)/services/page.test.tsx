import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ServicesPage from "./page";
import { Role } from "@/types";

// jsdom's `File`/`Blob` don't implement `.text()` in this project's test
// environment - `MasterDataPage.handleImportCsvFile` calls it directly
// (`await file.text()`), so CSV-import tests need this polyfilled.
if (!("text" in File.prototype)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (File.prototype as any).text = function (this: Blob) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(this);
    });
  };
}

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: Role.Owner } }),
}));

const mockToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

const mockCreateMutateAsync = vi.fn().mockResolvedValue({});
const mockUpdateMutateAsync = vi.fn().mockResolvedValue({});
const mockDownloadCsv = vi.fn();

vi.mock("@/lib/csv", async () => {
  const actual = await vi.importActual<typeof import("@/lib/csv")>("@/lib/csv");
  return { ...actual, downloadCsv: (...args: unknown[]) => mockDownloadCsv(...args) };
});

const mockServices = [
  { id: "svc-1", clinic_id: "clinic-1", service_code: "CONS", service_name: "Consultation", default_price: "500.00", duration_minutes: 20, department_id: "dept-1", status: "Active" },
  { id: "svc-2", clinic_id: "clinic-1", service_code: "LAB1", service_name: "CBC", default_price: "150.00", duration_minutes: null, department_id: null, status: "Active" },
];

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: (path: string) => ({
    list: () => {
      if (path === "/departments") {
        return Promise.resolve({ items: [{ id: "dept-1", name: "Internal Medicine" }, { id: "dept-2", name: "Laboratory" }] });
      }
      if (path === "/services") {
        return Promise.resolve({ items: mockServices });
      }
      return Promise.resolve({ items: [] });
    },
    create: (payload: unknown) => mockCreateMutateAsync(payload),
    update: (id: string, payload: unknown) => mockUpdateMutateAsync(id, payload),
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ServicesPage />
    </QueryClientProvider>
  );
}

describe("ServicesPage - Department assignment", () => {
  it("renders a Department column, clearly labeling an unassigned service", async () => {
    renderPage();

    const row1 = (await screen.findByText("Consultation")).closest("tr") as HTMLElement;
    expect(within(row1).getByText("Internal Medicine")).toBeInTheDocument();

    const row2 = screen.getByText("CBC").closest("tr") as HTMLElement;
    expect(within(row2).getByText("Unassigned")).toBeInTheDocument();
  });

  it("the create/edit form's Department field lists the clinic's active departments plus Unassigned, with no invented default", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Consultation");
    await user.click(screen.getByRole("button", { name: /add/i }));

    const dialog = await screen.findByRole("dialog");
    const departmentSelect = within(dialog).getByLabelText("Department") as HTMLSelectElement;
    expect(departmentSelect.value).toBe(""); // Unassigned, not an invented default
    expect(within(departmentSelect).getByText("Unassigned")).toBeInTheDocument();
    expect(within(departmentSelect).getByText("Internal Medicine")).toBeInTheDocument();
    expect(within(departmentSelect).getByText("Laboratory")).toBeInTheDocument();
  });

  it("editing a service back to Unassigned sends an explicit department_id: null, not an omitted field", async () => {
    const user = userEvent.setup();
    renderPage();

    const row1 = (await screen.findByText("Consultation")).closest("tr") as HTMLElement;
    await user.click(within(row1).getByRole("button", { name: "Edit" }));

    const dialog = await screen.findByRole("dialog");
    const departmentSelect = within(dialog).getByLabelText("Department") as HTMLSelectElement;
    expect(departmentSelect.value).toBe("dept-1");
    await user.selectOptions(departmentSelect, "");
    await user.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockUpdateMutateAsync).toHaveBeenCalled());
    const [, payload] = mockUpdateMutateAsync.mock.calls[0];
    expect(payload).toHaveProperty("department_id", null);
  });

  it("CSV export includes the Department column, by name, for both assigned and unassigned services", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Consultation");
    await user.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => expect(mockDownloadCsv).toHaveBeenCalled());
    const [filename, csvText] = mockDownloadCsv.mock.calls[0];
    expect(filename).toBe("services.csv");
    expect(csvText).toContain("department");
    expect(csvText).toContain("Internal Medicine");
    expect(csvText).toContain("Unassigned");
  });

  it("CSV import resolves a valid department name to its id", async () => {
    mockCreateMutateAsync.mockClear();
    renderPage();
    await screen.findByText("Consultation");

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    const goodCsv =
      "service_code,service_name,description,default_price,duration_minutes,department,status\r\n" +
      "NEWSVC,New Service,,250,10,Laboratory,Active";
    const goodFile = new File([goodCsv], "services.csv", { type: "text/csv" });
    await userEvent.upload(fileInput, goodFile);

    await waitFor(() => expect(mockCreateMutateAsync).toHaveBeenCalled());
    expect(mockCreateMutateAsync.mock.calls[0][0]).toMatchObject({ service_code: "NEWSVC", department_id: "dept-2" });
  });

  it('CSV import maps the literal "Unassigned" value to department_id: null', async () => {
    mockCreateMutateAsync.mockClear();
    renderPage();
    await screen.findByText("Consultation");

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const csvText =
      "service_code,service_name,description,default_price,duration_minutes,department,status\r\n" +
      "NEWSVC2,New Service 2,,250,10,Unassigned,Active";
    const file = new File([csvText], "services.csv", { type: "text/csv" });
    await userEvent.upload(fileInput, file);

    await waitFor(() => expect(mockCreateMutateAsync).toHaveBeenCalled());
    expect(mockCreateMutateAsync.mock.calls[0][0]).toMatchObject({ service_code: "NEWSVC2", department_id: null });
  });

  it("CSV import rejects an unknown Department name with no changes made, and lists the real active Department names", async () => {
    mockCreateMutateAsync.mockClear();
    mockUpdateMutateAsync.mockClear();
    mockToast.mockClear();
    renderPage();
    await screen.findByText("Consultation");

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    // Mirrors the real production mistake: "Consultation" is a Service
    // name in this system, not a Department name - there is no such
    // Department, so this must be rejected, not silently treated as
    // unassigned or fuzzy-matched to something else.
    const badCsv =
      "service_code,service_name,description,default_price,duration_minutes,department,status\r\n" +
      "NEWSVC3,New Service 3,,250,10,Consultation,Active";
    const file = new File([badCsv], "services.csv", { type: "text/csv" });
    await userEvent.upload(fileInput, file);

    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(mockCreateMutateAsync).not.toHaveBeenCalled();
    expect(mockUpdateMutateAsync).not.toHaveBeenCalled();
    const [toastArg] = mockToast.mock.calls[0];
    expect(toastArg.description).toContain(
      'Invalid Department "Consultation". Valid Department names are: Internal Medicine, Laboratory.'
    );
  });

  it("CSV import treats a blank department column as unassigned - backward compatible with pre-existing exports", async () => {
    mockCreateMutateAsync.mockClear();
    renderPage();
    await screen.findByText("Consultation");

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    // No "department" column at all - the exact shape of a CSV exported
    // before this feature existed.
    const legacyCsv = "service_code,service_name,description,default_price,duration_minutes,status\r\nOLDSVC,Old Service,,100,,Active";
    const legacyFile = new File([legacyCsv], "services.csv", { type: "text/csv" });
    await userEvent.upload(fileInput, legacyFile);

    await waitFor(() => expect(mockCreateMutateAsync).toHaveBeenCalled());
    expect(mockCreateMutateAsync.mock.calls[0][0]).toMatchObject({ service_code: "OLDSVC", department_id: null });
  });
});
