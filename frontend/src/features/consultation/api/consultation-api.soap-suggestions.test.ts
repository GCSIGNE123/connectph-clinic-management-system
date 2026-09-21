import { beforeEach, describe, expect, it, vi } from "vitest";
import { consultationApi } from "./consultation-api";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), put: vi.fn(), post: vi.fn(), patch: vi.fn() },
  apiFetchBlob: vi.fn(),
}));

describe("consultationApi.getSoapSuggestions (Task #2)", () => {
  beforeEach(() => getMock.mockReset());

  it("requests the field with a bounded limit and returns suggestion text only", async () => {
    getMock.mockResolvedValue({ field: "chief_complaint", suggestions: [{ text: "Headache" }, { text: "Cough" }] });
    const result = await consultationApi.getSoapSuggestions("chief_complaint");
    expect(String(getMock.mock.calls[0][0])).toBe("/consultations/soap-suggestions?field=chief_complaint&limit=20");
    expect(result).toEqual(["Headache", "Cough"]);
  });

  it("returns an empty list when nothing qualifies", async () => {
    getMock.mockResolvedValue({ field: "icd10_code", suggestions: [] });
    expect(await consultationApi.getSoapSuggestions("icd10_code")).toEqual([]);
  });
});
