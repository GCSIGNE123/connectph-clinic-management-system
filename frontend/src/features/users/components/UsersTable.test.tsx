import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { UsersTable } from "./UsersTable";
import type { ManagedUser } from "@/features/users/types";
import { Role, UserStatus } from "@/types";

function buildUser(overrides: Partial<ManagedUser> = {}): ManagedUser {
  return {
    id: "1",
    firstName: "Jane",
    lastName: "Doe",
    email: "jane@clinic.com",
    mobileNumber: "+63 900 000 0000",
    username: "jane.doe",
    role: Role.Receptionist,
    clinicId: "clinic-1",
    branchId: "branch-1",
    branchName: "Main Branch",
    status: UserStatus.Active,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

const noop = () => undefined;

describe("UsersTable", () => {
  it("renders a row per user with their details", () => {
    const users = [buildUser(), buildUser({ id: "2", firstName: "John", username: "john.doe" })];

    render(
      <UsersTable
        users={users}
        onEdit={noop}
        onDisable={noop}
        onEnable={noop}
        onResetPassword={noop}
      />
    );

    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("John Doe")).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(2);
  });

  it("shows an empty state when there are no users", () => {
    render(
      <UsersTable users={[]} onEdit={noop} onDisable={noop} onEnable={noop} onResetPassword={noop} />
    );

    expect(screen.getByText(/no users found/i)).toBeInTheDocument();
  });

  it("shows a loading skeleton instead of the table while loading", () => {
    render(
      <UsersTable
        users={[]}
        isLoading
        onEdit={noop}
        onDisable={noop}
        onEnable={noop}
        onResetPassword={noop}
      />
    );

    expect(screen.queryByText(/no users found/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });
});
