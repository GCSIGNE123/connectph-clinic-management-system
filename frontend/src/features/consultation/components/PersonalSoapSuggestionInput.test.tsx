import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ApiError } from "@/lib/api-client";
import { PersonalSoapSuggestionInput } from "./PersonalSoapSuggestionInput";
import { SoapSuggestionInput } from "./SoapSuggestionInput";

// Task #2 enhancement - the Doctor's My Phrases / Recently used view of a SOAP suggestion field.

const learnedByField: Record<string, string[]> = {};
vi.mock("@/features/consultation/hooks/use-soap-suggestions", () => ({
  useSoapSuggestions: (field: string) => ({ data: learnedByField[field] ?? [] }),
}));

type Personal = { favorites: string[]; recent: string[] };
const personalByField: Record<string, Personal | undefined> = {};
const usePersonalMock = vi.fn();
const mutateMock = vi.fn();
vi.mock("@/features/consultation/hooks/use-soap-personal-phrases", () => ({
  usePersonalSuggestions: (field: string, enabled: boolean) => {
    usePersonalMock(field, enabled);
    return { data: enabled ? personalByField[field] : undefined, refetch: vi.fn() };
  },
  useToggleFavoritePhrase: (field: string) => ({
    mutate: (vars: { text: string; favorite: boolean }, opts?: { onError?: (e: unknown) => void }) => mutateMock(field, vars, opts),
  }),
}));

type Field = "chief_complaint" | "treatment_plan" | "icd10_code";

function Harness({ field = "chief_complaint", multiline = true, initial = "" }: { field?: Field; multiline?: boolean; initial?: string }) {
  const [value, setValue] = useState(initial);
  return <PersonalSoapSuggestionInput field={field} value={value} onChange={setValue} multiline={multiline} aria-label="Field" />;
}

const box = () => screen.getByLabelText("Field") as HTMLTextAreaElement | HTMLInputElement;
const rowLabels = () =>
  screen
    .getAllByRole("button")
    .map((b) => b.textContent ?? "")
    .filter((t) => t && !/^[★☆]$/.test(t));
const headings = () => screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"));

// The suggestion rows act on mousedown. React's select plugin keeps a module-level "mouse is down" flag that only a
// mouseup clears, so release it on the (still mounted) field or later caret moves in other tests are ignored.
function press(el: HTMLElement) {
  fireEvent.mouseDown(el);
  fireEvent.mouseUp(box());
}

function placeCaret(el: HTMLTextAreaElement, position: number) {
  act(() => el.focus());
  el.setSelectionRange(position, position);
  fireEvent.select(el);
}

beforeEach(() => {
  for (const k of Object.keys(learnedByField)) delete learnedByField[k];
  for (const k of Object.keys(personalByField)) delete personalByField[k];
  usePersonalMock.mockReset();
  mutateMock.mockReset();
  learnedByField.chief_complaint = ["Clinic favourite", "Persistent cough"];
  personalByField.chief_complaint = { favorites: ["My usual"], recent: ["Recent one", "Recent two"] };
});

describe("PersonalSoapSuggestionInput - sections", () => {
  it("shows My phrases, Recently used, Clinic suggestions, then Starters - in that order", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    expect(headings()).toEqual(["My phrases", "Recently used", "Clinic suggestions", "Starters"]);
    const labels = rowLabels();
    expect(labels.indexOf("My usual")).toBeLessThan(labels.indexOf("Recent one"));
    expect(labels.indexOf("Recent two")).toBeLessThan(labels.indexOf("Clinic favourite"));
    expect(labels.indexOf("Persistent cough")).toBeLessThan(labels.indexOf("Fever")); // a static starter
    expect(within(screen.getByRole("group", { name: "My phrases" })).getByText("My usual")).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Recently used" })).getByText("Recent one")).toBeInTheDocument();
  });

  it("shows a phrase once, in the highest section that has it", async () => {
    personalByField.chief_complaint = { favorites: ["Cough"], recent: ["cough", "Recent one"] };
    learnedByField.chief_complaint = ["COUGH", "Clinic only"];
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    const labels = rowLabels();
    expect(labels.filter((l) => l.toLowerCase() === "cough")).toEqual(["Cough"]); // My phrases wins over recent/clinic/starter
    expect(within(screen.getByRole("group", { name: "My phrases" })).getByText("Cough")).toBeInTheDocument();
  });

  it("keeps every section short", async () => {
    personalByField.chief_complaint = {
      favorites: Array.from({ length: 9 }, (_, i) => `Mine ${i}`),
      recent: Array.from({ length: 9 }, (_, i) => `Recent ${i}`),
    };
    learnedByField.chief_complaint = Array.from({ length: 9 }, (_, i) => `Clinic ${i}`);
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    const count = (label: string) => within(screen.getByRole("group", { name: label })).getAllByRole("listitem").length;
    expect(count("My phrases")).toBe(5);
    expect(count("Recently used")).toBe(5);
    expect(count("Clinic suggestions")).toBe(5);
    expect(count("Starters")).toBeLessThanOrEqual(4);
  });

  it("typing filters every section, and a match deep in a section is still reachable", async () => {
    personalByField.chief_complaint = { favorites: ["Sore throat and fever"], recent: Array.from({ length: 8 }, (_, i) => `Aches ${i}`).concat("Sore neck") };
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "sore");
    const labels = rowLabels();
    expect(labels).toContain("Sore throat and fever");
    expect(labels).toContain("Sore neck"); // the 9th recent phrase surfaces once it is the only match
    expect(labels).not.toContain("Aches 0");
  });

  it("omits an empty section instead of showing an empty header", async () => {
    personalByField.chief_complaint = { favorites: [], recent: ["Recent one"] };
    learnedByField.chief_complaint = [];
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    expect(headings()).toEqual(["Recently used", "Starters"]);
  });
});

describe("PersonalSoapSuggestionInput - fetching", () => {
  it("does not request the personal list until the field is focused, then requests it for THIS field", async () => {
    const user = userEvent.setup();
    render(<Harness field="chief_complaint" />);
    expect(usePersonalMock).toHaveBeenCalledWith("chief_complaint", false);
    expect(usePersonalMock).not.toHaveBeenCalledWith("chief_complaint", true);
    await user.click(box());
    expect(usePersonalMock).toHaveBeenCalledWith("chief_complaint", true);
  });

  it("falls back to the plain clinic + starter list until (or unless) the personal list arrives", async () => {
    personalByField.chief_complaint = undefined; // request pending or failed
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    expect(screen.queryAllByRole("group")).toHaveLength(0); // no section headings
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument();
    const labels = rowLabels();
    expect(labels[0]).toBe("Clinic favourite"); // learned first...
    expect(labels).toContain("Fever"); // ...then starters, exactly the classic behaviour
    expect(screen.queryByText("☆")).not.toBeInTheDocument();
  });
});

describe("PersonalSoapSuggestionInput - selecting and editing", () => {
  it.each([
    ["a My phrase", "My usual"],
    ["a recent phrase", "Recent one"],
    ["a clinic suggestion", "Clinic favourite"],
    ["a starter", "Fever"],
  ])("selecting %s fills the field and it stays editable", async (_label, phrase) => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    press(screen.getByRole("button", { name: phrase }));
    expect(box().value).toBe(phrase);
    await user.type(box(), " for 2 days");
    expect(box().value).toBe(`${phrase} for 2 days`);
  });

  it("free text is always allowed, with or without a suggestion", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "Zzq entirely custom complaint");
    expect(box().value).toBe("Zzq entirely custom complaint");
  });
});

describe("PersonalSoapSuggestionInput - Save to My Phrases / unfavorite", () => {
  it("offers to save the line being typed, and saving calls the API for this field", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "Brand new phrase");
    press(screen.getByRole("button", { name: '☆ Save "Brand new phrase" to My Phrases' }));
    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(mutateMock.mock.calls[0][0]).toBe("chief_complaint");
    expect(mutateMock.mock.calls[0][1]).toEqual({ text: "Brand new phrase", favorite: true });
  });

  it("does not require the phrase to already be a suggestion, and hides the action when there is nothing to save", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument(); // empty field
    await user.type(box(), "x");
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument(); // too short
    await user.clear(box());
    await user.type(box(), "?!");
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument(); // no letters/digits
    await user.clear(box());
    await user.type(box(), "z".repeat(81));
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument(); // longer than 80
  });

  it("stars a suggestion row to save it, and un-stars a saved one to remove it", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    press(screen.getByRole("button", { name: 'Save "Recent one" to My Phrases' }));
    expect(mutateMock.mock.calls[0][1]).toEqual({ text: "Recent one", favorite: true });
    press(screen.getByRole("button", { name: 'Remove "My usual" from My Phrases' }));
    expect(mutateMock.mock.calls[1][1]).toEqual({ text: "My usual", favorite: false });
    expect(screen.getByRole("button", { name: 'Remove "My usual" from My Phrases' })).toHaveAttribute("aria-pressed", "true");
  });

  it("when the typed line is already saved, the action becomes Remove", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "my usual"); // case-insensitive match of the saved phrase
    expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument();
    press(screen.getByRole("button", { name: '★ Remove "my usual" from My Phrases' }));
    expect(mutateMock.mock.calls[0][1]).toEqual({ text: "my usual", favorite: false });
  });

  it("clicking the star or the save action does not select the row or change the field", async () => {
    const user = userEvent.setup();
    render(<Harness initial="" />);
    await user.click(box());
    press(screen.getByRole("button", { name: 'Save "Recent one" to My Phrases' }));
    expect(box().value).toBe("");
  });

  it("shows the server's reason when a phrase cannot be saved, and clears it when the Doctor keeps typing", async () => {
    mutateMock.mockImplementation((_f, _v, opts) => opts?.onError?.(new ApiError({ message: "That looks like patient-specific text.", statusCode: 422 })));
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    await user.type(box(), "Some phrase");
    press(screen.getByRole("button", { name: '☆ Save "Some phrase" to My Phrases' }));
    expect(await screen.findByText("That looks like patient-specific text.")).toBeInTheDocument();
    await user.type(box(), " more");
    expect(screen.queryByText("That looks like patient-specific text.")).not.toBeInTheDocument();
  });
});

describe("PersonalSoapSuggestionInput - multiline (Treatment plan)", () => {
  beforeEach(() => {
    learnedByField.treatment_plan = ["Clinic plan"];
    personalByField.treatment_plan = { favorites: ["Rest and hydration"], recent: ["Take medicines as advised"] };
  });

  it("matches, saves and replaces ONLY the line the caret is on", async () => {
    const text = "Line one\nhydra\nLine three";
    render(<Harness field="treatment_plan" initial={text} />);
    placeCaret(box() as HTMLTextAreaElement, text.indexOf("hydra") + 5); // end of line 2
    // Only line 2 drives the list: "hydra" matches the saved "Rest and hydration".
    expect(rowLabels()).toContain("Rest and hydration");
    expect(rowLabels()).not.toContain("Take medicines as advised");
    // "Save to My Phrases" offers the current line, never the whole block.
    expect(screen.getByRole("button", { name: '☆ Save "hydra" to My Phrases' })).toBeInTheDocument();
    press(screen.getByRole("button", { name: "Rest and hydration" }));
    expect(box().value).toBe("Line one\nRest and hydration\nLine three");
  });

  it("the whole multi-line block is never offered as one phrase", async () => {
    const text = "First line\nSecond line";
    render(<Harness field="treatment_plan" initial={text} />);
    placeCaret(box() as HTMLTextAreaElement, 4);
    await waitFor(() => {
      const saves = screen.queryAllByRole("button").filter((b) => /^☆ Save/.test(b.textContent ?? ""));
      expect(saves.map((b) => b.textContent)).toEqual(['☆ Save "First line" to My Phrases']);
    });
  });

  it("a blank current line offers no save action", async () => {
    render(<Harness field="treatment_plan" initial={"Line one\n\nLine three"} />);
    placeCaret(box() as HTMLTextAreaElement, "Line one\n".length);
    await screen.findByRole("group", { name: "My phrases" }); // the personal list has loaded
    await waitFor(() => expect(screen.queryByText(/Save ".*" to My Phrases/)).not.toBeInTheDocument());
  });
});

describe("PersonalSoapSuggestionInput - single-line ICD-10 fields", () => {
  it("works on a single-line input and only uses that field's lists", async () => {
    learnedByField.icd10_code = ["Z00.0"];
    personalByField.icd10_code = { favorites: ["J06.9"], recent: ["I10"] };
    const user = userEvent.setup();
    render(<Harness field="icd10_code" multiline={false} />);
    expect(box().tagName).toBe("INPUT");
    await user.click(box());
    expect(rowLabels()).toEqual(expect.arrayContaining(["J06.9", "I10", "Z00.0"]));
    expect(rowLabels()).not.toContain("My usual"); // the chief-complaint phrases never cross fields
  });
});

describe("PersonalSoapSuggestionInput - field isolation and mobile layout", () => {
  it("each field shows only its own personal phrases", async () => {
    personalByField.treatment_plan = { favorites: ["Plan phrase"], recent: [] };
    const user = userEvent.setup();
    const { unmount } = render(<Harness field="chief_complaint" />);
    await user.click(box());
    expect(rowLabels()).toContain("My usual");
    expect(rowLabels()).not.toContain("Plan phrase");
    unmount();
    render(<Harness field="treatment_plan" />);
    await userEvent.setup().click(box());
    expect(rowLabels()).toContain("Plan phrase");
    expect(rowLabels()).not.toContain("My usual");
    expect(usePersonalMock).toHaveBeenCalledWith("treatment_plan", true);
  });

  it("the list is a full-width, height-capped scroll area with the star on every row (usable without hover)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(box());
    const group = screen.getByRole("group", { name: "My phrases" });
    const dropdown = group.parentElement!.parentElement!;
    expect(dropdown.className).toContain("w-full");
    expect(group.parentElement!.className).toContain("max-h-56");
    expect(group.parentElement!.className).toContain("overflow-y-auto");
    const stars = screen.getAllByRole("button").filter((b) => /^[★☆]$/.test(b.textContent ?? ""));
    expect(stars.length).toBeGreaterThan(3);
    for (const s of stars) expect(s.className).not.toContain("hidden"); // always rendered, not hover-only
  });
});

describe("SoapSuggestionInput - personal prop", () => {
  function Wrapper({ personal, disabled }: { personal?: boolean; disabled?: boolean }) {
    const [value, setValue] = useState("");
    return <SoapSuggestionInput field="chief_complaint" value={value} onChange={setValue} personal={personal} disabled={disabled} aria-label="Field" />;
  }

  it("without `personal` (Receptionist/Nurse intake, everything else) it is the classic list and never asks for personal phrases", async () => {
    const user = userEvent.setup();
    render(<Wrapper />);
    await user.click(box());
    expect(usePersonalMock).not.toHaveBeenCalled();
    expect(screen.queryAllByRole("group")).toHaveLength(0);
    expect(rowLabels()[0]).toBe("Clinic favourite");
  });

  it("a read-only viewer never asks for personal phrases even on the Doctor page", () => {
    render(<Wrapper personal disabled />);
    expect(usePersonalMock).not.toHaveBeenCalled();
    expect(box()).toBeDisabled();
  });

  it("with `personal` the Doctor gets the sectioned view", async () => {
    const user = userEvent.setup();
    render(<Wrapper personal />);
    await user.click(box());
    expect(headings()).toEqual(["My phrases", "Recently used", "Clinic suggestions", "Starters"]);
  });
});
