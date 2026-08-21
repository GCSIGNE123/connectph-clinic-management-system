import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardPage from "./page";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

let mockRole = "Owner";
vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { firstName: "Jose", lastName: "Rizal", role: mockRole, clinic: { name: "Test Clinic" } }, isLoading: false }),
}));

vi.mock("@/features/patients/hooks/use-patients", () => ({
  usePatients: () => ({ data: { meta: { total: 12 } }, isLoading: false }),
}));

const mockGet = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>
  );
}

describe("DashboardPage medicine inventory cards", () => {
  it("renders Expiring Soon/Expired cards with server-backed counts for an inventory-viewing role", async () => {
    mockRole = "Receptionist";
    mockGet.mockReset().mockResolvedValue({ expiring_soon: 4, expired: 2, low_stock: 1, out_of_stock: 0 });
    renderPage();

    expect(await screen.findByText("Expiring Soon")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("navigates to the filtered Medicine Inventory page when a card is clicked", async () => {
    mockRole = "Doctor";
    mockGet.mockReset().mockResolvedValue({ expiring_soon: 3, expired: 1, low_stock: 0, out_of_stock: 0 });
    const user = userEvent.setup();
    renderPage();

    const card = await screen.findByText("Expiring Soon");
    await user.click(card);

    expect(mockPush).toHaveBeenCalledWith("/medicines?filter=near_expiry");
  });

  it("hides the inventory cards for a role without inventory view permission", async () => {
    mockRole = "Cashier";
    mockGet.mockReset().mockResolvedValue({ expiring_soon: 4, expired: 2, low_stock: 1, out_of_stock: 0 });
    renderPage();

    await waitFor(() => expect(screen.getByText(/Test Clinic/)).toBeInTheDocument());
    expect(screen.queryByText("Expiring Soon")).not.toBeInTheDocument();
    expect(mockGet).not.toHaveBeenCalled();
  });
});
