import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LaboratoryTemplatesPage from "./page";
import type { LaboratoryTemplate } from "@/features/laboratory/types";

const useLaboratoryTemplates = vi.fn();
const exportMutate = vi.fn();
const useExportLaboratoryTemplates = vi.fn();
const deleteMutateAsync = vi.fn();
const useDeleteLaboratoryTemplate = vi.fn();

vi.mock("@/features/laboratory/hooks/use-laboratory", () => ({
  useLaboratoryTemplates: () => useLaboratoryTemplates(),
  useExportLaboratoryTemplates: () => useExportLaboratoryTemplates(),
  useDeleteLaboratoryTemplate: () => useDeleteLaboratoryTemplate(),
  useDownloadBlankImportTemplate: () => ({ mutate: vi.fn(), isPending: false }),
  usePreviewTemplateImport: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCommitTemplateImport: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateLaboratoryTemplate: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateLaboratoryTemplate: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function template(overrides: Partial<LaboratoryTemplate> = {}): LaboratoryTemplate {
  return {
    id: "tmpl-1", testName: "CBC, PLATELET", testCategory: "Hematology", specimenType: "Whole Blood",
    defaultPrice: 250, turnaroundTimeHours: 24, isActive: true, parameters: [], createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LaboratoryTemplatesPage />
    </QueryClientProvider>
  );
}

describe("LaboratoryTemplatesPage - Import/Export (bulk Excel maintenance)", () => {
  it("1: Import button renders", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Import Templates" })).toBeInTheDocument();
  });

  it("2: Export button renders", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Export Templates" })).toBeInTheDocument();
  });

  it("New Template button still renders alongside Import/Export", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "+ New Template" })).toBeInTheDocument();
  });

  it("10: clicking Export Templates triggers the export action", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Export Templates" }));
    expect(exportMutate).toHaveBeenCalled();
  });

  it("11: Export button shows a loading state while pending", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: true });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Export Templates" })).toBeDisabled();
  });

  it("9: existing templates remain editable (Edit action untouched)", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByText("CBC, PLATELET")).toBeInTheDocument();
  });

  it("3: clicking Import Templates opens the import dialog", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: false });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Import Templates" }));
    expect(screen.getByRole("heading", { name: "Import Templates" })).toBeInTheDocument();
  });
});

describe("LaboratoryTemplatesPage - Delete template", () => {
  function setup(overrides: { isPending?: boolean } = {}) {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    deleteMutateAsync.mockReset().mockResolvedValue(undefined);
    useDeleteLaboratoryTemplate.mockReturnValue({ mutateAsync: deleteMutateAsync, isPending: overrides.isPending ?? false });
  }

  it("1: Delete button renders beside Edit", () => {
    setup();
    renderPage();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("2: clicking Delete opens the confirmation dialog with the template name", async () => {
    setup();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("heading", { name: "Delete Laboratory Template" })).toBeInTheDocument();
    expect(screen.getByText(/Are you sure you want to delete "CBC, PLATELET"\?/)).toBeInTheDocument();
    expect(screen.getByText(/no longer appear in the active laboratory template list/)).toBeInTheDocument();
  });

  it("3: Cancel closes the dialog without calling delete", async () => {
    setup();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(deleteMutateAsync).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Delete Laboratory Template" })).not.toBeInTheDocument();
  });

  it("4: confirming calls the delete API with the template id", async () => {
    setup();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(deleteMutateAsync).toHaveBeenCalledWith("tmpl-1");
  });

  it("5: a successful deletion closes the dialog (list refresh + toast happen inside the hook)", async () => {
    setup();
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Delete Laboratory Template" })).not.toBeInTheDocument()
    );
  });

  it("6: the confirm Delete button is disabled while the mutation is pending", async () => {
    setup({ isPending: true });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Delete" })).toBeDisabled();
  });
});
