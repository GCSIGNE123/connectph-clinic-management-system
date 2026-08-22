import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PathologistSignatureSettings } from "./PathologistSignatureSettings";
import type { Pathologist } from "@/features/pathologists/types";

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockUpload = vi.fn();
const mockRemove = vi.fn();
const mockGetSignatureBlob = vi.fn();
vi.mock("@/features/pathologists/api/pathologists-api", () => ({
  pathologistsApi: {
    uploadSignature: (...args: unknown[]) => mockUpload(...args),
    removeSignature: (...args: unknown[]) => mockRemove(...args),
    getSignatureBlob: (...args: unknown[]) => mockGetSignatureBlob(...args),
  },
}));

function buildPathologist(overrides: Partial<Pathologist> = {}): Pathologist {
  return {
    id: "path-1", clinic_id: "clinic-1", name: "Dr. Maria Santos", license_number: "PRC-12345",
    signature_url: null, is_active: true,
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function renderSettings(pathologist: Pathologist, onPathologistUpdated = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PathologistSignatureSettings pathologist={pathologist} onPathologistUpdated={onPathologistUpdated} />
    </QueryClientProvider>
  );
}

describe("PathologistSignatureSettings", () => {
  beforeEach(() => {
    mockUpload.mockReset();
    mockRemove.mockReset();
    mockGetSignatureBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
  });

  it("2: renders the pathologist configuration/signature panel with an empty state when unconfigured", () => {
    renderSettings(buildPathologist());
    expect(screen.getByTestId("signature-not-configured")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Signature" })).not.toBeInTheDocument();
  });

  it("uploads a PNG signature and calls onPathologistUpdated", async () => {
    mockUpload.mockResolvedValue(buildPathologist({ signature_url: "sig-new.png" }));
    const onUpdated = vi.fn();
    const user = userEvent.setup();
    renderSettings(buildPathologist(), onUpdated);

    await user.click(screen.getByRole("button", { name: "Upload PNG" }));
    const file = new File(["png-bytes"], "sig.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(mockUpload).toHaveBeenCalledWith("path-1", file));
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ signature_url: "sig-new.png" })));
  });

  it("shows the current signature preview and allows removal when configured", async () => {
    const onUpdated = vi.fn();
    mockRemove.mockResolvedValue(buildPathologist({ signature_url: null }));
    const user = userEvent.setup();
    renderSettings(buildPathologist({ signature_url: "sig-existing.png" }), onUpdated);

    expect(await screen.findByAltText("Current signature")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Signature" }));

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith("path-1"));
    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
  });
});
