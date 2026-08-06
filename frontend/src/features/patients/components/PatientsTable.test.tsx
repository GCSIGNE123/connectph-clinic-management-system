import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PatientsTable, computeAge } from "./PatientsTable";
import { PatientGender, PatientStatus, type PatientListItem } from "@/features/patients/types";

function buildPatient(overrides: Partial<PatientListItem> = {}): PatientListItem {
  return {
    id: "1",
    patientNumber: "PAT-000001",
    firstName: "Juan",
    lastName: "Dela Cruz",
    birthDate: "1990-01-01",
    gender: PatientGender.Male,
    mobileNumber: "+639171234567",
    status: PatientStatus.Active,
    dateRegistered: new Date().toISOString(),
    lastVisit: null,
    branchId: null,
    photoUrl: null,
    ...overrides,
  };
}

const noop = () => undefined;

describe("PatientsTable", () => {
  it("renders a row per patient with their details", () => {
    const patients = [
      buildPatient(),
      buildPatient({ id: "2", patientNumber: "PAT-000002", firstName: "Maria", lastName: "Santos" }),
    ];

    render(
      <PatientsTable
        patients={patients}
        onView={noop}
        onEdit={noop}
        onArchive={noop}
        onRestore={noop}
        canManage
        canArchive
      />
    );

    expect(screen.getByText("Juan Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("Maria Santos")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
    expect(screen.getByText("PAT-000001")).toBeInTheDocument();
  });

  it("shows an empty state when there are no patients", () => {
    render(
      <PatientsTable patients={[]} onView={noop} onEdit={noop} onArchive={noop} onRestore={noop} canManage canArchive />
    );

    expect(screen.getByText(/no patients found/i)).toBeInTheDocument();
  });

  it("shows a loading skeleton instead of the table while loading", () => {
    render(
      <PatientsTable
        patients={[]}
        isLoading
        onView={noop}
        onEdit={noop}
        onArchive={noop}
        onRestore={noop}
        canManage
        canArchive
      />
    );

    expect(screen.queryByText(/no patients found/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });
});

describe("computeAge", () => {
  it("computes whole years from a birth date", () => {
    const tenYearsAgo = new Date();
    tenYearsAgo.setFullYear(tenYearsAgo.getFullYear() - 10);
    expect(computeAge(tenYearsAgo.toISOString())).toBe(10);
  });
});
