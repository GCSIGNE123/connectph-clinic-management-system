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

// Client requirement: the Countersigning MedTech selector must exclude the
// releasing user (the Med Tech In Charge) BY ID. Mocked directly (rather
// than exercising the real `authApi.me()`/localStorage token plumbing) so
// each test can set exactly which user, if any, is "currently logged in" -
// defaults to no logged-in user (`data: undefined`), matching every
// pre-existing test above that never configures this mock and must keep
// seeing the full eligible-MedTechs list unfiltered.
const mockUseCurrentUser = vi.fn(() => ({ data: undefined as { id: string } | undefined, isLoading: false }));
vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => mockUseCurrentUser(),
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
    await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
    await user.click(screen.getByRole("button", { name: "Release" }));

    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", null));
  });

  it("releases with no countersigning MedTech when none is selected (preserves existing optional behavior for that field)", async () => {
    mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
    mockListMedTechs.mockReset().mockResolvedValue([]);
    mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
    const user = userEvent.setup();
    renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

    await screen.findByText("Dr. Santos");
    await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
    await user.click(screen.getByRole("button", { name: "Release" }));
    await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", null));
  });

  // --- Product decision: Pathologist selection is now MANDATORY ---
  describe("Pathologist is now mandatory", () => {
    it("marks the field as required, not optional", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      expect(await screen.findByText("Pathologist (required)")).toBeInTheDocument();
      expect(screen.queryByText("Pathologist (optional)")).not.toBeInTheDocument();
    });

    it("blocks submission and shows a validation error when no Pathologist is selected", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([]);
      mockReleaseResults.mockReset();
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Dr. Santos");
      await user.click(screen.getByRole("button", { name: "Release" }));

      expect(await screen.findByText("Select a Pathologist before releasing results.")).toBeInTheDocument();
      expect(mockReleaseResults).not.toHaveBeenCalled();
    });

    it("does not auto-select the first (or only) available Pathologist", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Only One", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Dr. Only One");
      const select = screen.getByLabelText("Pathologist (required)") as HTMLSelectElement;
      expect(select.value).toBe("");
    });

    it("clears the validation error once a Pathologist is selected", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Dr. Santos");
      await user.click(screen.getByRole("button", { name: "Release" }));
      expect(await screen.findByText("Select a Pathologist before releasing results.")).toBeInTheDocument();

      await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
      expect(screen.queryByText("Select a Pathologist before releasing results.")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Release" }));
      await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", null));
    });
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

    it("releases with the selected countersigning MedTech id (Pathologist still required alongside it)", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Aijilie Mosquite");
      await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
      await user.selectOptions(screen.getByLabelText("Countersigning Med Technologist (optional)"), "mt-1");
      await user.click(screen.getByRole("button", { name: "Release" }));

      await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", "mt-1"));
    });

    it("selecting both a Pathologist and a countersigning MedTech releases with both ids independently", async () => {
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Dr. Santos");
      await screen.findByText("Aijilie Mosquite");
      await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
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

    // --- Client requirement: the Countersigning MedTech must never be the
    // same person as the Med Tech In Charge (the releasing/logged-in user),
    // excluded from the selector by ID - never by displayed name, so two
    // MedTechs who happen to share a name are never confused with each
    // other. The backend independently re-enforces this same rule (see
    // `test_laboratory_signatories.py`) - this is a UX convenience only. ---
    it("C: the primary MedTech (the currently logged-in user) does not appear in the Countersigning MedTech dropdown", async () => {
      mockUseCurrentUser.mockReturnValue({ data: { id: "mt-1" }, isLoading: false });
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([
        { id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" },
        { id: "mt-2", fullName: "Diego Silang", licenseNumber: "654321" },
      ]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Diego Silang");
      const medTechSelect = screen.getByLabelText("Countersigning Med Technologist (optional)") as HTMLSelectElement;
      const optionTexts = Array.from(medTechSelect.options).map((o) => o.textContent);
      expect(optionTexts).not.toContain("Aijilie Mosquite");
    });

    it("D: other eligible MedTechs (not the logged-in user) remain selectable", async () => {
      mockUseCurrentUser.mockReturnValue({ data: { id: "mt-1" }, isLoading: false });
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([
        { id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" },
        { id: "mt-2", fullName: "Diego Silang", licenseNumber: "654321" },
      ]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Diego Silang");
      const medTechSelect = screen.getByLabelText("Countersigning Med Technologist (optional)") as HTMLSelectElement;
      const optionTexts = Array.from(medTechSelect.options).map((o) => o.textContent);
      expect(optionTexts).toEqual(["None selected", "Diego Silang"]);
      expect(medTechSelect.disabled).toBe(false);
    });

    it("E: the exclusion compares actual user IDs, not the displayed name - two different users who happen to share a name are still told apart", async () => {
      mockUseCurrentUser.mockReturnValue({ data: { id: "mt-1" }, isLoading: false });
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([
        { id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" },
        { id: "mt-2", fullName: "Aijilie Mosquite", licenseNumber: "999999" },
      ]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      const medTechSelect = (await screen.findByLabelText("Countersigning Med Technologist (optional)")) as HTMLSelectElement;
      // Only the OTHER "Aijilie Mosquite" (mt-2, a different user id) is
      // offered - a name match alone would have wrongly excluded both.
      expect(Array.from(medTechSelect.options).map((o) => (o as HTMLOptionElement).value)).toEqual(["", "mt-2"]);
    });

    it("F: when the logged-in MedTech is the only eligible Laboratory user, the selector is disabled with an explanatory empty state instead of offering them", async () => {
      mockUseCurrentUser.mockReturnValue({ data: { id: "mt-1" }, isLoading: false });
      mockListPathologists.mockReset().mockResolvedValue([]);
      mockListMedTechs.mockReset().mockResolvedValue([{ id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" }]);
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await waitFor(() => expect(mockListMedTechs).toHaveBeenCalled());
      const medTechSelect = screen.getByLabelText("Countersigning Med Technologist (optional)") as HTMLSelectElement;
      const optionTexts = Array.from(medTechSelect.options).map((o) => o.textContent);
      expect(optionTexts).toEqual(["None selected"]);
      expect(medTechSelect.disabled).toBe(true);
      expect(await screen.findByText("No other eligible Med Technologist is available to countersign.")).toBeInTheDocument();
    });

    it("releasing with a countersigning MedTech other than the logged-in user still submits that id normally", async () => {
      mockUseCurrentUser.mockReturnValue({ data: { id: "mt-1" }, isLoading: false });
      mockListPathologists.mockReset().mockResolvedValue([{ id: "path-1", name: "Dr. Santos", is_active: true }]);
      mockListMedTechs.mockReset().mockResolvedValue([
        { id: "mt-1", fullName: "Aijilie Mosquite", licenseNumber: "123456" },
        { id: "mt-2", fullName: "Diego Silang", licenseNumber: "654321" },
      ]);
      mockReleaseResults.mockReset().mockResolvedValue({ id: "lab-1", status: "Released" });
      const user = userEvent.setup();
      renderWithClient(<ReleaseResultsDialog laboratoryOrderId="lab-1" open={true} onOpenChange={() => {}} />);

      await screen.findByText("Diego Silang");
      await user.selectOptions(screen.getByLabelText("Pathologist (required)"), "path-1");
      await user.selectOptions(screen.getByLabelText("Countersigning Med Technologist (optional)"), "mt-2");
      await user.click(screen.getByRole("button", { name: "Release" }));

      await waitFor(() => expect(mockReleaseResults).toHaveBeenCalledWith("lab-1", "path-1", "mt-2"));
    });
  });
});
