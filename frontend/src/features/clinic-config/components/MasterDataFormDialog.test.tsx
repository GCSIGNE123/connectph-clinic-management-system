import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MasterDataFormDialog } from "./MasterDataFormDialog";
import type { FieldConfig } from "./FieldConfig";

/** Field config mirroring the Doctors master-data page (see
 * `app/(dashboard)/doctors/page.tsx`) - used here to test the generic
 * form dialog against a representative real module. */
const DOCTOR_FIELDS: FieldConfig[] = [
  { name: "first_name", label: "First name", type: "text", required: true },
  { name: "last_name", label: "Last name", type: "text", required: true },
  { name: "specialization", label: "Specialization", type: "text" },
  {
    name: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "Active", label: "Active" },
      { value: "Inactive", label: "Inactive" },
    ],
  },
];

describe("MasterDataFormDialog (doctors)", () => {
  it("renders all configured fields for a new doctor", () => {
    render(
      <MasterDataFormDialog open record={null} fields={DOCTOR_FIELDS} onOpenChange={() => undefined} onSubmit={() => undefined} />
    );

    expect(screen.getByLabelText(/First name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Last name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Specialization/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Status/)).toBeInTheDocument();
    expect(screen.getByText("Add record")).toBeInTheDocument();
  });

  it("pre-fills fields from the record being edited and submits the edited values", async () => {
    const onSubmit = vi.fn();
    const record = { id: "1", first_name: "Jose", last_name: "Rizal", specialization: "General Medicine", status: "Active" };

    render(
      <MasterDataFormDialog open record={record} fields={DOCTOR_FIELDS} onOpenChange={() => undefined} onSubmit={onSubmit} />
    );

    expect(screen.getByText("Edit record")).toBeInTheDocument();
    const lastNameInput = screen.getByLabelText(/Last name/) as HTMLInputElement;
    expect(lastNameInput.value).toBe("Rizal");

    fireEvent.change(lastNameInput, { target: { value: "Bonifacio" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ last_name: "Bonifacio", first_name: "Jose" });
  });
});
