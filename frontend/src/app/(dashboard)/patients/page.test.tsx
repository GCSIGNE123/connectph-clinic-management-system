import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PatientsPage from "./page";
import { Role } from "@/types";

const usePatientsMock = vi.fn();
vi.mock("@/features/patients/hooks/use-patients", () => ({
  usePatients: (params: unknown) => usePatientsMock(params),
  useDebouncedValue: <T,>(value: T) => value,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: Role.Receptionist } }),
}));
vi.mock("@/features/patients/api/patients-api", () => ({ patientsApi: { get: vi.fn() } }));
vi.mock("@/features/patients/components/PatientFormDialog", () => ({ PatientFormDialog: () => null }));
vi.mock("@/features/patients/components/ArchiveRestoreDialog", () => ({ ArchiveRestoreDialog: () => null }));

const tableProps: { emptyMessage?: string }[] = [];
vi.mock("@/features/patients/components/PatientsTable", () => ({
  PatientsTable: (props: { emptyMessage?: string }) => {
    tableProps.push(props);
    return <div data-testid="patients-table" />;
  },
}));

function lastParams() {
  return usePatientsMock.mock.calls.at(-1)?.[0];
}

describe("PatientsPage - Patient type (YAKAP) filter (Task #5)", () => {
  beforeEach(() => {
    usePatientsMock.mockReset().mockReturnValue({
      data: { data: [], meta: { page: 1, pageSize: 10, total: 0, totalPages: 1 } },
      isLoading: false,
      isFetching: false,
      isError: false,
    });
    tableProps.length = 0;
  });

  it("renders the Patient type filter defaulting to All Patients (no YAKAP param sent)", () => {
    render(<PatientsPage />);
    const select = screen.getByLabelText("Filter by patient type");
    expect(select).toHaveValue("");
    expect(screen.getByRole("option", { name: "All Patients" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Regular Patients" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "YAKAP Patients" })).toBeInTheDocument();
    expect(lastParams().isYakapBeneficiary).toBeUndefined();
  });

  it("YAKAP Patients sends isYakapBeneficiary=true and resets to page 1", async () => {
    const user = userEvent.setup();
    render(<PatientsPage />);
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "yakap");
    await waitFor(() => expect(lastParams()).toMatchObject({ isYakapBeneficiary: true, page: 1 }));
  });

  it("Regular Patients sends isYakapBeneficiary=false (not 'omitted')", async () => {
    const user = userEvent.setup();
    render(<PatientsPage />);
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "regular");
    await waitFor(() => expect(lastParams().isYakapBeneficiary).toBe(false));
  });

  it("switching back to All Patients drops the filter", async () => {
    const user = userEvent.setup();
    render(<PatientsPage />);
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "yakap");
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "");
    await waitFor(() => expect(lastParams().isYakapBeneficiary).toBeUndefined());
  });

  it("keeps the YAKAP filter when a search term is typed (filter + search together)", async () => {
    const user = userEvent.setup();
    render(<PatientsPage />);
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "yakap");
    await user.type(screen.getByLabelText("Search patients"), "Santos");
    await waitFor(() => expect(lastParams()).toMatchObject({ isYakapBeneficiary: true, search: "Santos" }));
  });

  it("shows a YAKAP-specific empty state and never a regular-patients message", async () => {
    const user = userEvent.setup();
    render(<PatientsPage />);
    await user.selectOptions(screen.getByLabelText("Filter by patient type"), "yakap");
    await waitFor(() => expect(tableProps.at(-1)?.emptyMessage).toBe("No YAKAP patients found."));
    await user.type(screen.getByLabelText("Search patients"), "Cruz");
    await waitFor(() => expect(tableProps.at(-1)?.emptyMessage).toBe('No YAKAP patients match "Cruz".'));
  });
});
