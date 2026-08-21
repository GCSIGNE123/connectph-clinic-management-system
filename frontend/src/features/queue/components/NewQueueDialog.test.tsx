import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NewQueueDialog } from "./NewQueueDialog";

// `Label`/`Select` in this codebase are plain sibling elements (no
// `htmlFor`/`id` association - see `components/ui/label.tsx` and
// `select.tsx`), so `getByLabelText` doesn't work here. Every field is a
// `<div class="space-y-1.5"><Label/><Select/></div>` - scope by the label's
// parent instead, same fix `EditQueueDialog.test.tsx` uses (`getAllByRole`
// there; this is the label-scoped equivalent so field order doesn't matter,
// which matters here since the Doctor field is conditionally hidden).
function getSelectByLabel(labelText: string): HTMLElement {
  const label = screen.getByText(labelText, { selector: "label" });
  return within(label.parentElement as HTMLElement).getByRole("combobox");
}

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: (path: string) => ({
    list: () => {
      if (path === "/departments") {
        return Promise.resolve({
          items: [
            { id: "dept-lab", name: "Laboratory" },
            { id: "dept-med", name: "Internal Medicine" },
          ],
        });
      }
      if (path === "/doctors") {
        return Promise.resolve({ items: [{ id: "doc-1", first_name: "Jose", last_name: "Rizal", department_id: null }] });
      }
      if (path === "/services") {
        return Promise.resolve({
          items: [
            { id: "svc-lab", service_name: "BLOOD CHEMISTRY", name: "BLOOD CHEMISTRY", service_code: "BLDCHEM" },
            { id: "svc-med", service_name: "Consultation - Follow-up Visit", name: "Follow-up", service_code: "OTHER" },
          ],
        });
      }
      if (path === "/branches") {
        return Promise.resolve({ items: [{ id: "branch-1", name: "Main Branch" }] });
      }
      return Promise.resolve({ items: [] });
    },
  }),
}));

vi.mock("@/features/patients/api/patients-api", () => ({
  patientsApi: {
    list: () =>
      Promise.resolve({
        data: [{ id: "pat-1", firstName: "Juan", lastName: "Dela Cruz", patientNumber: "PAT-001", isYakapBeneficiary: false }],
        meta: { page: 1, pageSize: 8, total: 1, totalPages: 1 },
      }),
  },
}));

const mockCreatePatientMutateAsync = vi.fn();
vi.mock("@/features/patients/hooks/use-patient-mutations", () => ({
  useCreatePatient: () => ({ mutateAsync: mockCreatePatientMutateAsync, isPending: false }),
}));

const mockCreatePreQueue = vi.fn();
vi.mock("@/features/visits/api/visits-api", () => ({
  visitsApi: {
    createPreQueue: (...args: unknown[]) => mockCreatePreQueue(...args),
  },
}));

const mockCreateQueueMutateAsync = vi.fn();
vi.mock("@/features/queue/hooks/use-queue-mutations", () => ({
  useCreateQueue: () => ({ mutateAsync: mockCreateQueueMutateAsync, isPending: false }),
}));

// `LabPaymentStep` (invoice creation + real `PaymentDialog`) is covered by
// its own dedicated test file - stubbed here so these tests isolate
// `NewQueueDialog`'s own orchestration: does it hide the doctor field, does
// it gate the submit button, does it only create the queue after `onPaid`
// fires, does cancelling avoid creating a queue.
let lastLabPaymentStepProps: { onPaid: (invoiceId: string) => void; onBack: () => void } | null = null;
vi.mock("@/features/queue/components/LabPaymentStep", () => ({
  LabPaymentStep: (props: { visitId: string; onPaid: (invoiceId: string) => void; onBack: () => void }) => {
    lastLabPaymentStepProps = props;
    return (
      <div data-testid="lab-payment-step">
        <button type="button" onClick={() => props.onPaid("invoice-1")}>
          Simulate Paid
        </button>
        <button type="button" onClick={props.onBack}>
          Simulate Cancel
        </button>
      </div>
    );
  },
}));

function renderDialog(onCreated = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NewQueueDialog open onOpenChange={vi.fn()} onCreated={onCreated} />
    </QueryClientProvider>
  );
}

async function selectPatient(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByPlaceholderText(/search by name/i), "Juan");
  const match = await screen.findByText("Juan Dela Cruz");
  await user.click(match);
}

async function fillBranchAndService(user: ReturnType<typeof userEvent.setup>, serviceLabel: string) {
  await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
  await user.selectOptions(getSelectByLabel("Branch"), "branch-1");
  // SearchableSelect - open then click the matching option.
  await user.click(screen.getByPlaceholderText(/select service/i));
  const option = await screen.findByText(serviceLabel);
  await user.click(option);
}

describe("NewQueueDialog", () => {
  it("A: non-Laboratory department keeps the existing single-step flow (doctor field shown, submits directly)", async () => {
    mockCreateQueueMutateAsync.mockReset().mockResolvedValue({ id: "queue-1", queueNumber: "A001" });
    const user = userEvent.setup();
    const onCreated = vi.fn();
    renderDialog(onCreated);

    await selectPatient(user);
    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-med");
    await fillBranchAndService(user, "Consultation - Follow-up Visit");

    // Doctor field is present (optional) for a non-Laboratory department.
    expect(screen.getByText(/Doctor \(optional\)/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create Queue Ticket" }));

    await waitFor(() => expect(mockCreateQueueMutateAsync).toHaveBeenCalled());
    const payload = mockCreateQueueMutateAsync.mock.calls[0][0];
    expect(payload.departmentId).toBe("dept-med");
    expect(payload.visitId).toBeNull();
    expect(mockCreatePreQueue).not.toHaveBeenCalled();
    expect(onCreated).toHaveBeenCalledWith("queue-1");
  });

  it("B: selecting the Laboratory department switches the flow to pay-first (hides doctor, changes the button)", async () => {
    const user = userEvent.setup();
    renderDialog();

    await selectPatient(user);
    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-lab");

    expect(screen.queryByText(/^Doctor/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Proceed to Payment" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create Queue Ticket" })).not.toBeInTheDocument();
  });

  it("D: successful payment (LabPaymentStep firing onPaid) creates the queue with the draft visit's id and no doctor", async () => {
    mockCreatePreQueue.mockReset().mockResolvedValue({
      id: "visit-1", serviceId: "svc-lab", patientId: "pat-1", departmentId: "dept-lab", doctorId: null,
    });
    mockCreateQueueMutateAsync.mockReset().mockResolvedValue({ id: "queue-2", queueNumber: "L001" });
    const user = userEvent.setup();
    const onCreated = vi.fn();
    renderDialog(onCreated);

    await selectPatient(user);
    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
    await fillBranchAndService(user, "BLOOD CHEMISTRY");

    await user.click(screen.getByRole("button", { name: "Proceed to Payment" }));

    await waitFor(() => expect(mockCreatePreQueue).toHaveBeenCalledTimes(1));
    expect(mockCreatePreQueue.mock.calls[0][0]).toMatchObject({ doctorId: null, departmentId: "dept-lab", serviceId: "svc-lab" });

    expect(await screen.findByTestId("lab-payment-step")).toBeInTheDocument();
    expect(mockCreateQueueMutateAsync).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Simulate Paid" }));

    await waitFor(() => expect(mockCreateQueueMutateAsync).toHaveBeenCalledTimes(1));
    const payload = mockCreateQueueMutateAsync.mock.calls[0][0];
    expect(payload.visitId).toBe("visit-1");
    expect(payload.doctorId).toBeNull();
    expect(payload.departmentId).toBe("dept-lab");
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("queue-2"));
  });

  it("E: cancelling out of the Laboratory payment step never creates a queue ticket", async () => {
    mockCreatePreQueue.mockReset().mockResolvedValue({
      id: "visit-2", serviceId: "svc-lab", patientId: "pat-1", departmentId: "dept-lab", doctorId: null,
    });
    mockCreateQueueMutateAsync.mockReset();
    const user = userEvent.setup();
    renderDialog();

    await selectPatient(user);
    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
    await fillBranchAndService(user, "BLOOD CHEMISTRY");
    await user.click(screen.getByRole("button", { name: "Proceed to Payment" }));

    expect(await screen.findByTestId("lab-payment-step")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Simulate Cancel" }));

    // Back at the form step - no queue was ever created.
    await waitFor(() => expect(screen.getByRole("button", { name: "Proceed to Payment" })).toBeInTheDocument());
    expect(mockCreateQueueMutateAsync).not.toHaveBeenCalled();
    expect(lastLabPaymentStepProps).not.toBeNull();
  });

  it("F: the Laboratory queue is created without a doctor even if a stray doctorId were present", async () => {
    mockCreatePreQueue.mockReset().mockResolvedValue({
      id: "visit-3", serviceId: "svc-lab", patientId: "pat-1", departmentId: "dept-lab", doctorId: null,
    });
    mockCreateQueueMutateAsync.mockReset().mockResolvedValue({ id: "queue-3", queueNumber: "L002" });
    const user = userEvent.setup();
    renderDialog();

    await selectPatient(user);
    await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
    await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
    await fillBranchAndService(user, "BLOOD CHEMISTRY");
    await user.click(screen.getByRole("button", { name: "Proceed to Payment" }));
    expect(await screen.findByTestId("lab-payment-step")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Simulate Paid" }));

    await waitFor(() => expect(mockCreateQueueMutateAsync).toHaveBeenCalled());
    expect(mockCreateQueueMutateAsync.mock.calls[0][0].doctorId).toBeNull();
  });

  describe("inline Create New Patient form (address field)", () => {
    // `Label`/`Input` here are plain sibling elements too (same reasoning
    // as `getSelectByLabel` above) - scope by the label's parent and grab
    // the input inside it directly, so this works for the `type="date"`
    // Birth date field too (which isn't exposed with an ARIA `textbox` role
    // in jsdom, unlike plain text inputs).
    function getFieldByLabel(labelText: string): HTMLInputElement {
      const label = screen.getByText(labelText, { selector: "label" });
      return (label.parentElement as HTMLElement).querySelector("input") as HTMLInputElement;
    }

    async function openInlineForm(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByRole("button", { name: "+ Create new patient" }));
      await screen.findByText("Create New Patient");
    }

    async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
      await user.type(getFieldByLabel("First name"), "New");
      await user.type(getFieldByLabel("Last name"), "Patient");
      await user.type(getFieldByLabel("Birth date"), "1990-01-01");
      await user.type(getFieldByLabel("Mobile number"), "+639171234567");
    }

    it("G: displays an Address field", async () => {
      const user = userEvent.setup();
      renderDialog();

      await openInlineForm(user);
      expect(getFieldByLabel("Address")).toBeInTheDocument();
    });

    it("H: entering an address submits it to patient creation", async () => {
      mockCreatePatientMutateAsync.mockReset().mockResolvedValue({
        patient: { id: "pat-new", firstName: "New", lastName: "Patient", patientNumber: "PAT-002" },
        duplicates: [],
      });
      const user = userEvent.setup();
      renderDialog();

      await openInlineForm(user);
      await user.type(getFieldByLabel("Address"), "123 Rizal St., Brgy. San Jose");
      await fillRequiredFields(user);
      await user.click(screen.getByRole("button", { name: "Create & Select" }));

      await waitFor(() => expect(mockCreatePatientMutateAsync).toHaveBeenCalled());
      expect(mockCreatePatientMutateAsync.mock.calls[0][0].input).toMatchObject({
        addressLine: "123 Rizal St., Brgy. San Jose",
      });
    });

    it("I: address is blank by default and creation still works with a blank address", async () => {
      mockCreatePatientMutateAsync.mockReset().mockResolvedValue({
        patient: { id: "pat-new2", firstName: "No", lastName: "Address", patientNumber: "PAT-003" },
        duplicates: [],
      });
      const user = userEvent.setup();
      renderDialog();

      await openInlineForm(user);
      expect(getFieldByLabel("Address").value).toBe("");
      await fillRequiredFields(user);
      await user.click(screen.getByRole("button", { name: "Create & Select" }));

      await waitFor(() => expect(mockCreatePatientMutateAsync).toHaveBeenCalled());
      expect(mockCreatePatientMutateAsync.mock.calls[0][0].input).toMatchObject({ addressLine: "" });
    });

    it("J: the address value is retained in the form while typing (not cleared mid-entry)", async () => {
      const user = userEvent.setup();
      renderDialog();

      await openInlineForm(user);
      const addressInput = getFieldByLabel("Address");
      await user.type(addressInput, "456 Bonifacio Ave.");

      expect(addressInput.value).toBe("456 Bonifacio Ave.");
    });

    it("K: existing required-field gating and patient-selection behavior remain unchanged", async () => {
      const user = userEvent.setup();
      renderDialog();

      await openInlineForm(user);
      // Address is optional - the Create button stays disabled until the
      // pre-existing required fields (name/birth date/mobile) are filled,
      // regardless of whether address has been entered.
      await user.type(getFieldByLabel("Address"), "Some Address");
      expect(screen.getByRole("button", { name: "Create & Select" })).toBeDisabled();

      await fillRequiredFields(user);
      expect(screen.getByRole("button", { name: "Create & Select" })).toBeEnabled();
    });
  });
});
