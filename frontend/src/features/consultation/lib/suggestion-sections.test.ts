import { describe, expect, it } from "vitest";
import { SECTION_LIMITS, buildSuggestionSections } from "./suggestion-sections";

describe("buildSuggestionSections (Task #2 enhancement)", () => {
  it("orders the sections My phrases, Recently used, Clinic suggestions, Starters", () => {
    const s = buildSuggestionSections({ mine: ["a"], recent: ["b"], clinic: ["c"], starters: ["d"] });
    expect(s.map((x) => [x.id, x.label])).toEqual([
      ["mine", "My phrases"],
      ["recent", "Recently used"],
      ["clinic", "Clinic suggestions"],
      ["starters", "Starters"],
    ]);
  });

  it("shows a phrase once, in the highest section (case- and whitespace-insensitive)", () => {
    const s = buildSuggestionSections({
      mine: ["Cough"],
      recent: [" cough ", "Fever"],
      clinic: ["FEVER", "Colds"],
      starters: ["cough", "colds", "Headache"],
    });
    expect(s.find((x) => x.id === "mine")!.items).toEqual(["Cough"]);
    expect(s.find((x) => x.id === "recent")!.items).toEqual(["Fever"]);
    expect(s.find((x) => x.id === "clinic")!.items).toEqual(["Colds"]);
    expect(s.find((x) => x.id === "starters")!.items).toEqual(["Headache"]);
  });

  it("drops empty sections and blank entries, and carries small per-section limits", () => {
    const s = buildSuggestionSections({ mine: [], recent: ["", "  "], clinic: ["Only clinic"], starters: [] });
    expect(s).toEqual([{ id: "clinic", label: "Clinic suggestions", items: ["Only clinic"], limit: SECTION_LIMITS.clinic }]);
    expect(SECTION_LIMITS).toEqual({ mine: 5, recent: 5, clinic: 5, starters: 4 });
  });

  it("never invents entries: only what each list contains", () => {
    const s = buildSuggestionSections({ mine: ["x"], recent: [], clinic: [], starters: [] });
    expect(s).toHaveLength(1);
    expect(s[0].items).toEqual(["x"]);
  });
});
