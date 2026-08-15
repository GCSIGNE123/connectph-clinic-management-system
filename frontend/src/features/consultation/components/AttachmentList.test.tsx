import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AttachmentList } from "./AttachmentList";
import type { ConsultationAttachment } from "@/features/consultation/types";

const getAttachmentFileBlob = vi.fn();

vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    getAttachmentFileBlob: (fileUrl: string) => getAttachmentFileBlob(fileUrl),
  },
}));

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

function attachment(overrides: Partial<ConsultationAttachment> = {}): ConsultationAttachment {
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

describe("AttachmentList", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no attachments", () => {
    renderWithClient(<AttachmentList attachments={[]} />);
    expect(screen.getByText(/no attachments yet/i)).toBeInTheDocument();
  });

  it("makes a just-uploaded attachment visible in the list immediately (not just its filename)", async () => {
    getAttachmentFileBlob.mockResolvedValue(new Blob(["fake-image-bytes"], { type: "image/jpeg" }));

    renderWithClient(<AttachmentList attachments={[attachment()]} />);

    expect(screen.getByText("wound.jpg")).toBeInTheDocument();
    expect(screen.getByText("ClinicalImage")).toBeInTheDocument();
    // The real viewable preview (clickable thumbnail), not just a filename row.
    expect(await screen.findByRole("button", { name: /view wound\.jpg full size/i })).toBeInTheDocument();
  });

  it("renders multiple attachments, each with its own independently-loaded preview", async () => {
    getAttachmentFileBlob.mockResolvedValue(new Blob(["fake-bytes"], { type: "image/jpeg" }));

    renderWithClient(
      <AttachmentList
        attachments={[
          attachment({ id: "att-1", fileName: "front.jpg" }),
          attachment({ id: "att-2", fileName: "referral.pdf", attachmentType: "PDF" }),
        ]}
      />
    );

    expect(await screen.findByRole("button", { name: /view front\.jpg full size/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /^view$/i })).toBeInTheDocument();
    expect(getAttachmentFileBlob).toHaveBeenCalledTimes(2);
  });
});
