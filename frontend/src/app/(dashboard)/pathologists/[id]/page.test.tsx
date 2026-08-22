import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PathologistDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "path-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const mockGet = vi.fn();
vi.mock("@/features/pathologists/api/pathologists-api", () => ({
  pathologistsApi: { get: (...args: unknown[]) => mockGet(...args) },
}));

vi.mock("@/features/pathologists/components/PathologistSignatureSettings", () => ({
  PathologistSignatureSettings: ({ pathologist }: { pathologist: { name: string } }) => (
    <div data-testid="signature-settings">settings for {pathologist.name}</div>
  ),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PathologistDetailPage />
    </QueryClientProvider>
  );
}

describe("PathologistDetailPage", () => {
  it("2: loads the pathologist and renders its E-Signature configuration section", async () => {
    mockGet.mockReset().mockResolvedValue({
      id: "path-1", clinic_id: "clinic-1", name: "Dr. Maria Santos", license_number: "PRC-12345",
      signature_url: null, is_active: true, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    });
    renderPage();

    expect(await screen.findByText("Dr. Maria Santos")).toBeInTheDocument();
    expect(screen.getByText("E-Signature")).toBeInTheDocument();
    expect(await screen.findByTestId("signature-settings")).toHaveTextContent("settings for Dr. Maria Santos");
  });

  it("shows a loading skeleton before the pathologist loads", () => {
    mockGet.mockReset().mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.queryByText("E-Signature")).not.toBeInTheDocument();
  });
});
