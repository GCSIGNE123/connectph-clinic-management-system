import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LaboratoryTemplateImportDialog } from "./LaboratoryTemplateImportDialog";
import type { LaboratoryTemplateImportPreview, LaboratoryTemplateImportResult } from "@/features/laboratory/types";

const downloadBlankMutate = vi.fn();
const previewMutateAsync = vi.fn();
const commitMutateAsync = vi.fn();

vi.mock("@/features/laboratory/hooks/use-laboratory", () => ({
  useDownloadBlankImportTemplate: () => ({ mutate: downloadBlankMutate, isPending: false }),
  usePreviewTemplateImport: () => ({ mutateAsync: previewMutateAsync, isPending: false }),
  useCommitTemplateImport: () => ({ mutateAsync: commitMutateAsync, isPending: false }),
}));

function validPreview(overrides: Partial<LaboratoryTemplateImportPreview> = {}): LaboratoryTemplateImportPreview {
  return {
    templateCount: 1, parameterCount: 2, newTemplateCount: 1, updatedTemplateCount: 0,
    errors: [], warnings: [],
    diffs: [{ templateId: null, testName: "Urinalysis", action: "create", parameters: { added: ["Color", "pH"], changed: [], removed: [], unchanged: [] } }],
    canCommit: true,
    ...overrides,
  };
}

function xlsxFile(name = "import.xlsx") {
  return new File(["fake-bytes"], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

async function chooseFile(user: ReturnType<typeof userEvent.setup>, file: File) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, file);
}

describe("LaboratoryTemplateImportDialog", () => {
  it("3: renders when open", () => {
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);
    expect(screen.getByRole("heading", { name: "Import Templates" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Excel Template" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose .xlsx File" })).toBeInTheDocument();
  });

  it("does not render its content when closed", () => {
    render(<LaboratoryTemplateImportDialog open={false} onOpenChange={() => {}} />);
    expect(screen.queryByRole("heading", { name: "Import Templates" })).not.toBeInTheDocument();
  });

  it("4: Download Excel Template triggers the download action", async () => {
    const user = userEvent.setup();
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Download Excel Template" }));
    expect(downloadBlankMutate).toHaveBeenCalled();
  });

  it("5: an invalid (non-.xlsx) file displays an error", async () => {
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    // `userEvent.upload` enforces the input's `accept` attribute and would
    // silently refuse a mismatched file before our own handler even runs -
    // `fireEvent` bypasses that so this test can exercise our own
    // extension check (`handleFileChosen`'s ".xlsx" guard).
    fireEvent.change(input, { target: { files: [new File(["oops"], "notes.txt", { type: "text/plain" })] } });
    await waitFor(() => expect(screen.getByText(/Please choose an .xlsx file/i)).toBeInTheDocument());
    expect(previewMutateAsync).not.toHaveBeenCalled();
  });

  it("6: a chosen file triggers a preview and displays its counts", async () => {
    previewMutateAsync.mockReset().mockResolvedValue(validPreview());
    const user = userEvent.setup();
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);

    await chooseFile(user, xlsxFile());
    await waitFor(() => expect(screen.getByText("Import Preview")).toBeInTheDocument());
    expect(screen.getByText("Parameters").nextElementSibling).toHaveTextContent("2");
    expect(screen.getByText("+ Color")).toBeInTheDocument();
    expect(screen.getByText("+ pH")).toBeInTheDocument();
  });

  it("7: validation errors block the Confirm Import action", async () => {
    previewMutateAsync.mockReset().mockResolvedValue(
      validPreview({
        canCommit: false,
        errors: [{ severity: "error", sheet: "Parameters", row: 3, template: "CBC, PLATELET", parameter: "Hemoglobin", reason: "required reference range missing" }],
      })
    );
    const user = userEvent.setup();
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);

    await chooseFile(user, xlsxFile());
    await waitFor(() => expect(screen.getByText("Import Preview")).toBeInTheDocument());

    expect(screen.getByText(/required reference range missing/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm Import" })).toBeDisabled();
  });

  it("8: a successful import displays the result summary", async () => {
    previewMutateAsync.mockReset().mockResolvedValue(validPreview());
    const result: LaboratoryTemplateImportResult = { createdTemplateCount: 1, updatedTemplateCount: 0, parameterCount: 2, templateNames: ["Urinalysis"] };
    commitMutateAsync.mockReset().mockResolvedValue(result);
    const user = userEvent.setup();
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);

    await chooseFile(user, xlsxFile());
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm Import" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Confirm Import" }));

    await waitFor(() => expect(screen.getByText("Import complete.")).toBeInTheDocument());
    expect(screen.getByText("1 template(s) created")).toBeInTheDocument();
    expect(screen.getByText("2 parameter(s) written")).toBeInTheDocument();
  });

  it("11: a preview failure (unreadable file) surfaces an inline error instead of crashing", async () => {
    previewMutateAsync.mockReset().mockRejectedValue(new Error("bad file"));
    const user = userEvent.setup();
    render(<LaboratoryTemplateImportDialog open onOpenChange={() => {}} />);

    await chooseFile(user, xlsxFile());
    await waitFor(() => expect(screen.getByText(/Could not read this file/i)).toBeInTheDocument());
  });
});
