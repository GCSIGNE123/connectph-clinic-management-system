import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SearchableSelect } from "./searchable-select";

const options = [
  { value: "1", label: "ALP" },
  { value: "2", label: "AROVENT NEB" },
  { value: "3", label: "CHLORIDE (Cl)" },
  { value: "4", label: "CREATININE" },
];

describe("SearchableSelect", () => {
  it("shows the selected option's label when closed", () => {
    render(<SearchableSelect options={options} value="3" onChange={vi.fn()} />);
    expect(screen.getByDisplayValue("CHLORIDE (Cl)")).toBeInTheDocument();
  });

  it("shows a placeholder when nothing is selected", () => {
    render(<SearchableSelect options={options} value="" onChange={vi.fn()} placeholder="Select service" />);
    expect(screen.getByPlaceholderText("Select service")).toBeInTheDocument();
  });

  it("filters the dropdown as the user types, case-insensitively", async () => {
    const user = userEvent.setup();
    render(<SearchableSelect options={options} value="" onChange={vi.fn()} />);
    await user.click(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "chlor");
    expect(screen.getByRole("button", { name: "CHLORIDE (Cl)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "ALP" })).not.toBeInTheDocument();
  });

  it("calls onChange with the option's value when clicked, and closes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SearchableSelect options={options} value="" onChange={onChange} />);
    await user.click(screen.getByRole("textbox"));
    await user.click(screen.getByRole("button", { name: "CREATININE" }));
    expect(onChange).toHaveBeenCalledWith("4");
    expect(screen.queryByRole("button", { name: "CREATININE" })).not.toBeInTheDocument();
  });

  it("shows an empty-state message when no options match", async () => {
    const user = userEvent.setup();
    render(<SearchableSelect options={options} value="" onChange={vi.fn()} emptyLabel="No matches." />);
    await user.click(screen.getByRole("textbox"));
    await user.type(screen.getByRole("textbox"), "zzz-nonexistent");
    expect(screen.getByText("No matches.")).toBeInTheDocument();
  });

  it("clears the search text and closes on Escape", async () => {
    const user = userEvent.setup();
    render(<SearchableSelect options={options} value="1" onChange={vi.fn()} />);
    const input = screen.getByRole("textbox");
    await user.click(input);
    await user.type(input, "xyz");
    await user.keyboard("{Escape}");
    expect(screen.queryByText("No matches.")).not.toBeInTheDocument();
  });
});
