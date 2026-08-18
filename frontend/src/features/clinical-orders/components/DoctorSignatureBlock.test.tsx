import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DoctorSignatureBlock } from "./DoctorSignatureBlock";

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

const mockFetchBlob = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetchBlob: (...args: unknown[]) => mockFetchBlob(...args),
}));

function renderBlock(props: Partial<React.ComponentProps<typeof DoctorSignatureBlock>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DoctorSignatureBlock doctorName="Jose Rizal" doctorPrcLicense="PRC-1" doctorPtrNumber="PTR-1" {...props} />
    </QueryClientProvider>
  );
}

describe("DoctorSignatureBlock", () => {
  it("renders the signature image when a snapshot path is given", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    renderBlock({ signatureFileApiPath: "/prescriptions/rx-1/signature/file" });

    await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/prescriptions/rx-1/signature/file"));
    expect(await screen.findByAltText("Doctor signature")).toBeInTheDocument();
  });

  it("renders a blank signature area (no image, no crash) when there is no snapshot", () => {
    mockFetchBlob.mockReset();
    renderBlock({ signatureFileApiPath: null });

    expect(mockFetchBlob).not.toHaveBeenCalled();
    expect(screen.queryByAltText("Doctor signature")).not.toBeInTheDocument();
    expect(screen.getByText(/Dr\. Jose Rizal/)).toBeInTheDocument();
  });

  it("omits PRC/PTR lines entirely when absent and blankLineWhenMissing is false (Prescription/Referral behavior)", () => {
    mockFetchBlob.mockReset();
    renderBlock({ doctorPrcLicense: null, doctorPtrNumber: null, signatureFileApiPath: null });

    expect(screen.queryByText(/PRC License No\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/PTR No\./)).not.toBeInTheDocument();
  });

  it("shows a blank fill-in line for missing PRC/PTR when blankLineWhenMissing is true (Medical Certificate behavior)", () => {
    mockFetchBlob.mockReset();
    renderBlock({ doctorPrcLicense: null, doctorPtrNumber: null, signatureFileApiPath: null, blankLineWhenMissing: true });

    expect(screen.getByText(/PRC License No\. ____________________/)).toBeInTheDocument();
    expect(screen.getByText(/PTR No\. ____________________/)).toBeInTheDocument();
  });

  it("uses the given fallback label when no doctor name is present", () => {
    mockFetchBlob.mockReset();
    renderBlock({ doctorName: null, signatureFileApiPath: null, fallbackLabel: "Prescribing Physician" });

    expect(screen.getByText(/Prescribing Physician/)).toBeInTheDocument();
  });
});
