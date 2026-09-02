import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { ResultEntryDialog } from "./ResultEntryDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const getOrder = vi.fn();
const enterResults = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    getOrder: (id: string) => getOrder(id),
    enterResults: (id: string, results: unknown, expectedUpdatedAt?: unknown) => enterResults(id, results, expectedUpdatedAt),
    listAttachments: vi.fn().mockResolvedValue([]),
  },
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-20260101-000001", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: "A001",
    patientId: "patient-1", patientName: "Juan Dela Cruz", patientAge: null, patientSex: null, doctorId: "doctor-1", doctorName: "Jose Rizal",
    templateId: "template-1",
    template: {
      id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0,
      turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
      parameters: [
        {
          id: "param-1", parameterName: "Hemoglobin", unit: "g/dL", normalRange: "12.0-16.0",
          resultType: "Numeric", displayOrder: 0, rangeLow: 12.0, rangeHigh: 16.0, expectedNormalText: null,
        },
      ],
    },
    testType: "CBC", priority: "Routine", status: "Processing",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null,
    completedAt: null, releasedAt: null, releasedBy: null, invoiceItemId: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [],
    attachments: [],
    ...overrides,
  };
}

function bloodTypingOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return labOrder({
    testType: "Blood Typing",
    templateId: "template-bt",
    template: {
      id: "template-bt", testName: "Blood Typing", testCategory: "Immunohematology", specimenType: "Whole Blood",
      defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
      parameters: [
        {
          id: "param-abo", parameterName: "ABO Group", unit: null, normalRange: null, resultType: "Categorical",
          displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: ["A", "B", "AB", "O"],
        },
        {
          id: "param-rh", parameterName: "Rh Factor", unit: null, normalRange: null, resultType: "Categorical",
          displayOrder: 1, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: ["Positive", "Negative"],
        },
      ],
    },
    ...overrides,
  });
}

// Phase 4B: a realistic mixed-section, mixed-type Urinalysis template -
// mirrors the actual Phase 4A seeded shape (Physical/Chemical/Microscopic),
// with "Color" given test-only options (the seeded default deliberately has
// none - see Phase 4A) so Categorical rendering can be exercised without
// inventing production clinical option lists.
function urinalysisOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return labOrder({
    testType: "Urinalysis",
    templateId: "template-ua",
    template: {
      id: "template-ua", testName: "Urinalysis", testCategory: "Clinical Microscopy", specimenType: "Urine",
      defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
      parameters: [
        {
          id: "p-color", parameterName: "Color", unit: null, normalRange: null, resultType: "Categorical",
          displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null,
          options: ["Straw", "Yellow", "Amber"], section: "Physical Examination",
        },
        {
          id: "p-sg", parameterName: "Specific Gravity", unit: null, normalRange: "1.005-1.030",
          resultType: "Numeric", displayOrder: 1, rangeLow: 1.005, rangeHigh: 1.03, expectedNormalText: null,
          options: null, section: "Physical Examination",
        },
        {
          id: "p-protein", parameterName: "Protein", unit: null, normalRange: null, resultType: "Categorical",
          displayOrder: 2, rangeLow: null, rangeHigh: null, expectedNormalText: null,
          options: null, section: "Chemical Examination",
        },
        {
          id: "p-rbc", parameterName: "RBC", unit: "/hpf", normalRange: null, resultType: "Numeric",
          displayOrder: 3, rangeLow: null, rangeHigh: null, expectedNormalText: null,
          options: null, section: "Microscopic Examination",
        },
        {
          id: "p-bacteria", parameterName: "Bacteria", unit: null, normalRange: null, resultType: "Text",
          displayOrder: 4, rangeLow: null, rangeHigh: null, expectedNormalText: null,
          options: null, section: "Microscopic Examination",
        },
      ],
    },
    ...overrides,
  });
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ResultEntryDialog", () => {
  it("Phase 2B: fetches the order fresh on open and prefills from the backend-resolved range, not the stale prop", async () => {
    const staleOrder = labOrder(); // prop's template says 12.0-16.0
    const resolved = labOrder({
      template: {
        ...staleOrder.template!,
        parameters: [
          { ...staleOrder.template!.parameters[0], rangeLow: 13.0, rangeHigh: 17.0, normalRange: "13.0000-17.0000" },
        ],
      },
    });
    getOrder.mockResolvedValue(resolved);

    renderWithClient(<ResultEntryDialog order={staleOrder} open onOpenChange={() => {}} />);

    expect(getOrder).toHaveBeenCalledWith("lab-1");
    await waitFor(() => {
      expect(screen.getByDisplayValue("13.0000-17.0000")).toBeInTheDocument();
    });
  });

  it("falls back to the passed-in order's own range while the fresh fetch is in flight", () => {
    getOrder.mockReturnValue(new Promise(() => {})); // never resolves during this test
    renderWithClient(<ResultEntryDialog order={labOrder()} open onOpenChange={() => {}} />);
    expect(screen.getByDisplayValue("12.0-16.0")).toBeInTheDocument();
  });

  describe("Phase 4H: reopening a partially-completed templated order", () => {
    it("shows every template parameter, not just the already-entered ones - the not-yet-entered one stays blank and editable", async () => {
      const order = bloodTypingOrder({
        results: [
          {
            id: "res-abo", parameterName: "ABO Group", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "O" }, site: null,
          },
          // Rh Factor was never entered - a partial save.
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      // Both parameters are shown - the saved ABO Group value, AND a blank,
      // still-selectable Rh Factor row (previously this second row was
      // silently missing entirely). Both are configured-options Categorical
      // parameters, so both render via the simplified layout (heading, not
      // an editable Parameter input - see the "UI restrictions" describe
      // block below for that assertion).
      expect(await screen.findByDisplayValue("O")).toBeInTheDocument();
      expect(screen.getByText("ABO Group")).toBeInTheDocument();
      expect(screen.getByText("Rh Factor")).toBeInTheDocument();
      // Rh Factor's own Categorical select is present and still unselected.
      const selects = screen.getAllByRole("combobox").filter((el) => el.tagName === "SELECT") as HTMLSelectElement[];
      const rhSelect = selects.find(
        (s) => s.value === "" && Array.from(s.options).some((o) => o.value === "Positive")
      );
      expect(rhSelect).toBeTruthy();
    });

    it("resubmitting after filling in the previously-missing parameter includes BOTH results, never dropping the already-saved one", async () => {
      const order = bloodTypingOrder({
        results: [
          {
            id: "res-abo", parameterName: "ABO Group", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "O" }, site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const selects = (await screen.findAllByRole("combobox")).filter((el) => el.tagName === "SELECT") as HTMLSelectElement[];
      const rhSelect = selects.find(
        (s) => s.value === "" && Array.from(s.options).some((o) => o.value === "Positive")
      )!;
      await userEvent.selectOptions(rhSelect, "Positive");
      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      const byName = Object.fromEntries(submitted.map((r) => [r.parameterName, r]));
      expect(byName["ABO Group"].structuredValue).toEqual({ value: "O" });
      expect(byName["Rh Factor"].structuredValue).toEqual({ value: "Positive" });
    });

    it("Phase 5: a sectioned template (Urinalysis) partially saved across two sections shows every parameter, section headers included, on reopen", async () => {
      const order = urinalysisOrder({
        results: [
          {
            id: "res-color", parameterName: "Color", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Straw" }, site: null,
          },
          {
            id: "res-protein", parameterName: "Protein", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
          },
          // Specific Gravity, RBC, and Bacteria were never entered - a
          // partial save spanning two of the three sections.
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      // All 3 section headers still render (none collapsed/dropped because
      // a section had only unentered parameters).
      expect(await screen.findByText("Physical Examination")).toBeInTheDocument();
      expect(screen.getByText("Chemical Examination")).toBeInTheDocument();
      expect(screen.getByText("Microscopic Examination")).toBeInTheDocument();

      // All 5 parameters render in template order, saved value included.
      // Color/Protein are configured/unconfigured-options Categorical
      // respectively (Color simplified - heading, not an editable Parameter
      // input; Protein unconfigured - still the full grid), Specific
      // Gravity/RBC/Bacteria are Numeric/Text (full grid, unaffected).
      expect(screen.getByText("Color")).toBeInTheDocument();
      const paramInputs = screen.getAllByPlaceholderText("e.g. Hemoglobin") as HTMLInputElement[];
      expect(paramInputs.map((i) => i.value)).toEqual(["Specific Gravity", "Protein", "RBC", "Bacteria"]);
      expect(screen.getByDisplayValue("Straw")).toBeInTheDocument();
    });
  });

  describe("Phase 4I: optimistic-concurrency guard on save", () => {
    it("echoes back the order's updatedAt as the third enterResults argument, so the backend can detect a stale/concurrent save", async () => {
      const order = labOrder({ updatedAt: "2026-03-01T10:00:00Z" });
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, , expectedUpdatedAt] = enterResults.mock.calls[enterResults.mock.calls.length - 1];
      expect(expectedUpdatedAt).toBe("2026-03-01T10:00:00Z");
    });

    it("surfaces a clear conflict message (not a silent failure) when the save is rejected as stale", async () => {
      const order = labOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockRejectedValue(
        new ApiError({ statusCode: 409, message: "This order was updated by someone else since you opened it. Reload and try again." })
      );
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      expect(await screen.findByText(/updated by someone else/i)).toBeInTheDocument();
    });
  });

  describe("Phase 3: Categorical (Blood Typing)", () => {
    it("#19/#20: renders a select control per Categorical parameter, with options sourced from the template, not hard-coded", async () => {
      const order = bloodTypingOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);

      await waitFor(() => {
        // Both ABO Group and Rh Factor rows start on the neutral
        // "Select..." placeholder - never auto-selecting A/B/AB/O/Positive/Negative.
        expect(screen.getAllByDisplayValue("Select...")).toHaveLength(2);
      });
      expect(screen.getByRole("option", { name: "A" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "AB" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Positive" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Negative" })).toBeInTheDocument();
    });

    it("#21: selecting an option updates the result and is included in the submitted payload", async () => {
      const order = bloodTypingOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const valueSelects = screen.getAllByDisplayValue("Select...");
      await userEvent.selectOptions(valueSelects[0], "O");
      await userEvent.selectOptions(valueSelects[1], "Positive");

      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[0] as [string, Array<Record<string, unknown>>];
      const abo = submitted.find((r) => r.parameterName === "ABO Group");
      const rh = submitted.find((r) => r.parameterName === "Rh Factor");
      expect(abo?.structuredValue).toEqual({ value: "O" });
      expect(rh?.structuredValue).toEqual({ value: "Positive" });
      // Never concatenated into a text field, and never given a false interpretation.
      expect(abo?.interpretation).toBeNull();
      expect(rh?.interpretation).toBeNull();
    });

    it("#22: an already-entered categorical result reloads into the correct selected option, not blank", async () => {
      const order = bloodTypingOrder({
        results: [
          {
            id: "res-abo", parameterName: "ABO Group", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "O" },
            site: null,
          },
          {
            id: "res-rh", parameterName: "Rh Factor", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Positive" },
            site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("O")).toBeInTheDocument();
        expect(screen.getByDisplayValue("Positive")).toBeInTheDocument();
      });
    });

    it("#23: the required categorical selection starts empty and is never auto-selected", async () => {
      const order = bloodTypingOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      const valueSelects = screen.getAllByDisplayValue("Select...");
      expect(valueSelects).toHaveLength(2);
    });

    it("#24: existing Numeric/Text result inputs remain unchanged alongside a Categorical row", async () => {
      const order = bloodTypingOrder({
        template: {
          ...bloodTypingOrder().template!,
          parameters: [
            ...bloodTypingOrder().template!.parameters,
            {
              id: "param-remarks", parameterName: "Remarks", unit: null, normalRange: null, resultType: "Text",
              displayOrder: 2, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: null,
            },
          ],
        },
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      // ABO Group/Rh Factor are configured-options Categorical (simplified
      // layout, no editable Parameter input); the added Text "Remarks"
      // parameter still uses the full grid, unchanged.
      expect(screen.getAllByPlaceholderText("e.g. Hemoglobin").length).toBe(1);
      expect(screen.getByText("ABO Group")).toBeInTheDocument();
      expect(screen.getByText("Rh Factor")).toBeInTheDocument();
      expect(screen.getAllByRole("textbox").length).toBeGreaterThan(0); // the Text row's Textarea still renders
    });
  });

  describe("Phase 4B: Urinalysis (generic section/mixed-type rendering)", () => {
    it("#1/#2/#3: groups parameters by section, in first-appearance order, preserving parameter order within each section", async () => {
      const order = urinalysisOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);

      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
      expect(headings).toEqual(["Physical Examination", "Chemical Examination", "Microscopic Examination"]);

      // Parameter-name inputs appear in template display_order, not
      // re-sorted. Color is a configured-options Categorical parameter, so
      // it renders via the simplified layout (a heading, not an editable
      // Parameter input) - the remaining Numeric/unconfigured-Categorical/
      // Text parameters still use the full grid, unaffected.
      expect(screen.getByText("Color")).toBeInTheDocument();
      const paramInputs = screen.getAllByPlaceholderText("e.g. Hemoglobin") as HTMLInputElement[];
      expect(paramInputs.map((i) => i.value)).toEqual([
        "Specific Gravity", "Protein", "RBC", "Bacteria",
      ]);
    });

    it("#4/#5: Numeric parameters render a numeric input, and a configured range is displayed in Normal Range", async () => {
      const order = urinalysisOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const numberInputs = document.querySelectorAll('input[type="number"]');
      expect(numberInputs.length).toBeGreaterThanOrEqual(2); // Specific Gravity + RBC
      expect(screen.getByDisplayValue("1.005-1.030")).toBeInTheDocument();
    });

    it("#6: an existing Numeric Urinalysis result reloads its saved value, not blank", async () => {
      const order = urinalysisOrder({
        results: [
          {
            id: "res-sg", parameterName: "Specific Gravity", resultType: "Numeric", numericValue: 1.015, textValue: null,
            normalRange: "1.005-1.030", units: null, interpretation: null, remarks: null, rangeLow: 1.005, rangeHigh: 1.03,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null,
            site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("1.015")).toBeInTheDocument());
    });

    it("#7/#8/#9: configured Categorical options render in a Select, sourced only from template data", async () => {
      const order = urinalysisOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      expect(screen.getByRole("option", { name: "Straw" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Yellow" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Amber" })).toBeInTheDocument();
      // Never a hard-coded reagent-strip scale anywhere in the DOM.
      expect(screen.queryByRole("option", { name: "Negative" })).not.toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Trace" })).not.toBeInTheDocument();
    });

    it("#10/#11: an options-less Categorical parameter (Protein) shows a disabled configuration-warning control and is excluded from submission", async () => {
      const order = urinalysisOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const warningOption = screen.getByRole("option", { name: "No options configured" });
      expect((warningOption.closest("select") as HTMLSelectElement).disabled).toBe(true);

      // Fill in the other valid rows so the submission isn't empty, then submit.
      const colorSelect = screen.getByRole("option", { name: "Straw" }).closest("select") as HTMLSelectElement;
      await userEvent.selectOptions(colorSelect, "Straw");
      const numberInputs = document.querySelectorAll('input[type="number"]');
      await userEvent.type(numberInputs[0] as HTMLInputElement, "1.015");
      await userEvent.type(numberInputs[1] as HTMLInputElement, "2");

      await userEvent.click(screen.getByRole("button", { name: /save results/i }));
      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      expect(submitted.some((r) => r.parameterName === "Protein")).toBe(false);
      expect(submitted.some((r) => r.parameterName === "Color")).toBe(true);
    });

    it("#12: a previously-saved Categorical value reloads into the correct selected option", async () => {
      const order = urinalysisOrder({
        results: [
          {
            id: "res-color", parameterName: "Color", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Yellow" },
            site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("Yellow")).toBeInTheDocument());
    });

    it("#13/#14: Text parameters render a text input, and a saved text value reloads correctly", async () => {
      const order = urinalysisOrder({
        results: [
          {
            id: "res-bacteria", parameterName: "Bacteria", resultType: "Text", numericValue: null, textValue: "Few",
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null,
            site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("Few")).toBeInTheDocument());
    });

    it("#15: a single template mixing Numeric, Categorical, and Text renders all three correctly, in one dialog", async () => {
      const order = urinalysisOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      expect(document.querySelectorAll('input[type="number"]').length).toBeGreaterThanOrEqual(2); // Numeric
      expect(screen.getByRole("option", { name: "Straw" })).toBeInTheDocument(); // Categorical
      expect(screen.getAllByRole("textbox").length).toBeGreaterThan(0); // Text (Bacteria's Textarea)
    });
  });

  describe("Phase 4C: qualitative catalog (HCG/HBsAg/VDRL/Dengue) - existing generic mechanism, no new component code", () => {
    function singleResultOrder(testName: string, options: string[] | null, overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
      return labOrder({
        testType: testName,
        templateId: "template-single",
        template: {
          id: "template-single", testName, testCategory: "Immunology", specimenType: null,
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-result", parameterName: "Result", unit: null, normalRange: null, resultType: "Categorical",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null, options,
            },
          ],
        },
        ...overrides,
      });
    }

    it("HCG (test-only configured options): renders the existing Categorical Select with configured choices", async () => {
      const order = singleResultOrder("HCG (Serum)", ["Positive", "Negative"]);
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "Positive" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Negative" })).toBeInTheDocument();
    });

    it("HCG: a saved result reloads into the correct selected option", async () => {
      const order = singleResultOrder("HCG (Urine)", ["Positive", "Negative"], {
        results: [
          {
            id: "res-hcg", parameterName: "Result", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Negative" },
            site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("Negative")).toBeInTheDocument());
    });

    it("HBsAg (unconfigured, production-realistic): shows the disabled 'No options configured' state", async () => {
      const order = singleResultOrder("Hepatitis B Antigen (HBsAg)", null);
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      const warningOption = screen.getByRole("option", { name: "No options configured" });
      expect((warningOption.closest("select") as HTMLSelectElement).disabled).toBe(true);
    });

    it("VDRL (test-only configured options): renders as Categorical, not Titer - no Titer-specific control exists", async () => {
      const order = singleResultOrder("VDRL / Syphilis Test", ["Reactive", "Non-reactive"]);
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "Reactive" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Non-reactive" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Titer" })).not.toBeInTheDocument();
    });

    it("Dengue Rapid Test: three independent Categorical parameters (NS1/IgM/IgG) render as three selects, each with its own options", async () => {
      const order = labOrder({
        testType: "Dengue Rapid Test",
        templateId: "template-dengue",
        template: {
          id: "template-dengue", testName: "Dengue Rapid Test", testCategory: "Immunology", specimenType: null,
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-ns1", parameterName: "NS1", unit: null, normalRange: null, resultType: "Categorical",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: ["Positive", "Negative"],
            },
            {
              id: "p-igm", parameterName: "IgM", unit: null, normalRange: null, resultType: "Categorical",
              displayOrder: 1, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: ["Positive", "Negative"],
            },
            {
              id: "p-igg", parameterName: "IgG", unit: null, normalRange: null, resultType: "Categorical",
              displayOrder: 2, rangeLow: null, rangeHigh: null, expectedNormalText: null, options: ["Positive", "Negative"],
            },
          ],
        },
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      // All three are configured-options Categorical parameters, so all
      // three render via the simplified layout (heading, not an editable
      // Parameter input).
      expect(screen.getByText("NS1")).toBeInTheDocument();
      expect(screen.getByText("IgM")).toBeInTheDocument();
      expect(screen.getByText("IgG")).toBeInTheDocument();
      expect(screen.getAllByRole("option", { name: "Positive" }).length).toBe(3);
    });
  });

  describe("Phase 4D: KOH Mount (generic requires_site handling)", () => {
    function kohOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
      return labOrder({
        testType: "KOH Mount",
        templateId: "template-koh",
        template: {
          id: "template-koh", testName: "KOH Mount", testCategory: "Clinical Microscopy", specimenType: "Varies (per site)",
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-koh-result", parameterName: "Result", unit: null, normalRange: null, resultType: "Categorical",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null,
              options: ["Positive", "Negative"], requiresSite: true,
            },
          ],
        },
        ...overrides,
      });
    }

    it("shows a generic Site input purely because the parameter declares requiresSite - not a KOH-specific branch", async () => {
      const order = kohOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByPlaceholderText("e.g. Skin, Vaginal, Nail")).toBeInTheDocument();
    });

    it("a parameter with requiresSite=false never shows the Site input (e.g. Blood Typing)", async () => {
      const order = bloodTypingOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.queryByPlaceholderText("e.g. Skin, Vaginal, Nail")).not.toBeInTheDocument();
    });

    it("entering a site includes it in the submitted payload", async () => {
      const order = kohOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      await userEvent.type(screen.getByPlaceholderText("e.g. Skin, Vaginal, Nail"), "Skin");
      const valueSelect = screen.getByRole("option", { name: "Positive" }).closest("select") as HTMLSelectElement;
      await userEvent.selectOptions(valueSelect, "Positive");
      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      expect(submitted[0].site).toBe("Skin");
      expect(submitted[0].structuredValue).toEqual({ value: "Positive" });
    });

    it("a saved site reloads into the Site input, not blank", async () => {
      const order = kohOrder({
        results: [
          {
            id: "res-koh", parameterName: "Result", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Negative" }, site: "Vaginal",
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("Vaginal")).toBeInTheDocument());
      expect(screen.getByDisplayValue("Negative")).toBeInTheDocument();
    });
  });

  describe("Phase 4E: Titer (generic free-text lifecycle, using existing Text storage)", () => {
    function titerOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
      return labOrder({
        testType: "VDRL",
        templateId: "template-vdrl",
        template: {
          id: "template-vdrl", testName: "VDRL", testCategory: "Serology", specimenType: "Blood",
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-titer", parameterName: "VDRL Titer", unit: null, normalRange: null, resultType: "Titer",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null,
            },
          ],
        },
        ...overrides,
      });
    }

    it("Titer appears as a valid Type and the Type selector is locked (template-configured, not freely selectable)", async () => {
      const order = titerOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "Titer" })).toBeInTheDocument();
      expect(screen.getByDisplayValue("Titer")).toBeDisabled();
    });

    it("a Titer value can be entered and is included in the submitted payload without being nulled", async () => {
      const order = titerOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const row = screen.getByDisplayValue("VDRL Titer").closest(".grid") as HTMLElement;
      const textarea = within(row).getAllByRole("textbox")[1];
      await userEvent.type(textarea, "1:160");
      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      expect(submitted[0].textValue).toBe("1:160");
      expect(submitted[0].resultType).toBe("Titer");
    });

    it("a persisted Titer value reloads correctly and no automatic interpretation is shown", async () => {
      const order = titerOrder({
        results: [
          {
            id: "res-titer", parameterName: "VDRL Titer", resultType: "Titer", numericValue: null, textValue: "1:80",
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      // No automatic interpretation: the row's `interpretation` stays exactly
      // as loaded (null) - nothing recomputes it for Titer. Reaching this
      // render at all (rather than throwing/crashing on an unhandled
      // resultType) is itself proof the reload lifecycle is intact.
      await waitFor(() => expect(screen.getByDisplayValue("1:80")).toBeInTheDocument());
    });
  });

  describe("Phase 4E: Microscopy (generic free-text lifecycle, using existing Text storage)", () => {
    function microscopyOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
      return labOrder({
        testType: "Gram Stain",
        templateId: "template-gram",
        template: {
          id: "template-gram", testName: "Gram Stain", testCategory: "Clinical Microscopy", specimenType: "Varies",
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-micro", parameterName: "Findings", unit: null, normalRange: null, resultType: "Microscopy",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: null,
            },
          ],
        },
        ...overrides,
      });
    }

    it("Microscopy appears as a valid, locked Type and renders a free-text control - no invented option list", async () => {
      const order = microscopyOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "Microscopy" })).toBeInTheDocument();
      expect(screen.getByDisplayValue("Microscopy")).toBeDisabled();
      const row = screen.getByDisplayValue("Findings").closest(".grid") as HTMLElement;
      const textboxesInRow = within(row).getAllByRole("textbox");
      expect(textboxesInRow.length).toBeGreaterThanOrEqual(2); // Parameter input + free-text Value control
    });

    it("a Microscopy value can be entered, submits without being nulled, and does not use structuredValue", async () => {
      const order = microscopyOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const row = screen.getByDisplayValue("Findings").closest(".grid") as HTMLElement;
      const textarea = within(row).getAllByRole("textbox")[1];
      await userEvent.type(textarea, "Gram-positive cocci in clusters");
      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      expect(submitted[0].textValue).toBe("Gram-positive cocci in clusters");
      expect(submitted[0].structuredValue).toBeNull();
    });

    it("a persisted Microscopy value reloads correctly", async () => {
      const order = microscopyOrder({
        results: [
          {
            id: "res-micro", parameterName: "Findings", resultType: "Microscopy", numericValue: null,
            textValue: "No organisms seen", normalRange: null, units: null, interpretation: null, remarks: null,
            rangeLow: null, rangeHigh: null, enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z",
            structuredValue: null, site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("No organisms seen")).toBeInTheDocument());
    });
  });

  describe("Qualitative/Categorical result-entry simplification (HBsAg example)", () => {
    function hbsagOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
      return labOrder({
        testType: "HEPATITIS B ANTIGEN (HBSAG)",
        templateId: "template-hbsag",
        template: {
          id: "template-hbsag", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: "Immunology", specimenType: "Whole Blood",
          defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [
            {
              id: "p-hbsag", parameterName: "HBsAg", unit: null, normalRange: "Negative", resultType: "Categorical",
              displayOrder: 0, rangeLow: null, rangeHigh: null, expectedNormalText: "Negative",
              options: ["Positive", "Negative"],
            },
          ],
        },
        ...overrides,
      });
    }

    it("UI restrictions: Parameter name is a heading, not an editable input", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByText("HBsAg")).toBeInTheDocument();
      expect(screen.queryByPlaceholderText("e.g. Hemoglobin")).not.toBeInTheDocument();
    });

    it("UI restrictions: no Result Type selector is shown", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.queryByDisplayValue("Categorical")).not.toBeInTheDocument();
    });

    it("UI restrictions: Units input is hidden entirely when the parameter has no unit", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.queryByText(/^Unit/)).not.toBeInTheDocument();
      expect(screen.queryByText("Units")).not.toBeInTheDocument();
    });

    it("UI restrictions: Normal Range is a read-only display, not an editable input", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByText("Normal Range: Negative")).toBeInTheDocument();
      expect(screen.queryByDisplayValue("Negative")).not.toBeInTheDocument(); // no editable input holds this value
    });

    it("UI restrictions: Result is a dropdown containing the template-defined options", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "Positive" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Negative" })).toBeInTheDocument();
    });

    it("UI restrictions: Interpretation is not manually selectable (no Interpretation <select>)", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      // The only <select> on this dialog is the Result dropdown itself.
      const selects = screen.getAllByRole("combobox").filter((el) => el.tagName === "SELECT");
      expect(selects).toHaveLength(1);
    });

    it("UI restrictions: Remarks appears exactly once, and the stray Remove control is gone", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getAllByText("Remarks")).toHaveLength(1);
      expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    });

    it("selecting Positive sets Result=Positive and auto-derives Interpretation=Abnormal", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      await userEvent.selectOptions(screen.getByRole("combobox"), "Positive");

      expect(screen.getByDisplayValue("Positive")).toBeInTheDocument();
      expect(screen.getByText("Abnormal")).toBeInTheDocument();
    });

    it("selecting Negative sets Result=Negative and auto-derives Interpretation=Normal, updating immediately on change", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      const select = screen.getByRole("combobox");
      await userEvent.selectOptions(select, "Positive");
      expect(screen.getByText("Abnormal")).toBeInTheDocument();

      await userEvent.selectOptions(select, "Negative");
      expect(screen.getByDisplayValue("Negative")).toBeInTheDocument();
      expect(screen.getByText("✓ Normal")).toBeInTheDocument();
    });

    it("submits the selected value under the template's own parameter name, with the live-computed interpretation (backend recomputes/verifies from the template regardless - see backend tests)", async () => {
      const order = hbsagOrder();
      getOrder.mockResolvedValue(order);
      enterResults.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());

      await userEvent.selectOptions(screen.getByRole("combobox"), "Positive");
      await userEvent.click(screen.getByRole("button", { name: /save results/i }));

      await waitFor(() => expect(enterResults).toHaveBeenCalled());
      const [, submitted] = enterResults.mock.calls[enterResults.mock.calls.length - 1] as [string, Array<Record<string, unknown>>];
      expect(submitted[0].parameterName).toBe("HBsAg");
      expect(submitted[0].structuredValue).toEqual({ value: "Positive" });
      expect(submitted[0].interpretation).toBe("Abnormal");
    });

    it("a saved Positive result reloads with Interpretation shown as Abnormal", async () => {
      const order = hbsagOrder({
        results: [
          {
            id: "res-hbsag", parameterName: "HBsAg", resultType: "Categorical", numericValue: null, textValue: null,
            normalRange: "Negative", units: null, interpretation: "Abnormal", remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: { value: "Positive" }, site: null,
          },
        ],
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByDisplayValue("Positive")).toBeInTheDocument());
      expect(screen.getByText("Abnormal")).toBeInTheDocument();
    });

    it("an options-less Categorical parameter (production-realistic, no admin configuration yet) keeps the full grid, not the simplified layout", async () => {
      const order = hbsagOrder({
        template: {
          ...hbsagOrder().template!,
          parameters: [{ ...hbsagOrder().template!.parameters[0], options: null, expectedNormalText: null, normalRange: null }],
        },
      });
      getOrder.mockResolvedValue(order);
      renderWithClient(<ResultEntryDialog order={order} open onOpenChange={() => {}} />);
      await waitFor(() => expect(getOrder).toHaveBeenCalled());
      expect(screen.getByRole("option", { name: "No options configured" })).toBeInTheDocument();
      expect(screen.getByDisplayValue("HBsAg")).toBeInTheDocument(); // Parameter input still editable in the fallback grid
    });
  });
});
