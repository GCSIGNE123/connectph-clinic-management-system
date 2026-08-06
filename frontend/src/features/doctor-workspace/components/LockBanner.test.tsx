import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LockBanner } from "./LockBanner";

describe("LockBanner", () => {
  it("renders nothing when there is no active lock", () => {
    const { container } = render(<LockBanner lock={{ locked: false, lockedBy: null, lockedByName: null, lockedAt: null, isSelf: false }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when lock is null/undefined", () => {
    const { container } = render(<LockBanner lock={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a self-editing confirmation when the current user holds the lock", () => {
    render(
      <LockBanner
        lock={{ locked: true, lockedBy: "user-1", lockedByName: "Maria Santos", lockedAt: new Date().toISOString(), isSelf: true }}
      />
    );
    expect(screen.getByText(/you have this visit open for editing/i)).toBeInTheDocument();
  });

  it("shows a warning banner naming the lock holder when locked by another user", () => {
    render(
      <LockBanner
        lock={{ locked: true, lockedBy: "user-2", lockedByName: "Dr. Ana Lopez", lockedAt: new Date().toISOString(), isSelf: false }}
      />
    );
    expect(screen.getByText(/currently being edited by/i)).toBeInTheDocument();
    expect(screen.getByText("Dr. Ana Lopez")).toBeInTheDocument();
  });
});
