import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SoapSuggestionInput } from "./SoapSuggestionInput";

const useSoapSuggestionsMock = vi.fn();
vi.mock("@/features/consultation/hooks/use-soap-suggestions", () => ({
  useSoapSuggestions: (field: string, enabled: boolean) => useSoapSuggestionsMock(field, enabled),
}));

function Harness({ field, disabled = false, multiline = true }: { field: "chief_complaint" | "icd10_code"; disabled?: boolean; multiline?: boolean }) {
  const [value, setValue] = useState("");
  return <SoapSuggestionInput field={field} value={value} onChange={setValue} disabled={disabled} multiline={multiline} aria-label="Field" />;
}

const box = () => screen.getByLabelText("Field") as HTMLTextAreaElement | HTMLInputElement;

describe("SoapSuggestionInput (Task #2)", () => {
  beforeEach(() => useSoapSuggestionsMock.mockReset().mockReturnValue({ data: [] }));

  it("shows the clinic's learned suggestions BEFORE the static starters, without duplicates", async () => {
    useSoapSuggestionsMock.mockReturnValue({ data: ["Clinic favourite", "fever"] });
    const user = userEvent.setup();
    render(<Harness field="chief_complaint" />);
    await user.click(box());
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels[0]).toBe("Clinic favourite");
    expect(labels[1]).toBe("fever"); // the learned casing wins over the static "Fever"
    expect(labels.filter((l) => l?.toLowerCase() === "fever")).toHaveLength(1);
    expect(labels).toContain("Cough"); // static starters still follow
  });

  it("falls back to the static starters when nothing was learned (or the request failed)", async () => {
    useSoapSuggestionsMock.mockReturnValue({ data: undefined });
    const user = userEvent.setup();
    render(<Harness field="chief_complaint" />);
    await user.click(box());
    expect(screen.getByRole("button", { name: "Fever" })).toBeInTheDocument();
  });

  it("selecting a learned suggestion populates the field and it stays editable / custom text still works", async () => {
    useSoapSuggestionsMock.mockReturnValue({ data: ["Persistent dry cough"] });
    const user = userEvent.setup();
    render(<Harness field="chief_complaint" />);
    await user.click(box());
    await user.click(screen.getByRole("button", { name: "Persistent dry cough" }));
    expect(box()).toHaveValue("Persistent dry cough");
    await user.type(box(), " x2 weeks");
    expect(box()).toHaveValue("Persistent dry cough x2 weeks");
    await user.clear(box());
    await user.type(box(), "totally custom");
    expect(box()).toHaveValue("totally custom");
  });

  it("ICD-10 code offers only learned values (no static catalog) and is a single-line input", async () => {
    useSoapSuggestionsMock.mockReturnValue({ data: ["J06.9"] });
    const user = userEvent.setup();
    render(<Harness field="icd10_code" multiline={false} />);
    expect(box().tagName).toBe("INPUT");
    await user.click(box());
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["J06.9"]);
  });

  it("no learned data and no static list -> no dropdown for ICD-10, free typing still works", async () => {
    const user = userEvent.setup();
    render(<Harness field="icd10_code" multiline={false} />);
    await user.click(box());
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    await user.type(box(), "Z00.0");
    expect(box()).toHaveValue("Z00.0");
  });

  it("read-only (disabled) fields make no suggestion request and stay plain", async () => {
    render(<Harness field="chief_complaint" disabled />);
    expect(box()).toBeDisabled();
    expect(useSoapSuggestionsMock).toHaveBeenCalledWith("chief_complaint", false);
  });
});
