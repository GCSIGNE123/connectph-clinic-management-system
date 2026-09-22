import { beforeEach, describe, expect, it, vi } from "vitest";
import { consultationApi } from "./consultation-api";

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
    put: vi.fn(),
    patch: vi.fn(),
    delete: (...a: unknown[]) => del(...a),
  },
  ApiError: class extends Error {},
}));

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  del.mockReset();
});

describe("consultationApi personal phrases (Task #2 enhancement)", () => {
  it("getPersonalSuggestions calls the personal endpoint for one field and maps text only", async () => {
    get.mockResolvedValue({ field: "treatment_plan", favorites: [{ text: "Mine" }], recent: [{ text: "R1" }, { text: "R2" }] });
    const result = await consultationApi.getPersonalSuggestions("treatment_plan");
    expect(get).toHaveBeenCalledWith("/consultations/soap-suggestions/personal?field=treatment_plan&limit=20");
    expect(result).toEqual({ favorites: ["Mine"], recent: ["R1", "R2"] });
  });

  it("addFavoritePhrase posts {field, text} and returns the saved text", async () => {
    post.mockResolvedValue({ field: "chief_complaint", text: "Fever and cough" });
    await expect(consultationApi.addFavoritePhrase("chief_complaint", "  Fever and cough ")).resolves.toBe("Fever and cough");
    expect(post).toHaveBeenCalledWith("/consultations/soap-suggestions/favorites", { field: "chief_complaint", text: "  Fever and cough " });
  });

  it("removeFavoritePhrase deletes by field + text, URL-encoded", async () => {
    del.mockResolvedValue(undefined);
    await consultationApi.removeFavoritePhrase("chief_complaint", "Cough & colds, 3 days");
    expect(del).toHaveBeenCalledWith(
      "/consultations/soap-suggestions/favorites?field=chief_complaint&text=Cough%20%26%20colds%2C%203%20days"
    );
  });

  it("the existing clinic-suggestions call is unchanged", async () => {
    get.mockResolvedValue({ field: "chief_complaint", suggestions: [{ text: "Fever" }] });
    await expect(consultationApi.getSoapSuggestions("chief_complaint")).resolves.toEqual(["Fever"]);
    expect(get).toHaveBeenCalledWith("/consultations/soap-suggestions?field=chief_complaint&limit=20");
  });
});
