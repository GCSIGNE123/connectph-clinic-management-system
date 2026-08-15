import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaboratoryAttachmentList } from "./LaboratoryAttachmentList";
import type { LaboratoryAttachment } from "@/features/laboratory/types";

const getAttachmentFileBlob = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    getAttachmentFileBlob: (fileUrl: string) => getAttachmentFileBlob(fileUrl),
  },
}));

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

function attachment(overrides: Partial<LaboratoryAttachment> = {}): LaboratoryAttachment {
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

describe("LaboratoryAttachmentList", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no images attached yet", () => {
    renderWithClient(<LaboratoryAttachmentList attachments={[]} />);
    expect(screen.getByText(/no images attached yet/i)).toBeInTheDocument();
  });

  it("makes a just-uploaded image visible in the list immediately, as a real thumbnail (not just a filename)", async () => {
    getAttachmentFileBlob.mockResolvedValue(new Blob(["fake-image-bytes"], { type: "image/jpeg" }));

    renderWithClient(<LaboratoryAttachmentList attachments={[attachment()]} />);

    expect(screen.getByText("cbc-result.jpg")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /view cbc-result\.jpg full size/i })).toBeInTheDocument();
  });

  it("renders multiple attachments, each with its own independently-loaded preview", async () => {
    getAttachmentFileBlob.mockResolvedValue(new Blob(["fake-bytes"], { type: "image/jpeg" }));

    renderWithClient(
      <LaboratoryAttachmentList
        attachments={[
          attachment({ id: "att-1", fileName: "front.jpg" }),
          attachment({ id: "att-2", fileName: "back.jpg" }),
        ]}
      />
    );

    expect(await screen.findByRole("button", { name: /view front\.jpg full size/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /view back\.jpg full size/i })).toBeInTheDocument();
    expect(getAttachmentFileBlob).toHaveBeenCalledTimes(2);
  });
});
