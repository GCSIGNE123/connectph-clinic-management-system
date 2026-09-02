import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { ReleaseResultsDialog } from "./ReleaseResultsDialog";

const mockReleaseResults = vi.fn();
const mockListMedTechs = vi.fn();
vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    releaseResults: (...args: unknown[]) => mockReleaseResults(...args),
    listMedTechs: (...args: unknown[]) => mockListMedTechs(...args),
  },
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
    mockListMedTechs.mockReset().mockResolvedValue([]);
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    expect(screen.getByText("Release Results")).toBeInTheDocument();
    expect(await screen.findByText("Dr. Active Santos")).toBeInTheDocument();
    expect(mockListPathologists).toHaveBeenCalledWith(true);
  });

  it("4: only active pathologists are requested/shown (activeOnly=true)", async () => {
    mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Active Only", is_active: true }]);
    mockListMedTechs.mockReset().mockResolvedValue([]);
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await waitFor(() => expect(mockListPathologists).toHaveBeenCalledWith(true));
    expect(await screen.findByText("Dr. Active Only")).toBeInTheDocument();
  });

  it("does not fetch pathologists or eligible MedTechs at all while closed", () => {
    mockListPathologists.mockReset();
    mockListMedTechs.mockReset();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={false} onOpenChange={() => {}} />);
    expect(mockListPathologists).not.toHaveBeenCalled();
    expect(mockListMedTechs).not.toHaveBeenCalled();
  });

  it("releases with the selected pathologist id", async () => {
    mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
    mockListMedTechs.mockReset().mockResolvedValue([]);
    mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
    const user = userEvent.setup();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await screen.findByText("Dr. Santos");
    await user.selectOptions(screen.getByLabelText("Pathologist (optional)"), "path-1");
    await user.click(screen.getByRole("button", { name: "Release" }));

    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", null));
  });

  it("releases with no pathologist and no countersigning MedTech when neither is selected (preserves existing release behavior)", async () => {
    mockListPathologists.mockReset().mockResolvedValue([]);
    mockListMedTechs.mockReset().mockResolvedValue([]);
    mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
    const user = userEvent.setup();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Release" }));
    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", null, null));
  });

  // --- Client requirement: countersigning MedTech selection, at release
  // time, from the eligible-MedTechs list only (never a Pathologist,
  // Doctor, Receptionist, or other non-MedTech role - that eligibility
  // filtering happens backend-side; the frontend simply renders whatever
  // this list returns). ---
  describe("Countersigning MedTech selector", () => {
    it("appears as part of the release workflow and lists eligible MedTechs", async () => {
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      expect(screen.getByText("Countersigning Med Technologist (optional)")).toBeInTheDocument();
      expect(await screen.findByText("Aijilie Mosquite")).toBeInTheDocument();
      expect(mockListMedTechs).toHaveBeenCalled();
    });

    it("releases with the selected countersigning MedTech id", async () => {
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Aijilie Mosquite");
      await user.selectOptions(screen.getByLabelText("Countersigning Med Technologist (optional)"), "mt-1");
      await user.click(screen.getByRole("button", { name: "Release" }));

      await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", null, "mt-1"));
    });

    it("selecting both a Pathologist and a countersigning MedTech releases with both ids independently", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Dr. Santos");
      await screen.findByText("Aijilie Mosquite");
      await user.selectOptions(screen.getByLabelText("Pathologist (optional)"), "path-1");
      await user.selectOptions(screen.getByLabelText("Countersigning Med Technologist (optional)"), "mt-1");
      await user.click(screen.getByRole("button", { name: "Release" }));

      await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", "mt-1"));
    });

    it("the selector never offers a Pathologist/Doctor/Receptionist - it only ever renders whatever the eligible-MedTechs list (backend-role-filtered) returns", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Aijilie Mosquite");
      const medTechSelect = screen.getByLabelText("Countersigning Med Technologist (optional)") as HTMLSelectElement;
      const optionTexts = Array.from(medTechSelect.options).map((o) => o.textContent);
      expect(optionTexts).toEqual(["None selected", "Aijilie Mosquite"]);
      expect(optionTexts).not.toContain("Dr. Santos");
    });
  });
});
