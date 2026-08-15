import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VisitOrdersCard } from "./VisitOrdersCard";
import type { Order } from "@/features/clinical-orders/types";

const listOrdersForVisit = vi.fn();

vi.mock("@/features/clinical-orders/api/clinical-orders-api", () => ({
  clinicalOrdersApi: {
    listOrdersForVisit: (...args: unknown[]) => listOrdersForVisit(...args),
  },
}));

function order(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-1",
    consultationId: "consult-1",
    visitId: "visit-1",
    patientId: "patient-1",
    doctorId: "doctor-1",
    orderNumber: "ORD-20260101-000001",
    orderCategory: "Laboratory",
    priority: "Routine",
    scheduledDate: null,
    clinicalNotes: "Rule out anemia",
    status: "Completed",
    createdAt: "2026-01-01T00:00:00Z",
    items: [{ id: "item-1", itemName: "CBC" }],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("VisitOrdersCard", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no orders", async () => {
    listOrdersForVisit.mockResolvedValueOnce([]);
    renderWithClient(<VisitOrdersCard visitId="visit-1" />);
    expect(await screen.findByText(/no orders yet/i)).toBeInTheDocument();
  });

  it("renders an order row as clickable (obvious affordance, not color alone)", async () => {
    listOrdersForVisit.mockResolvedValueOnce([order()]);
    renderWithClient(<VisitOrdersCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    expect(row).toHaveClass("cursor-pointer");
    // A static, always-visible chevron icon - not just a hover-only cue.
    expect(row.querySelector("svg")).toBeInTheDocument();
  });

  it("opens the order detail dialog on click, showing items and clinical notes", async () => {
    listOrdersForVisit.mockResolvedValueOnce([order()]);
    renderWithClient(<VisitOrdersCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    await userEvent.click(row);

    expect(await screen.findByRole("heading", { name: /order ord-20260101-000001/i })).toBeInTheDocument();
    expect(screen.getByText("CBC")).toBeInTheDocument();
    expect(screen.getByText("Rule out anemia")).toBeInTheDocument();
  });

  it("opens the detail dialog on Enter key too, not just mouse click", async () => {
    listOrdersForVisit.mockResolvedValueOnce([order()]);
    renderWithClient(<VisitOrdersCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    row.focus();
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { name: /order ord-20260101-000001/i })).toBeInTheDocument();
  });
});
