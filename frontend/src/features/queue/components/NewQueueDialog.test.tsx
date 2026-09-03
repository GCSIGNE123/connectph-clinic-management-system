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
            { id: "svc-lab", service_name: "BLOOD CHEMISTRY", name: "BLOOD CHEMISTRY", service_code: "BLDCHEM", default_price: "350.00" },
            { id: "svc-lab-2", service_name: "URINALYSIS", name: "URINALYSIS", service_code: "URIN", default_price: "150.00" },
            { id: "svc-med", service_name: "Consultation - Follow-up Visit", name: "Follow-up", service_code: "OTHER" },
            // Department-aware Service filtering: assigned to a specific
            // department, unlike every other mock service above (all
            // `department_id: undefined` - unassigned/shared).
            { id: "svc-lab-only", service_name: "HEP B SCREENING", name: "HEP B SCREENING", service_code: "HEPB", default_price: "200.00", department_id: "dept-lab" },
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
let lastLabPaymentStepProps: { onPaid: (invoiceId: string) => void; onBack: () => void; serviceIds?: string[] } | null = null;
vi.mock("@/features/queue/components/LabPaymentStep", () => ({
  LabPaymentStep: (props: { visitId: string; serviceIds?: string[]; onPaid: (invoiceId: string) => void; onBack: () => void }) => {
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
  // SearchableSelect - open then click the matching option. The Laboratory
  // multi-select uses "Select Laboratory Service"; every other department
  // uses the single "Select Service" field - either placeholder contains
  // "Select" and ends in "Service".
  await user.click(screen.getByPlaceholderText(/select (laboratory )?service/i));
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

  describe("Multiple Laboratory Services in One Queue Transaction", () => {
    async function selectLabService(user: ReturnType<typeof userEvent.setup>, label: string) {
      await user.click(screen.getByPlaceholderText(/select laboratory service/i));
      const option = await screen.findByText(label);
      await user.click(option);
    }

    it("1: renders the Laboratory multi-select with a running total, hides the single Service field", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");

      expect(screen.getByText("Laboratory Services")).toBeInTheDocument();
      expect(screen.queryByText("Service", { selector: "label" })).not.toBeInTheDocument();
      expect(screen.getByText(/select at least one laboratory service/i)).toBeInTheDocument();
    });

    it("2/4: selecting two services lists both with prices and a correct running total", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await selectLabService(user, "BLOOD CHEMISTRY");
      await selectLabService(user, "URINALYSIS");

      expect(screen.getByText("BLOOD CHEMISTRY")).toBeInTheDocument();
      expect(screen.getByText("URINALYSIS")).toBeInTheDocument();
      expect(screen.getByText("₱350.00")).toBeInTheDocument();
      expect(screen.getByText("₱150.00")).toBeInTheDocument();
      expect(screen.getByText("₱500.00")).toBeInTheDocument(); // Total
    });

    it("3: removing a selected service updates the total and re-offers it for selection", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await selectLabService(user, "BLOOD CHEMISTRY");
      await selectLabService(user, "URINALYSIS");
      expect(screen.getByText("₱500.00")).toBeInTheDocument();

      await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);

      expect(screen.queryByText("BLOOD CHEMISTRY")).not.toBeInTheDocument();
      expect(screen.getByText("URINALYSIS")).toBeInTheDocument();
      // Line price and Total both show ₱150.00 now that only one service
      // remains - assert there are exactly two (not stale from before removal).
      expect(screen.getAllByText("₱150.00")).toHaveLength(2);

      // Removed service is selectable again.
      await user.click(screen.getByPlaceholderText(/select laboratory service/i));
      expect(await screen.findByText("BLOOD CHEMISTRY")).toBeInTheDocument();
    });

    it("5: an already-selected service is not offered again (no duplicate selection)", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await selectLabService(user, "BLOOD CHEMISTRY");
      await user.click(screen.getByPlaceholderText(/select laboratory service/i));
      // Only one "BLOOD CHEMISTRY" on screen - the selected-services list
      // entry - not a second one in the (now-empty-of-it) dropdown options.
      expect(screen.getAllByText("BLOOD CHEMISTRY")).toHaveLength(1);
    });

    it("6: Proceed to Payment stays disabled until at least one Laboratory service is selected", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      expect(screen.getByRole("button", { name: "Proceed to Payment" })).toBeDisabled();

      await selectLabService(user, "BLOOD CHEMISTRY");
      expect(screen.getByRole("button", { name: "Proceed to Payment" })).toBeEnabled();
    });

    it("7: proceeding creates the draft visit with the first-selected service and passes every selected service id to LabPaymentStep", async () => {
      mockCreatePreQueue.mockReset().mockResolvedValue({
        id: "visit-multi", serviceId: "svc-lab", patientId: "pat-1", departmentId: "dept-lab", doctorId: null,
      });
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await selectLabService(user, "BLOOD CHEMISTRY");
      await selectLabService(user, "URINALYSIS");
      await user.click(screen.getByRole("button", { name: "Proceed to Payment" }));

      await waitFor(() => expect(mockCreatePreQueue).toHaveBeenCalledTimes(1));
      expect(mockCreatePreQueue.mock.calls[0][0]).toMatchObject({ serviceId: "svc-lab" });

      expect(await screen.findByTestId("lab-payment-step")).toBeInTheDocument();
      expect(lastLabPaymentStepProps?.serviceIds).toEqual(["svc-lab", "svc-lab-2"]);
    });

    it("9: paying for a multi-service selection still creates exactly one queue ticket", async () => {
      mockCreatePreQueue.mockReset().mockResolvedValue({
        id: "visit-multi-2", serviceId: "svc-lab", patientId: "pat-1", departmentId: "dept-lab", doctorId: null,
      });
      mockCreateQueueMutateAsync.mockReset().mockResolvedValue({ id: "queue-multi", queueNumber: "L010" });
      const user = userEvent.setup();
      const onCreated = vi.fn();
      renderDialog(onCreated);

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");
      await selectLabService(user, "BLOOD CHEMISTRY");
      await selectLabService(user, "URINALYSIS");
      await user.click(screen.getByRole("button", { name: "Proceed to Payment" }));

      expect(await screen.findByTestId("lab-payment-step")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Simulate Paid" }));

      await waitFor(() => expect(mockCreateQueueMutateAsync).toHaveBeenCalledTimes(1));
      await waitFor(() => expect(onCreated).toHaveBeenCalledWith("queue-multi"));
    });

    it("11: the Doctor field remains hidden while multiple Laboratory services are selected", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");
      await selectLabService(user, "BLOOD CHEMISTRY");
      await selectLabService(user, "URINALYSIS");

      expect(screen.queryByText(/^Doctor/)).not.toBeInTheDocument();
    });
  });

  describe("department-aware Service filtering", () => {
    it("does not offer a department-assigned service under a different department", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-med");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await user.click(screen.getByPlaceholderText(/select service/i));
      // "HEP B SCREENING" (svc-lab-only) is assigned to dept-lab, not dept-med.
      expect(screen.queryByText("HEP B SCREENING")).not.toBeInTheDocument();
      // A shared (unassigned) service is still offered.
      expect(screen.getByText("Consultation - Follow-up Visit")).toBeInTheDocument();
    });

    it("drops a Laboratory-service selection that's no longer valid after the Department changes, but keeps a shared one", async () => {
      const user = userEvent.setup();
      renderDialog();

      await selectPatient(user);
      await waitFor(() => expect(getSelectByLabel("Department")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");
      await waitFor(() => expect(getSelectByLabel("Branch")).toBeInTheDocument());
      await user.selectOptions(getSelectByLabel("Branch"), "branch-1");

      await user.click(screen.getByPlaceholderText(/select laboratory service/i));
      await user.click(await screen.findByText("BLOOD CHEMISTRY")); // shared (department_id undefined)
      await user.click(screen.getByPlaceholderText(/select laboratory service/i));
      await user.click(await screen.findByText("HEP B SCREENING")); // assigned to dept-lab
      expect(screen.getByText("BLOOD CHEMISTRY")).toBeInTheDocument();
      expect(screen.getByText("HEP B SCREENING")).toBeInTheDocument();

      // Switch away to a non-Laboratory department (hides the multi-select)
      // and back - HEP B SCREENING no longer belongs to dept-med, so it's
      // dropped; the shared BLOOD CHEMISTRY selection survives.
      await user.selectOptions(getSelectByLabel("Department"), "dept-med");
      await user.selectOptions(getSelectByLabel("Department"), "dept-lab");

      expect(screen.getByText("BLOOD CHEMISTRY")).toBeInTheDocument();
      expect(screen.queryByText("HEP B SCREENING")).not.toBeInTheDocument();
    });
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
