import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import MedicineDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "med-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

let mockRole = "Owner";
vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: mockRole }, isLoading: false }),
}));

const mockGet = vi.fn();
const mockList = vi.fn();
const mockCreate = vi.fn();

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({
    get: (...args: unknown[]) => mockGet(...args),
    list: (...args: unknown[]) => mockList(...args),
    create: (...args: unknown[]) => mockCreate(...args),
    update: vi.fn(),
    remove: vi.fn(),
    restore: vi.fn(),
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MedicineDetailPage />
      </ToastProvider>
    </QueryClientProvider>
  );
}

const medicine = {
  id: "med-1", clinic_id: "clinic-1", generic_name: "Paracetamol", brand_name: "Biogesic",
  strength: "500mg", dosage_form: "Tablet", unit: "tablet", reorder_level: 50, is_active: true,
  created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
};

const batch = {
  id: "batch-1", clinic_id: "clinic-1", medicine_id: "med-1", batch_number: "P2026-07-A",
  quantity_received: 120, quantity_remaining: 120, expiry_date: "2026-11-30", received_date: "2026-07-01",
  supplier: "MedSupply Corp", cost_per_unit: "2.50", status: "Active",
  created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z",
};

describe("MedicineDetailPage", () => {
  it("loads the medicine and lists its batches", async () => {
    mockRole = "Owner";
    mockGet.mockReset().mockResolvedValue(medicine);
    mockList.mockReset().mockResolvedValue({ items: [batch], total: 1 });
    renderPage();

    expect(await screen.findByText(/Paracetamol \(Biogesic\)/)).toBeInTheDocument();
    expect(await screen.findByText("P2026-07-A")).toBeInTheDocument();
    expect(screen.getByText("120 / 120")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("lets a manager add a batch", async () => {
    mockRole = "Owner";
    mockGet.mockReset().mockResolvedValue(medicine);
    mockList.mockReset().mockResolvedValue({ items: [], total: 0 });
    mockCreate.mockReset().mockResolvedValue({ ...batch, id: "batch-2" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(/Paracetamol/);
    await user.click(screen.getByRole("button", { name: /add batch/i }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Batch #/i), "NEW-BATCH-01");
    await user.type(within(dialog).getByLabelText(/Quantity received/i), "50");
    await user.type(within(dialog).getByLabelText(/Quantity remaining/i), "50");
    await user.type(within(dialog).getByLabelText(/Expiry date/i), "2027-01-01");
    await user.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ batch_number: "NEW-BATCH-01" });
  });

  it("hides Add Batch/Edit for a Doctor (view-only role)", async () => {
    mockRole = "Doctor";
    mockGet.mockReset().mockResolvedValue(medicine);
    mockList.mockReset().mockResolvedValue({ items: [batch], total: 1 });
    renderPage();

    await screen.findByText("P2026-07-A");
    expect(screen.queryByRole("button", { name: /add batch/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  });

  it("shows a loading skeleton before the medicine loads", () => {
    mockGet.mockReset().mockReturnValue(new Promise(() => {}));
    mockList.mockReset().mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.queryByText("Batches")).not.toBeInTheDocument();
  });
});
