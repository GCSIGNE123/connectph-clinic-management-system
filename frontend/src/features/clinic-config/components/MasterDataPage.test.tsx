import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MasterDataPage } from "./MasterDataPage";

// jsdom's `File`/`Blob` don't implement `.text()` in this project's test
// environment - `handleImportCsvFile` calls it directly - same polyfill
// `services/page.test.tsx` already carries for the same reason.
if (!("text" in File.prototype)) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (File.prototype as any).text = function (this: Blob) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(this);
    });
  };
}

const mockToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

interface Widget {
  id: string;
  status?: string;
  code: string;
  label: string;
}

const mockCreateMutateAsync = vi.fn().mockResolvedValue({});
const mockUpdateMutateAsync = vi.fn().mockResolvedValue({});

let mockWidgets: Widget[] = [];

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({
    list: () => Promise.resolve({ items: mockWidgets, total: mockWidgets.length }),
    create: (payload: unknown) => mockCreateMutateAsync(payload),
    update: (id: string, payload: unknown) => mockUpdateMutateAsync(id, payload),
  }),
}));

function renderWidgetsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MasterDataPage<Widget>
        title="Widgets"
        description="Test-only fake resource."
        resourceKey="widgets"
        resourcePath="/widgets"
        canManage
        rowLabel={(w) => w.label}
        columns={[
          { header: "Code", render: (w) => w.code },
          { header: "Label", render: (w) => w.label },
        ]}
        fields={[
          { name: "code", label: "Code", type: "text", required: true },
          { name: "label", label: "Label", type: "text", required: true },
        ]}
        csv={{
          filename: "widgets.csv",
          headers: ["code", "label"],
          toRow: (w) => [w.code, w.label],
          matchKey: "code",
          fromRow: (row) => {
            if (!row.code?.trim()) throw new Error("code is required.");
            if (row.label?.trim().toLowerCase() === "invalid") {
              throw new Error(`Invalid label "${row.label}".`);
            }
            return { code: row.code.trim(), label: row.label?.trim() ?? "" };
          },
        }}
      />
    </QueryClientProvider>
  );
}

async function uploadCsv(csvText: string) {
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File([csvText], "widgets.csv", { type: "text/csv" });
  await userEvent.upload(fileInput, file);
}

describe("MasterDataPage - two-phase CSV import", () => {
  it("all rows valid: every row is applied (creates and updates both counted)", async () => {
    mockWidgets = [{ id: "w-1", code: "A", label: "Old A" }];
    mockCreateMutateAsync.mockClear();
    mockUpdateMutateAsync.mockClear();
    mockToast.mockClear();
    renderWidgetsPage();
    await screen.findByText("Old A");

    await uploadCsv("code,label\r\nA,New A\r\nB,Brand New B");

    await waitFor(() => expect(mockUpdateMutateAsync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockCreateMutateAsync).toHaveBeenCalledTimes(1));
    expect(mockUpdateMutateAsync).toHaveBeenCalledWith("w-1", { code: "A", label: "New A" });
    expect(mockCreateMutateAsync).toHaveBeenCalledWith({ code: "B", label: "Brand New B" });
    const successToast = mockToast.mock.calls.find(([arg]) => arg.title === "Import complete");
    expect(successToast?.[0].description).toBe("1 created, 1 updated.");
  });

  it("one invalid row: ZERO creates/updates occur, and the failure is reported", async () => {
    mockWidgets = [{ id: "w-1", code: "A", label: "Old A" }];
    mockCreateMutateAsync.mockClear();
    mockUpdateMutateAsync.mockClear();
    mockToast.mockClear();
    renderWidgetsPage();
    await screen.findByText("Old A");

    // Row 2 (A) is perfectly valid; row 3 (B) has the invalid label.
    await uploadCsv("code,label\r\nA,New A\r\nB,invalid");

    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(mockCreateMutateAsync).not.toHaveBeenCalled();
    expect(mockUpdateMutateAsync).not.toHaveBeenCalled();
    const [toastArg] = mockToast.mock.calls[0];
    expect(toastArg.title).toBe("Import rejected - 1 invalid row(s)");
    expect(toastArg.description).toContain("No changes were made.");
    expect(toastArg.description).toContain('Row 3: Invalid label "invalid".');
  });

  it("multiple invalid rows: every error is reported, not just the first", async () => {
    mockWidgets = [];
    mockToast.mockClear();
    renderWidgetsPage();
    await waitFor(() => expect(document.querySelector('input[type="file"]')).toBeTruthy());

    await uploadCsv("code,label\r\n,Missing code\r\nB,invalid\r\nC,invalid");

    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    const [toastArg] = mockToast.mock.calls[0];
    expect(toastArg.title).toBe("Import rejected - 3 invalid row(s)");
    expect(toastArg.description).toContain("Row 2: code is required.");
    expect(toastArg.description).toContain('Row 3: Invalid label "invalid".');
    expect(toastArg.description).toContain('Row 4: Invalid label "invalid".');
  });

  it("an invalid row appearing AFTER valid rows still leaves the valid rows unwritten (the real production bug)", async () => {
    mockWidgets = [{ id: "w-1", code: "A", label: "Old A" }];
    mockCreateMutateAsync.mockClear();
    mockUpdateMutateAsync.mockClear();
    mockToast.mockClear();
    renderWidgetsPage();
    await screen.findByText("Old A");

    // Rows 2-3 are valid and would previously have been committed before
    // the loop ever reached row 4's invalid value - this is exactly the
    // "0 created, 25 updated, 25 errors" partial-import bug being fixed.
    await uploadCsv("code,label\r\nA,New A\r\nB,Brand New B\r\nC,invalid");

    await waitFor(() => expect(mockToast).toHaveBeenCalled());
    expect(mockUpdateMutateAsync).not.toHaveBeenCalled();
    expect(mockCreateMutateAsync).not.toHaveBeenCalled();
    const [toastArg] = mockToast.mock.calls[0];
    expect(toastArg.title).toBe("Import rejected - 1 invalid row(s)");
  });

  it("existing CSV matching behavior remains intact - matchKey resolves update vs. create correctly", async () => {
    mockWidgets = [{ id: "w-1", code: "A", label: "Old A" }, { id: "w-2", code: "B", label: "Old B" }];
    mockCreateMutateAsync.mockClear();
    mockUpdateMutateAsync.mockClear();
    renderWidgetsPage();
    await screen.findByText("Old A");

    await uploadCsv("code,label\r\nA,Updated A\r\nB,Updated B\r\nC,New C");

    await waitFor(() => expect(mockCreateMutateAsync).toHaveBeenCalledTimes(1));
    expect(mockUpdateMutateAsync).toHaveBeenCalledTimes(2);
    expect(mockUpdateMutateAsync).toHaveBeenCalledWith("w-1", { code: "A", label: "Updated A" });
    expect(mockUpdateMutateAsync).toHaveBeenCalledWith("w-2", { code: "B", label: "Updated B" });
    expect(mockCreateMutateAsync).toHaveBeenCalledWith({ code: "C", label: "New C" });
  });
});
