import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PrescriptionTab } from "./PrescriptionTab";
import type { Prescription } from "@/features/clinical-orders/types";

const mockPrescription: Prescription = {
  id: "rx-1",
  consultationId: "consult-1",
  visitId: "visit-1",
  patientId: "patient-1",
  doctorId: "doctor-1",
  prescriptionNumber: "RX-20260101-000001",
  status: "Finalized",
  createdAt: "2026-01-01T00:00:00Z",
  items: [
    {
      id: "item-1",
      medicine: "Amoxicillin",
      strength: "500mg",
      dosage: "1 tab",
      frequency: "TID",
      duration: "7 days",
      quantity: "21 tabs",
      route: "Oral",
      instructions: null,
      substitutionAllowed: true,
    },
  ],
};

const mockCreateMutate = vi.fn();
vi.mock("@/features/clinical-orders/hooks/use-clinical-orders", () => ({
  usePrescriptionsForConsultation: () => ({ data: [mockPrescription], isLoading: false }),
  useCreatePrescription: () => ({ mutate: mockCreateMutate, isPending: false }),
}));

// Task #8: Medicine catalog source - GET /medicines (the same real
// inventory endpoint the Medicines admin page uses via `createCrudHooks`),
// NOT the removed `COMMON_MEDICINES` hardcoded array. `/clinic-settings` is
// unrelated (used for the print header) and stays a generic empty-object
// mock like before.
const MOCK_MEDICINES = [
  { id: "med-1", generic_name: "Amoxicillin", brand_name: "Amoxil", strength: "500mg", dosage_form: "Capsule", is_active: true },
  { id: "med-2", generic_name: "Amoxicillin", brand_name: null, strength: "250mg", dosage_form: "Capsule", is_active: true },
  { id: "med-3", generic_name: "Paracetamol", brand_name: "Biogesic", strength: "500mg", dosage_form: "Tablet", is_active: true },
];
const mockApiGet = vi.fn((url: string) => {
  if (url.startsWith("/medicines")) return Promise.resolve({ items: MOCK_MEDICINES, total: MOCK_MEDICINES.length });
  return Promise.resolve({});
});
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...args: [string]) => mockApiGet(...args) },
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("PrescriptionTab print output", () => {
  it("prints the doctor's PRC license and PTR number directly below the doctor's name", async () => {
    renderWithClient(
      <PrescriptionTab
        consultationId="consult-1"
        visitId="visit-1"
        canEdit={false}
        doctorName="Jose Rizal"
        doctorPrcLicense="0123456"
        doctorPtrNumber="9876543"
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /print/i }));

    const signatureBlock = screen.getByTestId("prescription-signature-block");
    expect(signatureBlock).toHaveTextContent("Dr. Jose Rizal");
    expect(signatureBlock).toHaveTextContent("PRC License No. 0123456");
    expect(signatureBlock).toHaveTextContent("PTR No. 9876543");
  });

  it("omits PRC/PTR lines when the doctor record has none on file", async () => {
    renderWithClient(
      <PrescriptionTab consultationId="consult-1" visitId="visit-1" canEdit={false} doctorName="Jose Rizal" />
    );

    await userEvent.click(screen.getByRole("button", { name: /print/i }));

    const signatureBlock = screen.getByTestId("prescription-signature-block");
    expect(signatureBlock).not.toHaveTextContent("PRC License No.");
    expect(signatureBlock).not.toHaveTextContent("PTR No.");
  });
});

// Task #8: Prescription searchable dropdowns/autocomplete.
describe("PrescriptionTab - searchable dropdowns/autocomplete (Task #8)", () => {
  beforeEach(() => {
    mockApiGet.mockClear();
    mockCreateMutate.mockClear();
  });

  function renderEditable() {
    return renderWithClient(
      <PrescriptionTab consultationId="consult-1" visitId="visit-1" canEdit={true} doctorName="Jose Rizal" patientId="patient-1" />
    );
  }

  it("1: the prescription page renders correctly, including the existing (historical) prescription and an editable first row", () => {
    renderEditable();
    expect(screen.getByText("RX-20260101-000001")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search medicine…")).toBeInTheDocument();
  });

  it("2: medicine search loads from the real Medicine catalog (GET /medicines), not the removed hardcoded list", async () => {
    const user = userEvent.setup();
    renderEditable();
    await user.click(screen.getByPlaceholderText("Search medicine…"));
    await user.type(screen.getByPlaceholderText("Search medicine…"), "Amox");
    await screen.findByRole("button", { name: /Amoxicillin \(Amoxil\) — 500mg/ });
    expect(mockApiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/medicines\?/));
  });

  it("3: medicine search/filter narrows to matching results as the doctor types", async () => {
    const user = userEvent.setup();
    renderEditable();
    await user.click(screen.getByPlaceholderText("Search medicine…"));
    await user.type(screen.getByPlaceholderText("Search medicine…"), "Amox");
    expect(await screen.findByRole("button", { name: /Amoxicillin \(Amoxil\) — 500mg/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Amoxicillin — 250mg/ })).toBeInTheDocument();
  });

  it("4 & 5: selecting a medicine fills medicine name and auto-fills its strength from the catalog record", async () => {
    const user = userEvent.setup();
    renderEditable();
    await user.click(screen.getByPlaceholderText("Search medicine…"));
    await user.type(screen.getByPlaceholderText("Search medicine…"), "Amox");
    await user.click(await screen.findByRole("button", { name: /Amoxicillin \(Amoxil\) — 500mg/ }));

    expect(screen.getByPlaceholderText("Search medicine…")).toHaveValue("Amoxicillin");
    expect(screen.getByPlaceholderText("e.g. 500mg")).toHaveValue("500mg");
  });

  it("10: selecting a medicine also auto-fills Form from the catalog record's dosage_form", async () => {
    const user = userEvent.setup();
    renderEditable();
    await user.click(screen.getByPlaceholderText("Search medicine…"));
    await user.type(screen.getByPlaceholderText("Search medicine…"), "Amox");
    await user.click(await screen.findByRole("button", { name: /Amoxicillin \(Amoxil\) — 500mg/ }));

    expect(screen.getByPlaceholderText("e.g. Tablet")).toHaveValue("Capsule");
  });

  it("6: Dosage shows suggestions from the shared vocabulary, without restricting free text", async () => {
    const user = userEvent.setup();
    renderEditable();
    const dosageLabel = screen.getByText("Dosage");
    const input = dosageLabel.parentElement?.querySelector("input") as HTMLInputElement;
    await user.click(input);
    expect(await screen.findByRole("button", { name: "1 tablet" })).toBeInTheDocument();
  });

  it("7: Frequency shows suggestions from the shared vocabulary", async () => {
    const user = userEvent.setup();
    renderEditable();
    const label = screen.getByText("Frequency");
    const input = label.parentElement?.querySelector("input") as HTMLInputElement;
    await user.click(input);
    expect(await screen.findByRole("button", { name: "Once daily" })).toBeInTheDocument();
  });

  it("8: Route shows suggestions from the shared vocabulary", async () => {
    const user = userEvent.setup();
    renderEditable();
    const label = screen.getByText("Route");
    const input = label.parentElement?.querySelector("input") as HTMLInputElement;
    await user.click(input);
    expect(await screen.findByRole("button", { name: "Oral" })).toBeInTheDocument();
  });

  it("9: Duration shows suggestions from the shared vocabulary", async () => {
    const user = userEvent.setup();
    renderEditable();
    const label = screen.getByText("Duration");
    const input = label.parentElement?.querySelector("input") as HTMLInputElement;
    await user.click(input);
    expect(await screen.findByRole("button", { name: "7 days" })).toBeInTheDocument();
  });

  it("11: a custom/free-text value not in any suggestion list is still accepted", async () => {
    const user = userEvent.setup();
    renderEditable();
    const label = screen.getByText("Frequency");
    const input = label.parentElement?.querySelector("input") as HTMLInputElement;
    await user.type(input, "Every other day as tolerated");
    expect(input).toHaveValue("Every other day as tolerated");
  });

  it("12: existing prescription creation still works - Save Prescription submits the filled item, including the new dosageForm field", async () => {
    const user = userEvent.setup();
    renderEditable();
    await user.click(screen.getByPlaceholderText("Search medicine…"));
    await user.type(screen.getByPlaceholderText("Search medicine…"), "Amox");
    await user.click(await screen.findByRole("button", { name: /Amoxicillin \(Amoxil\) — 500mg/ }));

    await user.click(screen.getByRole("button", { name: "Save Prescription" }));

    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    const submitted = mockCreateMutate.mock.calls[0][0];
    expect(submitted).toHaveLength(1);
    expect(submitted[0]).toMatchObject({ medicine: "Amoxicillin", strength: "500mg", dosageForm: "Capsule" });
  });

  it("13, 15 & 16: editing one prescription item (pre-submission) does not alter another - multiple items remain independent", async () => {
    const user = userEvent.setup();
    renderEditable();

    await user.click(screen.getByRole("button", { name: "+ Add another medicine" }));
    const medicineInputs = screen.getAllByPlaceholderText("Search medicine…");
    expect(medicineInputs).toHaveLength(2);

    await user.type(medicineInputs[0], "Row One Medicine");
    await user.type(medicineInputs[1], "Row Two Medicine");

    expect(medicineInputs[0]).toHaveValue("Row One Medicine");
    expect(medicineInputs[1]).toHaveValue("Row Two Medicine");

    const strengthInputs = screen.getAllByPlaceholderText("e.g. 500mg");
    await user.type(strengthInputs[0], "111mg");
    expect(strengthInputs[0]).toHaveValue("111mg");
    expect(strengthInputs[1]).toHaveValue("");
  });

  it("14: an existing (historical) prescription item with no dosageForm on file renders cleanly, no 'null'/'undefined'", () => {
    renderEditable();
    const historyCard = screen.getByText("RX-20260101-000001").closest("li") as HTMLElement;
    expect(historyCard).toHaveTextContent("Amoxicillin");
    expect(historyCard).toHaveTextContent("500mg");
    expect(historyCard).not.toHaveTextContent("null");
    expect(historyCard).not.toHaveTextContent("undefined");
  });

  it("17: the Doctor role (canEdit=true) can use the new controls", () => {
    renderEditable();
    expect(screen.getByPlaceholderText("Search medicine…")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save Prescription" })).toBeInTheDocument();
  });

  it("18: a role without edit access (canEdit=false) does not gain the create/edit controls - unchanged existing gating", () => {
    renderWithClient(
      <PrescriptionTab consultationId="consult-1" visitId="visit-1" canEdit={false} doctorName="Jose Rizal" />
    );
    expect(screen.queryByPlaceholderText("Search medicine…")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Prescription" })).not.toBeInTheDocument();
  });
});
