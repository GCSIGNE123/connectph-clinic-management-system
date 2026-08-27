import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DoctorDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "doc-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const mockGet = vi.fn();
vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({ get: (...args: unknown[]) => mockGet(...args) }),
}));

vi.mock("@/features/doctors/components/DoctorSignatureSettings", () => ({
  DoctorSignatureSettings: ({ doctor }: { doctor: { first_name: string } }) => (
    <div data-testid="signature-settings">settings for {doctor.first_name}</div>
  ),
}));

vi.mock("@/features/doctors/components/DoctorWorkspaceConfigSettings", () => ({
  DoctorWorkspaceConfigSettings: ({ doctor }: { doctor: { first_name: string } }) => (
    <div data-testid="workspace-config-settings">workspace config for {doctor.first_name}</div>
  ),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DoctorDetailPage />
    </QueryClientProvider>
  );
}

describe("DoctorDetailPage", () => {
  it("loads the doctor and renders the E-Signature section", async () => {
    mockGet.mockReset().mockResolvedValue({
      id: "doc-1", clinic_id: "clinic-1", doctor_code: "DOC-001",
      first_name: "Jose", last_name: "Rizal", specialization: "Internal Medicine",
      status: "Active", created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z", signature_url: null,
    });
    renderPage();

    expect(await screen.findByText(/Dr\. Jose Rizal/)).toBeInTheDocument();
    expect(screen.getByText("E-Signature")).toBeInTheDocument();
    expect(await screen.findByTestId("signature-settings")).toHaveTextContent("settings for Jose");
    expect(screen.getByText("Consultation Workspace")).toBeInTheDocument();
    expect(await screen.findByTestId("workspace-config-settings")).toHaveTextContent("workspace config for Jose");
  });

  it("shows a loading skeleton before the doctor loads", () => {
    mockGet.mockReset().mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.queryByText("E-Signature")).not.toBeInTheDocument();
  });
});
