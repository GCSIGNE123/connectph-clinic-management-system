import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VisitLaboratoryCard } from "./VisitLaboratoryCard";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const listForVisit = vi.fn();
const getAttachmentFileBlob = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    listForVisit: (...args: unknown[]) => listForVisit(...args),
    getAttachmentFileBlob: (fileUrl: string) => getAttachmentFileBlob(fileUrl),
  },
}));

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-20260101-000001", visitId: "visit-1", visitNumber: "VIS-1",
    patientId: "patient-1", patientName: "Juan Dela Cruz", doctorId: "doctor-1", doctorName: "Jose Rizal",
    templateId: null, template: null, testType: "CBC", priority: "Routine", status: "Completed",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null,
    completedAt: "2026-01-01T00:00:00Z", releasedAt: null, releasedBy: null, invoiceItemId: null,
    createdAt: "2026-01-01T00:00:00Z",
    results: [
      {
        id: "res-1", parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 10, textValue: null,
        normalRange: "12.0-16.0", units: "g/dL", interpretation: "Low", remarks: null,
        rangeLow: 12, rangeHigh: 16, enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z",
      },
    ],
    attachments: [],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("VisitLaboratoryCard", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no laboratory orders", async () => {
    listForVisit.mockResolvedValueOnce([]);
    renderWithClient(<VisitLaboratoryCard visitId="visit-1" />);
    expect(await screen.findByText(/no laboratory orders yet/i)).toBeInTheDocument();
  });

  it("renders a laboratory order row as clickable with a visible affordance", async () => {
    listForVisit.mockResolvedValueOnce([labOrder()]);
    renderWithClient(<VisitLaboratoryCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    expect(row).toHaveClass("cursor-pointer");
    expect(row.querySelector("svg")).toBeInTheDocument();
  });

  it("opens the laboratory order detail dialog on click, showing results with interpretation and attachments", async () => {
    listForVisit.mockResolvedValueOnce([labOrder()]);
    renderWithClient(<VisitLaboratoryCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    await userEvent.click(row);

    const heading = await screen.findByRole("heading", { name: /cbc - ord-20260101-000001/i });
    const dialog = heading.closest('[role="dialog"]') as HTMLElement;
    expect(within(dialog).getByText(/Hemoglobin: 10/)).toBeInTheDocument();
    expect(within(dialog).getByText(/↓ Low/)).toBeInTheDocument();
    expect(within(dialog).getByText(/no images attached yet/i)).toBeInTheDocument();
  });

  it("shows a real thumbnail preview for an attached result image inside the detail dialog", async () => {
    getAttachmentFileBlob.mockResolvedValueOnce(new Blob(["fake-image-bytes"], { type: "image/jpeg" }));
    listForVisit.mockResolvedValueOnce([
      labOrder({
        attachments: [
          {
            id: "att-1", attachmentType: "Image", fileName: "cbc-result.jpg",
            fileUrl: "/laboratory/orders/order-1/attachments/att-1/file", fileSizeBytes: 1000,
            uploadedBy: "user-1", createdAt: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    ]);
    renderWithClient(<VisitLaboratoryCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /ORD-20260101-000001/i });
    await userEvent.click(row);

    expect(await screen.findByRole("button", { name: /view cbc-result\.jpg full size/i })).toBeInTheDocument();
  });
});
