import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DoctorSignatureSettings } from "./DoctorSignatureSettings";
import type { Doctor } from "@/features/clinic-config/types";
import { ApiError } from "@/lib/api-client";

// jsdom has no native createObjectURL/revokeObjectURL - stub both, same
// pattern as `AttachmentPreview.test.tsx`/`LaboratoryAttachmentPreview.test.tsx`.
URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockUpload = vi.fn();
const mockRemove = vi.fn();
const mockGetSignatureBlob = vi.fn();
vi.mock("@/features/doctors/api/doctor-signature-api", () => ({
  doctorSignatureApi: {
    upload: (...args: unknown[]) => mockUpload(...args),
    remove: (...args: unknown[]) => mockRemove(...args),
    getSignatureBlob: (...args: unknown[]) => mockGetSignatureBlob(...args),
  },
}));

function buildDoctor(overrides: Partial<Doctor> = {}): Doctor {
  return {
    id: "doc-1", clinic_id: "clinic-1", doctor_code: "DOC-001",
    first_name: "Jose", last_name: "Rizal", status: "Active",
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    signature_url: null,
    workspace_config: { sections: {} },
    ...overrides,
  };
}

function renderSettings(doctor: Doctor, onDoctorUpdated = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DoctorSignatureSettings doctor={doctor} onDoctorUpdated={onDoctorUpdated} />
    </QueryClientProvider>
  );
}

describe("DoctorSignatureSettings", () => {
  beforeEach(() => {
    mockUpload.mockReset();
    mockRemove.mockReset();
    mockGetSignatureBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
  });

  it("shows the empty state when no signature is configured", () => {
    renderSettings(buildDoctor());
    expect(screen.getByTestId("signature-not-configured")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Signature" })).not.toBeInTheDocument();
  });

  it("shows a preview and Remove action when a signature is configured", async () => {
    renderSettings(buildDoctor({ signature_url: "abc.png" }));
    await waitFor(() => expect(mockGetSignatureBlob).toHaveBeenCalledWith("doc-1"));
    expect(await screen.findByAltText("Current signature")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Signature" })).toBeInTheDocument();
  });

  it("uploads a PNG file and calls onDoctorUpdated", async () => {
    const updated = buildDoctor({ signature_url: "new.png" });
    mockUpload.mockResolvedValue(updated);
    const onDoctorUpdated = vi.fn();
    const user = userEvent.setup();
    renderSettings(buildDoctor(), onDoctorUpdated);

    await user.click(screen.getByRole("button", { name: "Upload PNG" }));
    const file = new File(["png-bytes"], "sig.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(mockUpload).toHaveBeenCalledWith("doc-1", file));
    await waitFor(() => expect(onDoctorUpdated).toHaveBeenCalledWith(updated));
  });

  it("rejects a non-PNG file client-side without calling the API", async () => {
    const user = userEvent.setup();
    renderSettings(buildDoctor());

    await user.click(screen.getByRole("button", { name: "Upload PNG" }));
    const file = new File(["jpg-bytes"], "sig.jpg", { type: "image/jpeg" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText("Only PNG files are accepted.")).toBeInTheDocument();
    expect(mockUpload).not.toHaveBeenCalled();
  });

  it("removes the current signature", async () => {
    const updated = buildDoctor({ signature_url: null });
    mockRemove.mockResolvedValue(updated);
    const onDoctorUpdated = vi.fn();
    const user = userEvent.setup();
    renderSettings(buildDoctor({ signature_url: "abc.png" }), onDoctorUpdated);

    await user.click(await screen.findByRole("button", { name: "Remove Signature" }));

    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith("doc-1"));
    await waitFor(() => expect(onDoctorUpdated).toHaveBeenCalledWith(updated));
  });

  it("surfaces a 403 permission error from the backend instead of failing silently", async () => {
    mockUpload.mockRejectedValue(new ApiError({ statusCode: 403, message: "You do not have permission to manage this doctor's signature." }));
    const user = userEvent.setup();
    renderSettings(buildDoctor());

    await user.click(screen.getByRole("button", { name: "Upload PNG" }));
    const file = new File(["png-bytes"], "sig.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText("You do not have permission to manage this doctor's signature.")).toBeInTheDocument();
  });

  it("draw panel: Save is disabled until a stroke is drawn, and clear resets it", async () => {
    const user = userEvent.setup();
    renderSettings(buildDoctor());

    await user.click(screen.getByRole("button", { name: "Draw Signature" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Clear" })).toBeDisabled();
  });
});
