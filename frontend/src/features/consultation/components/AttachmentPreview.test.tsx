import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AttachmentPreview } from "./AttachmentPreview";
import type { ConsultationAttachment } from "@/features/consultation/types";

const getAttachmentFileBlob = vi.fn();

vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    getAttachmentFileBlob: (fileUrl: string) => getAttachmentFileBlob(fileUrl),
  },
}));

// jsdom has no native createObjectURL/revokeObjectURL at all - stub both
// once for the whole file rather than trying to save/restore "originals"
// that don't exist, which would leave cleanup-time revokeObjectURL calls
// (from the component's effect cleanup) crashing on unmount.
URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

function imageAttachment(overrides: Partial<ConsultationAttachment> = {}): ConsultationAttachment {
  return {
    id: "att-1",
    consultationId: "consult-1",
    attachmentType: "ClinicalImage",
    fileName: "wound.jpg",
    fileUrl: "/consultations/consult-1/attachments/att-1/file",
    fileSizeBytes: 12345,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("AttachmentPreview", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders a clickable image thumbnail and opens a full-size dialog for a ClinicalImage attachment", async () => {
    getAttachmentFileBlob.mockResolvedValueOnce(new Blob(["fake-image-bytes"], { type: "image/jpeg" }));

    renderWithClient(<AttachmentPreview attachment={imageAttachment()} />);

    const thumbnailButton = await screen.findByRole("button", { name: /view wound\.jpg full size/i });
    const thumbnailImg = thumbnailButton.querySelector("img");
    expect(thumbnailImg).toHaveAttribute("src", "blob:mock-url");

    await userEvent.click(thumbnailButton);
    expect(await screen.findByRole("heading", { name: "wound.jpg" })).toBeInTheDocument();
  });

  it("does not render an image thumbnail for a non-image attachment (PDF) - shows a View button instead", async () => {
    getAttachmentFileBlob.mockResolvedValueOnce(new Blob(["fake-pdf-bytes"], { type: "application/pdf" }));

    renderWithClient(
      <AttachmentPreview attachment={imageAttachment({ id: "att-2", attachmentType: "PDF", fileName: "referral.pdf" })} />
    );

    const viewButton = await screen.findByRole("button", { name: /view/i });
    expect(viewButton).toBeInTheDocument();
    // No <img> anywhere for a non-image attachment type.
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("shows a clear broken-image state when the file fails to load, instead of crashing or a silent blank", async () => {
    getAttachmentFileBlob.mockRejectedValueOnce(new Error("404 Not Found"));

    renderWithClient(<AttachmentPreview attachment={imageAttachment({ id: "att-3", fileName: "missing.jpg" })} />);

    await waitFor(() => {
      expect(screen.getByTitle(/could not load this file/i)).toBeInTheDocument();
    });
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });
});
