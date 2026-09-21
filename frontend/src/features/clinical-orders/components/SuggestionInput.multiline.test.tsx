import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SuggestionInput, currentLine } from "./SuggestionInput";

const SUGGESTIONS = ["Rest and hydration", "Symptomatic treatment", "Medications as prescribed", "Monitor symptoms"];

function Harness({ initial = "", disabled = false, multiline = true, onValue }: { initial?: string; disabled?: boolean; multiline?: boolean; onValue?: (v: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <SuggestionInput
      value={value}
      onChange={(v) => {
        setValue(v);
        onValue?.(v);
      }}
      suggestions={SUGGESTIONS}
      multiline={multiline}
      disabled={disabled}
      aria-label="Plan"
    />
  );
}

const box = () => screen.getByLabelText("Plan") as HTMLTextAreaElement;

function placeCaret(el: HTMLTextAreaElement, position: number) {
  el.focus();
  el.setSelectionRange(position, position);
  fireEvent.select(el);
}

describe("currentLine (Task #2 segment helper)", () => {
  it("finds the line around the caret, including first/last/empty lines", () => {
    const text = "alpha\nbeta\n\ngamma";
    expect(currentLine(text, 0)).toEqual({ start: 0, end: 5, text: "alpha" });
    expect(currentLine(text, 3)).toEqual({ start: 0, end: 5, text: "alpha" });
    expect(currentLine(text, 5)).toEqual({ start: 0, end: 5, text: "alpha" }); // caret at end of line 1
    expect(currentLine(text, 6)).toEqual({ start: 6, end: 10, text: "beta" });
    expect(currentLine(text, 11)).toEqual({ start: 11, end: 11, text: "" }); // the empty line
    expect(currentLine(text, text.length)).toEqual({ start: 12, end: 17, text: "gamma" });
    expect(currentLine("", 0)).toEqual({ start: 0, end: 0, text: "" });
    expect(currentLine("\nx", 0)).toEqual({ start: 0, end: 0, text: "" }); // caret 0 on a leading newline
  });
});

describe("SuggestionInput - multiline (Task #2)", () => {
  it("renders a textarea (not a single-line input) and shows suggestions on focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(box().tagName).toBe("TEXTAREA");
    await user.click(box());
    expect(await screen.findByRole("button", { name: "Rest and hydration" })).toBeInTheDocument();
  });

  it("typing filters the suggestions to the current line", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "hydra");
    expect(screen.getByRole("button", { name: "Rest and hydration" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Symptomatic treatment" })).not.toBeInTheDocument();
  });

  it("selecting a suggestion fills the field, leaves it editable, and keeps the caret at the end of the insertion", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "symp");
    await user.click(screen.getByRole("button", { name: "Symptomatic treatment" }));
    expect(box()).toHaveValue("Symptomatic treatment");
    expect(box().selectionStart).toBe("Symptomatic treatment".length);
    // still fully editable afterwards
    await user.type(box(), " for 3 days");
    expect(box()).toHaveValue("Symptomatic treatment for 3 days");
  });

  it("replaces ONLY the current line and preserves the other lines", async () => {
    const user = userEvent.setup();
    const onValue = vi.fn();
    render(<Harness initial={"Line one stays\nmon\nLine three stays"} onValue={onValue} />);
    // caret at the end of the middle line ("mon", offsets 15..18)
    placeCaret(box(), 18);
    expect(await screen.findByRole("button", { name: "Monitor symptoms" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Monitor symptoms" }));
    expect(box()).toHaveValue("Line one stays\nMonitor symptoms\nLine three stays");
    expect(box().selectionStart).toBe("Line one stays\nMonitor symptoms".length);
  });

  it("matches against the line the caret is on, not the whole text", async () => {
    render(<Harness initial={"Rest and hydration\nzzz"} />);
    placeCaret(box(), 22); // end of "zzz" -> no suggestion matches this line
    expect(screen.queryByRole("button", { name: "Rest and hydration" })).not.toBeInTheDocument();
    placeCaret(box(), 4); // inside the first line, which already equals a suggestion -> nothing left to offer for it
    expect(screen.queryByRole("button", { name: "Rest and hydration" })).not.toBeInTheDocument();
  });

  it("an empty new line offers suggestions again without touching the text above", async () => {
    const user = userEvent.setup();
    render(<Harness initial={"Rest and hydration\n"} />);
    placeCaret(box(), 19);
    await user.click(await screen.findByRole("button", { name: "Monitor symptoms" }));
    expect(box()).toHaveValue("Rest and hydration\nMonitor symptoms");
  });

  it("custom text is always valid and can be cleared", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "Patient-specific custom plan");
    expect(box()).toHaveValue("Patient-specific custom plan");
    await user.clear(box());
    expect(box()).toHaveValue("");
    await user.type(box(), "another");
    expect(box()).toHaveValue("another");
  });

  it("does not show suggestions or accept edits when disabled", async () => {
    const user = userEvent.setup();
    render(<Harness initial="Existing plan" disabled />);
    await user.click(box());
    expect(box()).toBeDisabled();
    expect(box()).toHaveValue("Existing plan");
    expect(screen.queryByRole("button", { name: "Rest and hydration" })).not.toBeInTheDocument();
  });

  it("single-line mode is unchanged: an <input>, and a pick replaces the whole value", async () => {
    const user = userEvent.setup();
    render(<Harness multiline={false} />);
    expect(box().tagName).toBe("INPUT");
    await user.click(box());
    await user.type(box(), "moni");
    await user.click(screen.getByRole("button", { name: "Monitor symptoms" }));
    expect(box()).toHaveValue("Monitor symptoms");
  });
});
