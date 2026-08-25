import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LaboratoryTemplatesPage from "./page";
import type { LaboratoryTemplate } from "@/features/laboratory/types";

const useLaboratoryTemplates = vi.fn();
const exportMutate = vi.fn();
const useExportLaboratoryTemplates = vi.fn();

vi.mock("@/features/laboratory/hooks/use-laboratory", () => ({
  useLaboratoryTemplates: () => useLaboratoryTemplates(),
  useExportLaboratoryTemplates: () => useExportLaboratoryTemplates(),
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
    renderPage();
    expect(screen.getByRole("button", { name: "Import Templates" })).toBeInTheDocument();
  });

  it("2: Export button renders", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Export Templates" })).toBeInTheDocument();
  });

  it("New Template button still renders alongside Import/Export", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "+ New Template" })).toBeInTheDocument();
  });

  it("10: clicking Export Templates triggers the export action", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Export Templates" }));
    expect(exportMutate).toHaveBeenCalled();
  });

  it("11: Export button shows a loading state while pending", () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: true });
    renderPage();
    expect(screen.getByRole("button", { name: "Export Templates" })).toBeDisabled();
  });

  it("9: existing templates remain editable (Edit action untouched)", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    renderPage();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByText("CBC, PLATELET")).toBeInTheDocument();
  });

  it("3: clicking Import Templates opens the import dialog", async () => {
    useLaboratoryTemplates.mockReturnValue({ data: [template()], isLoading: false });
    useExportLaboratoryTemplates.mockReturnValue({ mutate: exportMutate, isPending: false });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Import Templates" }));
    expect(screen.getByRole("heading", { name: "Import Templates" })).toBeInTheDocument();
  });
});
