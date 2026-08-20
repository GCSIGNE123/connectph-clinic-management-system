import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import MedicinesPage from "./page";

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
  created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
};

describe("MedicinesPage", () => {
  it("renders the medicine list", async () => {
    mockRole = "Owner";
    mockList.mockReset().mockResolvedValue({ items: [medicine], total: 1, limit: 50, offset: 0 });
    renderPage();

    expect(await screen.findByText("Paracetamol")).toBeInTheDocument();
    expect(screen.getByText("Biogesic")).toBeInTheDocument();
    expect(screen.getByText("500mg")).toBeInTheDocument();
  });

  it("lets a manager add a medicine", async () => {
    mockRole = "Owner";
    mockList.mockReset().mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    mockCreate.mockReset().mockResolvedValue({ ...medicine, id: "med-2", generic_name: "Amoxicillin" });
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

  it("hides Add/Edit/Batches actions for a Doctor (view-only role)", async () => {
    mockRole = "Doctor";
    mockList.mockReset().mockResolvedValue({ items: [medicine], total: 1, limit: 50, offset: 0 });
    renderPage();

    await screen.findByText("Paracetamol");
    expect(screen.queryByRole("button", { name: /add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /batches/i })).not.toBeInTheDocument();
  });
});
