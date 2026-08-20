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
const mockBatchList = vi.fn();
const mockBatchCreate = vi.fn();
const mockMovementList = vi.fn();

// `createCrudApi` is called with a different resourcePath for the medicine
// itself, the batches list, and (once a batch is selected) that batch's
// movements list - route each call to its own mock by inspecting the path,
// so the movements query never collides with the batches query.
vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: (path: string) => ({
    get: (...args: unknown[]) => mockGet(...args),
    list: (...args: unknown[]) => (path.includes("/movements") ? mockMovementList(...args) : mockBatchList(...args)),
    create: (...args: unknown[]) => mockBatchCreate(...args),
    update: vi.fn(),
    remove: vi.fn(),
    restore: vi.fn(),
  }),
}));

const mockApiPost = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockApiPost(...args),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
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

const movement = {
  id: "move-1", clinic_id: "clinic-1", batch_id: "batch-1", movement_type: "Received",
  quantity_delta: 100, resulting_quantity: 220, reason: "Initial stock", performed_by: "user-1",
  performed_by_name: "Receptionist Rey", reference_type: null, reference_id: null,
  created_at: "2026-08-21T08:30:00Z",
};

function resetMocks() {
  mockGet.mockReset();
  mockBatchList.mockReset();
  mockBatchCreate.mockReset();
  mockMovementList.mockReset();
  mockApiPost.mockReset();
}

describe("MedicineDetailPage", () => {
  it("loads the medicine and lists its batches", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    renderPage();

    expect(await screen.findByText(/Paracetamol \(Biogesic\)/)).toBeInTheDocument();
    expect(await screen.findByText("P2026-07-A")).toBeInTheDocument();
    expect(screen.getByText("120 / 120")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("lets a manager add a batch", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [], total: 0 });
    mockBatchCreate.mockResolvedValue({ ...batch, id: "batch-2" });
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

    await waitFor(() => expect(mockBatchCreate).toHaveBeenCalled());
    expect(mockBatchCreate.mock.calls[0][0]).toMatchObject({ batch_number: "NEW-BATCH-01" });
  });

  it("hides Add Batch/Edit for a Doctor (view-only role)", async () => {
    mockRole = "Doctor";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    renderPage();

    await screen.findByText("P2026-07-A");
    expect(screen.queryByRole("button", { name: /add batch/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  });

  it("shows a loading skeleton before the medicine loads", () => {
    resetMocks();
    mockGet.mockReturnValue(new Promise(() => {}));
    mockBatchList.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.queryByText("Batches")).not.toBeInTheDocument();
  });

  it("renders movement history for a selected batch", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockResolvedValue({ items: [movement], total: 1 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));

    expect(await screen.findByText(/Stock Movements - P2026-07-A/)).toBeInTheDocument();
    expect(screen.getAllByText("Received").length).toBeGreaterThan(0);
    expect(screen.getByText("+100")).toBeInTheDocument();
    expect(screen.getByText("220")).toBeInTheDocument();
    expect(screen.getByText("Initial stock")).toBeInTheDocument();
    expect(screen.getByText("Receptionist Rey")).toBeInTheDocument();
  });

  it("shows an empty state when a batch has no movements", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));

    expect(await screen.findByText("No stock movements recorded yet.")).toBeInTheDocument();
  });

  it("shows an error state when movement history fails to load", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockRejectedValue(new Error("network error"));
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));

    expect(await screen.findByText("Failed to load stock movements.")).toBeInTheDocument();
  });

  it("hides Add Stock Movement for a Doctor (view-only role)", async () => {
    mockRole = "Doctor";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockResolvedValue({ items: [movement], total: 1 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));

    await screen.findByText(/Stock Movements - P2026-07-A/);
    expect(screen.queryByRole("button", { name: /add stock movement/i })).not.toBeInTheDocument();
  });

  it("lets a manager record a Received movement with the amount adapted for the type", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockResolvedValue({ items: [], total: 0 });
    mockApiPost.mockResolvedValue({ ...movement, id: "move-2" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));
    await user.click(await screen.findByRole("button", { name: /add stock movement/i }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Quantity to add/i), "25");
    await user.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockApiPost).toHaveBeenCalled());
    expect(mockApiPost.mock.calls[0][1]).toMatchObject({ movement_type: "Received", quantity_delta: 25 });
  });

  it("requires a reason and negates the amount for an Adjustment-type removal like Expired", async () => {
    mockRole = "Owner";
    resetMocks();
    mockGet.mockResolvedValue(medicine);
    mockBatchList.mockResolvedValue({ items: [batch], total: 1 });
    mockMovementList.mockResolvedValue({ items: [], total: 0 });
    mockApiPost.mockResolvedValue({ ...movement, id: "move-3" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("P2026-07-A");
    await user.click(screen.getByRole("button", { name: /movements/i }));
    await user.click(await screen.findByRole("button", { name: /add stock movement/i }));

    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText(/Movement type/i), "Expired");
    await user.type(within(dialog).getByLabelText(/Quantity to remove/i), "10");
    // No reason entered - the browser-native `required` attribute blocks
    // submission, so the mocked POST should never fire.
    await user.click(within(dialog).getByRole("button", { name: /save/i }));
    expect(mockApiPost).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText(/Reason/i), "Past expiry");
    await user.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockApiPost).toHaveBeenCalled());
    expect(mockApiPost.mock.calls[0][1]).toMatchObject({ movement_type: "Expired", quantity_delta: -10, reason: "Past expiry" });
  });
});
