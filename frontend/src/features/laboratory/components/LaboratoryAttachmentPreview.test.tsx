import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaboratoryAttachmentPreview } from "./LaboratoryAttachmentPreview";
import type { LaboratoryAttachment } from "@/features/laboratory/types";

const getAttachmentFileBlob = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    getAttachmentFileBlob: (fileUrl: string) => getAttachmentFileBlob(fileUrl),
  },
}));

// jsdom has no native createObjectURL/revokeObjectURL - stub both once for
// the whole file (see AttachmentPreview.test.tsx's identical note).
URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

function imageAttachment(overrides: Partial<LaboratoryAttachment> = {}): LaboratoryAttachment {
  return {
    id: "att-1",
    attachmentType: "Image",
    fileName: "cbc-result.jpg",
    fileUrl: "/laboratory/orders/order-1/attachments/att-1/file",
    fileSizeBytes: 54321,
    uploadedBy: "user-1",
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("LaboratoryAttachmentPreview", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders a clickable image thumbnail and opens a full-size lightbox for an Image attachment", async () => {
    getAttachmentFileBlob.mockResolvedValueOnce(new Blob(["fake-image-bytes"], { type: "image/jpeg" }));

    renderWithClient(<LaboratoryAttachmentPreview attachment={imageAttachment()} />);

    const thumbnailButton = await screen.findByRole("button", { name: /view cbc-result\.jpg full size/i });
    const thumbnailImg = thumbnailButton.querySelector("img");
    expect(thumbnailImg).toHaveAttribute("src", "blob:mock-url");

    await userEvent.click(thumbnailButton);
    expect(await screen.findByRole("heading", { name: "cbc-result.jpg" })).toBeInTheDocument();
  });

  it("does not render an image thumbnail for a non-image attachment type - shows a View button instead", async () => {
    getAttachmentFileBlob.mockResolvedValueOnce(new Blob(["fake-pdf-bytes"], { type: "application/pdf" }));

    renderWithClient(
      <LaboratoryAttachmentPreview attachment={imageAttachment({ id: "att-2", attachmentType: "PDFReport", fileName: "report.pdf" })} />
    );

    const viewButton = await screen.findByRole("button", { name: /view/i });
    expect(viewButton).toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("shows a clear broken-image state when the file fails to load, instead of crashing or a silent blank", async () => {
    getAttachmentFileBlob.mockRejectedValueOnce(new Error("404 Not Found"));

    renderWithClient(<LaboratoryAttachmentPreview attachment={imageAttachment({ id: "att-3", fileName: "missing.jpg" })} />);

    await waitFor(() => {
      expect(screen.getByTitle(/could not load this file/i)).toBeInTheDocument();
    });
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });
});
