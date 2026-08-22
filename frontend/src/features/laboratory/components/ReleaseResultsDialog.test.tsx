import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { ReleaseResultsDialog } from "./ReleaseResultsDialog";

const mockReleaseResults = vi.fn();
vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: { releaseResults: (...args: unknown[]) => mockReleaseResults(...args) },
}));

const mockListPathologists = vi.fn();
vi.mock("@/features/pathologists/api/pathologists-api", () => ({
  pathologistsApi: { list: (...args: unknown[]) => mockListPathologists(...args) },
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("ReleaseResultsDialog", () => {
  it("3: the Pathologist selector appears as part of the release workflow", async () => {
    mockListPathologists.mockReset().mockResolvedValue([
      { id: "path-1", name: "Dr. Active Santos", is_active: true },
    ]);
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    expect(screen.getByText("Release Results")).toBeInTheDocument();
    expect(await screen.findByText("Dr. Active Santos")).toBeInTheDocument();
    expect(mockListPathologists).toHaveBeenCalledWith(true);
  });

  it("4: only active pathologists are requested/shown (activeOnly=true)", async () => {
    mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Active Only", is_active: true }]);
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await waitFor(() => expect(mockListPathologists).toHaveBeenCalledWith(true));
    expect(await screen.findByText("Dr. Active Only")).toBeInTheDocument();
  });

  it("does not fetch pathologists at all while closed", () => {
    mockListPathologists.mockReset();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={false} onOpenChange={() => {}} />);
    expect(mockListPathologists).not.toHaveBeenCalled();
  });

  it("releases with the selected pathologist id", async () => {
    mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
    mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
    const user = userEvent.setup();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await screen.findByText("Dr. Santos");
    await user.selectOptions(screen.getByLabelText("Pathologist (optional)"), "path-1");
    await user.click(screen.getByRole("button", { name: "Release" }));

    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1"));
  });

  it("releases with no pathologist when none is selected (preserves existing release behavior)", async () => {
    mockListPathologists.mockReset().mockResolvedValue([]);
    mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
    const user = userEvent.setup();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Release" }));
    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", null));
  });
});
