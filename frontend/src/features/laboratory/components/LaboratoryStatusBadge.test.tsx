import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LaboratoryStatusBadge } from "./LaboratoryStatusBadge";

describe("LaboratoryStatusBadge", () => {
  it("renders the status text for each lifecycle state", () => {
    const { rerender } = render(<LaboratoryStatusBadge status="Requested" />);
    expect(screen.getByText("Requested")).toBeInTheDocument();

    rerender(<LaboratoryStatusBadge status="Released" />);
    expect(screen.getByText("Released")).toBeInTheDocument();

    rerender(<LaboratoryStatusBadge status="Cancelled" />);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });
});
