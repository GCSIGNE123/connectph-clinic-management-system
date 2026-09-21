import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClinicalOrdersTab } from "./ClinicalOrdersTab";
import type { Order, Procedure, Referral } from "@/features/clinical-orders/types";

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

const mockFetchBlob = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn().mockResolvedValue({ license_number: "CLINIC-LIC-1" }) },
  apiFetchBlob: (...args: unknown[]) => mockFetchBlob(...args),
}));

let mockOrders: Order[] = [];
let mockProcedures: Procedure[] = [];
let mockReferrals: Referral[] = [];
const mockCreateOrderMutate = vi.fn();
vi.mock("@/features/clinical-orders/hooks/use-clinical-orders", () => ({
  useOrdersForConsultation: () => ({ data: mockOrders, isLoading: false }),
  useProceduresForConsultation: () => ({ data: mockProcedures, isLoading: false }),
  useReferralsForConsultation: () => ({ data: mockReferrals, isLoading: false }),
  useCreateOrder: () => ({ mutate: mockCreateOrderMutate, isPending: false }),
  useUpdateOrderStatus: () => ({ mutate: vi.fn() }),
  useCreateProcedure: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateReferral: () => ({ mutate: vi.fn(), isPending: false }),
}));

// Task #3: the Laboratory catalog picker's authoritative source - see
// ClinicalOrdersTab's own module note on why this is Laboratory Templates,
// not the Services catalog.
const mockLabTemplates = [
  { id: "tpl-cbc", testName: "CBC", testCategory: "Hematology", specimenType: "Whole Blood", defaultPrice: 350, turnaroundTimeHours: 4, isActive: true, parameters: [], createdAt: "2026-08-19T00:00:00Z" },
  { id: "tpl-uri", testName: "Urinalysis", testCategory: "Chemistry", specimenType: "Urine", defaultPrice: 100, turnaroundTimeHours: 2, isActive: true, parameters: [], createdAt: "2026-08-19T00:00:00Z" },
  { id: "tpl-fbs", testName: "FBS", testCategory: "Chemistry", specimenType: "Blood", defaultPrice: 80, turnaroundTimeHours: 2, isActive: true, parameters: [], createdAt: "2026-08-19T00:00:00Z" },
];
vi.mock("@/features/laboratory/hooks/use-laboratory", () => ({
  useLaboratoryTemplates: () => ({ data: mockLabTemplates, isLoading: false }),
}));

function buildOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-1", consultationId: "consult-1", visitId: "visit-1", patientId: "patient-1",
    doctorId: "doctor-1", orderNumber: "ORD-000001", orderCategory: "Laboratory", priority: "Routine",
    status: "Requested", createdAt: "2026-08-19T00:00:00Z",
    items: [{ id: "item-1", itemName: "CBC" }],
    ...overrides,
  };
}

function buildProcedure(overrides: Partial<Procedure> = {}): Procedure {
  return {
    id: "proc-1", consultationId: "consult-1", visitId: "visit-1",
    doctorId: "doctor-1", procedureName: "Wound Dressing", status: "Requested",
    createdAt: "2026-08-19T00:00:00Z",
    ...overrides,
  };
}

function buildReferral(overrides: Partial<Referral> = {}): Referral {
  return {
    id: "ref-1", consultationId: "consult-1", visitId: "visit-1", doctorId: "doctor-1",
    referredTo: "Dr. Cardio Specialist", status: "Requested", createdAt: "2026-08-19T00:00:00Z",
    doctorSignatureSnapshotUrl: "snap.png",
    ...overrides,
  };
}

function renderTab(props: Partial<React.ComponentProps<typeof ClinicalOrdersTab>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ClinicalOrdersTab
        consultationId="consult-1"
        visitId="visit-1"
        canEdit={false}
        patientName="Juan Dela Cruz"
        doctorName="Jose Rizal"
        doctorPrcLicense="PRC-1"
        doctorPtrNumber="PTR-1"
        visitNumber="VIS-000001"
        {...props}
      />
    </QueryClientProvider>
  );
}

describe("ClinicalOrdersTab - doctor signature block on print", () => {
  it("A: Order print includes the signature image above doctor name, PRC, and PTR", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    mockOrders = [buildOrder()];
    mockProcedures = [];
    mockReferrals = [];
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/doctors/doctor-1/signature/file"));
    const block = screen.getByTestId("order-signature-block");
    const img = await screen.findByAltText("Doctor signature");
    expect(block.contains(img)).toBe(true);
    // Visual order: image, then name, then PRC, then PTR.
    const order = [...block.querySelectorAll("img, br")].length;
    expect(order).toBeGreaterThan(0);
    expect(block).toHaveTextContent(/Dr\. Jose Rizal/);
    expect(block).toHaveTextContent(/PRC License No\. PRC-1/);
    expect(block).toHaveTextContent(/PTR No\. PTR-1/);
    const html = block.innerHTML;
    expect(html.indexOf("<img")).toBeLessThan(html.indexOf("Dr. Jose Rizal"));
    expect(html.indexOf("Dr. Jose Rizal")).toBeLessThan(html.indexOf("PRC License No"));
    expect(html.indexOf("PRC License No")).toBeLessThan(html.indexOf("PTR No"));
  });

  it("B: Procedure print includes the same signature block", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    mockOrders = [];
    mockProcedures = [buildProcedure()];
    mockReferrals = [];
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/doctors/doctor-1/signature/file"));
    const block = screen.getByTestId("procedure-signature-block");
    expect(await screen.findByAltText("Doctor signature")).toBeInTheDocument();
    expect(block).toHaveTextContent(/Dr\. Jose Rizal/);
    expect(block).toHaveTextContent(/PRC License No\. PRC-1/);
    expect(block).toHaveTextContent(/PTR No\. PTR-1/);
  });

  it("C: Referral print includes the signature block, using its own document snapshot endpoint", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    mockOrders = [];
    mockProcedures = [];
    mockReferrals = [buildReferral()];
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/referrals/ref-1/signature/file"));
    const block = screen.getByTestId("referral-signature-block");
    expect(await screen.findByAltText("Doctor signature")).toBeInTheDocument();
    expect(block).toHaveTextContent(/Dr\. Jose Rizal/);
  });

  it("G: Referral print uses the referral's snapshot file, not the doctor's live signature endpoint", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    mockOrders = [];
    mockProcedures = [];
    mockReferrals = [buildReferral({ id: "ref-2", doctorSignatureSnapshotUrl: "snap-2.png" })];
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/referrals/ref-2/signature/file"));
    expect(mockFetchBlob).not.toHaveBeenCalledWith(expect.stringContaining("/doctors/"));
  });

  it("A2: every printable Order category (Laboratory, Radiology, Vaccination, Custom) shows a Print button and opens with its own signature block", async () => {
    mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
    mockOrders = [
      buildOrder({ id: "o-lab", orderCategory: "Laboratory" }),
      buildOrder({ id: "o-rad", orderCategory: "Radiology" }),
      buildOrder({ id: "o-vac", orderCategory: "Vaccination" }),
      buildOrder({ id: "o-cus", orderCategory: "Custom" }),
    ];
    mockProcedures = [];
    mockReferrals = [];
    const user = userEvent.setup();
    renderTab();

    const printButtons = screen.getAllByRole("button", { name: "Print" });
    expect(printButtons).toHaveLength(4);

    for (const btn of printButtons) {
      await user.click(btn);
      const block = await screen.findByTestId("order-signature-block");
      expect(block).toHaveTextContent(/Dr\. Jose Rizal/);
      await user.click(screen.getByRole("button", { name: "Close" }));
    }
  });

  it("D: Order still prints with a blank signature area, name/PRC/PTR remain visible, when doctor has no signature", async () => {
    mockFetchBlob.mockReset();
    mockOrders = [buildOrder({ doctorId: null })];
    mockProcedures = [];
    mockReferrals = [];
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    expect(mockFetchBlob).not.toHaveBeenCalled();
    const block = screen.getByTestId("order-signature-block");
    expect(screen.queryByAltText("Doctor signature")).not.toBeInTheDocument();
    expect(block).toHaveTextContent(/Dr\. Jose Rizal/);
    expect(block).toHaveTextContent(/PRC License No\. PRC-1/);
    expect(block).toHaveTextContent(/PTR No\. PTR-1/);
  });

  it("E: missing PRC/PTR lines are omitted (not fabricated) on Order print", async () => {
    mockFetchBlob.mockReset();
    mockOrders = [buildOrder({ doctorId: null })];
    mockProcedures = [];
    mockReferrals = [];
    const user = userEvent.setup();
    renderTab({ doctorPrcLicense: null, doctorPtrNumber: null });

    await user.click(screen.getByRole("button", { name: "Print" }));

    const block = screen.getByTestId("order-signature-block");
    expect(block).not.toHaveTextContent(/PRC License No\./);
    expect(block).not.toHaveTextContent(/PTR No\./);
  });
});

describe("ClinicalOrdersTab - Doctor Workspace Configuration (Lab Requests toggle)", () => {
  it("shows Laboratory as a selectable category by default", () => {
    mockOrders = [];
    mockProcedures = [];
    mockReferrals = [];
    renderTab({ canEdit: true });
    expect(screen.getByRole("option", { name: "Laboratory" })).toBeInTheDocument();
  });

  it("hides Laboratory from the category dropdown when hideLaboratoryOption is set, without removing Radiology/Vaccination/Custom", () => {
    mockOrders = [];
    mockProcedures = [];
    mockReferrals = [];
    renderTab({ canEdit: true, hideLaboratoryOption: true });
    expect(screen.queryByRole("option", { name: "Laboratory" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Radiology" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Vaccination" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Custom" })).toBeInTheDocument();
  });
});

// Task #3: Laboratory Requests searchable multi-select, replacing the old
// single free-text "Item / test name" field for the Laboratory category
// only. Options come from `useLaboratoryTemplates` (mocked above) - CBC,
// Urinalysis, FBS - matching the client's exact acceptance scenario.
describe("ClinicalOrdersTab - Laboratory Requests searchable multi-select (Task #3)", () => {
  beforeEach(() => {
    mockCreateOrderMutate.mockReset();
    mockOrders = [];
    mockProcedures = [];
    mockReferrals = [];
  });

  function labSearchInput() {
    return screen.getByPlaceholderText("Search laboratory test…");
  }

  it("1: loads the laboratory catalog (from Laboratory Templates) for the Doctor role and shows it on search", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    expect(screen.getByRole("button", { name: "CBC" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Urinalysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "FBS" })).toBeInTheDocument();
  });

  it("2: search filters the catalog by typed text", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    await user.type(labSearchInput(), "uri");
    expect(screen.getByRole("button", { name: "Urinalysis" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "CBC" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "FBS" })).not.toBeInTheDocument();
  });

  it("3: doctor can select one lab item, which appears in the selected list", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    await user.click(screen.getByRole("button", { name: "CBC" }));
    expect(screen.getByText("CBC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("4: doctor can select multiple lab items (CBC, Urinalysis, FBS)", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    for (const name of ["CBC", "Urinalysis", "FBS"]) {
      await user.click(labSearchInput());
      await user.click(screen.getByRole("button", { name }));
    }
    const selectedRows = screen.getAllByRole("button", { name: "Remove" });
    expect(selectedRows).toHaveLength(3);
  });

  it("5: the same test cannot be selected twice - it drops out of the searchable options once selected", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    await user.click(screen.getByRole("button", { name: "CBC" }));
    await user.click(labSearchInput());
    expect(screen.queryByRole("button", { name: "CBC" })).not.toBeInTheDocument();
    // Still selected exactly once, not duplicated.
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(1);
  });

  it("6: doctor can remove a selected item before submission, and it becomes selectable again", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    await user.click(screen.getByRole("button", { name: "CBC" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    await user.click(labSearchInput());
    expect(screen.getByRole("button", { name: "CBC" })).toBeInTheDocument();
  });

  it("7 & 8: submitting once with CBC + Urinalysis + FBS selected sends ONE createOrder call with three OrderItems, not three separate Orders", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    for (const name of ["CBC", "Urinalysis", "FBS"]) {
      await user.click(labSearchInput());
      await user.click(screen.getByRole("button", { name }));
    }
    await user.click(screen.getByRole("button", { name: "Create Order" }));

    expect(mockCreateOrderMutate).toHaveBeenCalledTimes(1);
    const payload = mockCreateOrderMutate.mock.calls[0][0];
    expect(payload.orderCategory).toBe("Laboratory");
    expect(payload.items).toEqual([{ itemName: "CBC" }, { itemName: "Urinalysis" }, { itemName: "FBS" }]);
  });

  it("10: a single laboratory request still works (existing single-item behavior unchanged)", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    await user.click(labSearchInput());
    await user.click(screen.getByRole("button", { name: "CBC" }));
    await user.click(screen.getByRole("button", { name: "Create Order" }));

    expect(mockCreateOrderMutate).toHaveBeenCalledTimes(1);
    expect(mockCreateOrderMutate.mock.calls[0][0].items).toEqual([{ itemName: "CBC" }]);
  });

  it("11: Create Order is disabled with nothing selected, and Radiology's free-text single-item flow is unaffected", async () => {
    const user = userEvent.setup();
    renderTab({ canEdit: true });
    expect(screen.getByRole("button", { name: "Create Order" })).toBeDisabled();

    await user.selectOptions(screen.getByDisplayValue("Laboratory"), "Radiology");
    // Laboratory's searchable picker is gone; the old free-text field is back.
    expect(screen.queryByPlaceholderText("Search laboratory test…")).not.toBeInTheDocument();
    const itemInput = screen.getByPlaceholderText("e.g. Chest X-Ray");
    await user.type(itemInput, "Chest X-Ray");
    await user.click(screen.getByRole("button", { name: "Create Order" }));

    expect(mockCreateOrderMutate).toHaveBeenCalledTimes(1);
    const payload = mockCreateOrderMutate.mock.calls[0][0];
    expect(payload.orderCategory).toBe("Radiology");
    expect(payload.items).toEqual([{ itemName: "Chest X-Ray", examType: null, bodyPart: null, clinicalIndication: null }]);
  });

  it("12: create controls remain hidden entirely when canEdit is false (existing role/permission gating unchanged)", () => {
    renderTab({ canEdit: false });
    expect(screen.queryByPlaceholderText("Search laboratory test…")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Order" })).not.toBeInTheDocument();
  });
});
