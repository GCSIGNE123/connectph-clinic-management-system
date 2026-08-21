import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import MedicinesPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(mockSearch),
}));
let mockSearch = "";

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: mockRole }, isLoading: false }),
}));

let mockRole = "Owner";
const mockList = vi.fn();
const mockCreate = vi.fn();

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({
    list: (...args: unknown[]) => mockList(...args),
    get: vi.fn(),
    create: (...args: unknown[]) => mockCreate(...args),
    update: vi.fn(),
    remove: vi.fn(),
    restore: vi.fn(),
  }),
}));

const mockStats = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockStats(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MedicinesPage />
      </ToastProvider>
    </QueryClientProvider>
  );
}

const medicine = {
  id: "med-1", clinic_id: "clinic-1", generic_name: "Paracetamol", brand_name: "Biogesic",
  strength: "500mg", dosage_form: "Tablet", unit: "tablet", reorder_level: 50, is_active: true,
  stock_status: "in_stock", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
};

const stats = { expiring_soon: 2, expired: 1, low_stock: 0, out_of_stock: 0 };

function resetMocks() {
  mockList.mockReset();
  mockCreate.mockReset();
  mockStats.mockReset().mockResolvedValue(stats);
  mockSearch = "";
}

describe("MedicinesPage", () => {
  it("renders the medicine list with stock status", async () => {
    mockRole = "Owner";
    resetMocks();
    mockList.mockResolvedValue({ items: [medicine], total: 1, limit: 50, offset: 0 });
    renderPage();

    expect(await screen.findByText("Paracetamol")).toBeInTheDocument();
    expect(screen.getByText("Biogesic")).toBeInTheDocument();
    expect(screen.getAllByText("In Stock").length).toBeGreaterThan(0);
  });

  it("renders the dashboard-style stat cards from /medicines/stats", async () => {
    mockRole = "Owner";
    resetMocks();
    mockList.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    renderPage();

    expect(await screen.findByText("Expiring Soon")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(0);
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("lets a manager add a medicine", async () => {
    mockRole = "Owner";
    resetMocks();
    mockList.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    mockCreate.mockResolvedValue({ ...medicine, id: "med-2", generic_name: "Amoxicillin" });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("No records found.")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /add/i }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Generic name/i), "Amoxicillin");
    await user.click(within(dialog).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ generic_name: "Amoxicillin" });
  });

  it("hides Add/Edit for a Doctor (view-only role) but still allows viewing batches", async () => {
    mockRole = "Doctor";
    resetMocks();
    mockList.mockResolvedValue({ items: [medicine], total: 1, limit: 50, offset: 0 });
    renderPage();

    await screen.findByText("Paracetamol");
    expect(screen.queryByRole("button", { name: /^add$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /batches/i })).toBeInTheDocument();
  });

  it("filters by stock status when a chip is clicked", async () => {
    mockRole = "Owner";
    resetMocks();
    mockList.mockResolvedValue({ items: [medicine], total: 1, limit: 50, offset: 0 });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Paracetamol");
    await user.click(screen.getByRole("button", { name: "Filter: Expired" }));

    await waitFor(() => {
      const lastCall = mockList.mock.calls.at(-1)?.[0];
      expect(lastCall).toMatchObject({ stock_status: "expired" });
    });
  });

  it("applies the initial filter from the ?filter= URL param (dashboard card deep link)", async () => {
    mockRole = "Owner";
    resetMocks();
    mockSearch = "filter=near_expiry";
    mockList.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    renderPage();

    await waitFor(() => {
      const lastCall = mockList.mock.calls.at(-1)?.[0];
      expect(lastCall).toMatchObject({ stock_status: "near_expiry" });
    });
  });
});
