import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import VaccinationsPage from "./page";
import type { VaccinationAdministration } from "@/features/vaccinations/types";

const list = vi.fn();

vi.mock("@/features/vaccinations/api/vaccinations-api", () => ({
  vaccinationsApi: {
    list: (...args: unknown[]) => list(...args),
    administer: vi.fn(),
    cancel: vi.fn(),
  },
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

function vaccination(overrides: Partial<VaccinationAdministration> = {}): VaccinationAdministration {
  return {
    id: "vacc-1", orderId: "order-1", visitId: "visit-1", patientId: "patient-1",
    patientName: "Maria Santos", doctorId: "doctor-1", vaccineName: "MMR Vaccine",
    status: "Requested", dose: null, lotNumber: null, site: null, route: null, notes: null,
    administeredAt: null, administeredBy: null, administeredByName: null,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderWithClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <VaccinationsPage />
    </QueryClientProvider>
  );
}

describe("VaccinationsPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the patient name in the worklist", async () => {
    list.mockResolvedValueOnce([vaccination()]);
    renderWithClient();
    expect(await screen.findByText("Maria Santos")).toBeInTheDocument();
  });

  it("shows the administering personnel's name once administered", async () => {
    list.mockResolvedValueOnce([
      vaccination({
        status: "Administered", administeredBy: "user-1", administeredByName: "Test Nurse",
        administeredAt: "2026-01-02T09:00:00Z", dose: "0.5 mL",
      }),
    ]);
    renderWithClient();
    expect(await screen.findByText("Test Nurse")).toBeInTheDocument();
  });

  it("shows a safe placeholder, not a crash, when personnel data is missing (not yet administered)", async () => {
    list.mockResolvedValueOnce([vaccination({ status: "Requested" })]);
    renderWithClient();
    await screen.findByText("Maria Santos");
    const row = screen.getByText("Maria Santos").closest("tr") as HTMLElement;
    // "Administered By" cell renders the safe fallback, not "null"/"undefined"/blank crash text.
    expect(row.textContent).toContain("-");
    expect(row.textContent).not.toContain("null");
    expect(row.textContent).not.toContain("undefined");
  });

  it("shows the patient name in the Administer dialog", async () => {
    list.mockResolvedValueOnce([vaccination()]);
    renderWithClient();

    const administerButton = await screen.findByRole("button", { name: /administer/i });
    await userEvent.click(administerButton);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Maria Santos")).toBeInTheDocument();
    expect(within(dialog).getByText(/patient:/i)).toBeInTheDocument();
  });
});
