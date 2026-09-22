import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { usePersonalSuggestions, useToggleFavoritePhrase } from "./use-soap-personal-phrases";

const getPersonal = vi.fn();
const addFavorite = vi.fn();
const removeFavorite = vi.fn();
vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    getPersonalSuggestions: (...a: unknown[]) => getPersonal(...a),
    addFavoritePhrase: (...a: unknown[]) => addFavorite(...a),
    removeFavoritePhrase: (...a: unknown[]) => removeFavorite(...a),
  },
}));

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { client, wrapper };
}

beforeEach(() => {
  getPersonal.mockReset().mockResolvedValue({ favorites: ["Mine"], recent: ["Recent", "Other"] });
  addFavorite.mockReset().mockImplementation(async (_f: string, text: string) => text.trim());
  removeFavorite.mockReset().mockResolvedValue(undefined);
});

describe("usePersonalSuggestions", () => {
  it("does not request anything until enabled, then requests exactly this field", async () => {
    const { wrapper } = setup();
    const { result, rerender } = renderHook(({ on }) => usePersonalSuggestions("treatment_plan", on), { wrapper, initialProps: { on: false } });
    expect(getPersonal).not.toHaveBeenCalled();
    rerender({ on: true });
    await waitFor(() => expect(result.current.data).toEqual({ favorites: ["Mine"], recent: ["Recent", "Other"] }));
    expect(getPersonal).toHaveBeenCalledWith("treatment_plan");
  });

  it("keeps each field's cache separate", async () => {
    const { wrapper } = setup();
    getPersonal.mockImplementation(async (field: string) => ({ favorites: [`fav-${field}`], recent: [] }));
    const a = renderHook(() => usePersonalSuggestions("chief_complaint", true), { wrapper });
    const b = renderHook(() => usePersonalSuggestions("treatment_plan", true), { wrapper });
    await waitFor(() => expect(a.result.current.data?.favorites).toEqual(["fav-chief_complaint"]));
    await waitFor(() => expect(b.result.current.data?.favorites).toEqual(["fav-treatment_plan"]));
  });

  it("a failed request leaves data undefined (the caller falls back to the classic list)", async () => {
    getPersonal.mockRejectedValue(new Error("403"));
    const { wrapper } = setup();
    const { result } = renderHook(() => usePersonalSuggestions("chief_complaint", true), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });
});

describe("useToggleFavoritePhrase", () => {
  it("saving moves the phrase to My phrases (newest first) and out of Recently used", async () => {
    const { wrapper } = setup();
    const personal = renderHook(() => usePersonalSuggestions("chief_complaint", true), { wrapper });
    await waitFor(() => expect(personal.result.current.data).toBeDefined());
    getPersonal.mockResolvedValue({ favorites: ["Recent", "Mine"], recent: ["Other"] }); // what the refetch will return
    const toggle = renderHook(() => useToggleFavoritePhrase("chief_complaint"), { wrapper });
    await act(async () => {
      await toggle.result.current.mutateAsync({ text: "  recent ", favorite: true });
    });
    expect(addFavorite).toHaveBeenCalledWith("chief_complaint", "  recent ");
    await waitFor(() => expect(personal.result.current.data).toEqual({ favorites: ["Recent", "Mine"], recent: ["Other"] }));
  });

  it("removing calls the delete endpoint for this field and drops it from My phrases", async () => {
    const { wrapper } = setup();
    const personal = renderHook(() => usePersonalSuggestions("treatment_plan", true), { wrapper });
    await waitFor(() => expect(personal.result.current.data?.favorites).toEqual(["Mine"]));
    getPersonal.mockResolvedValue({ favorites: [], recent: ["Recent", "Other", "Mine"] });
    const toggle = renderHook(() => useToggleFavoritePhrase("treatment_plan"), { wrapper });
    await act(async () => {
      await toggle.result.current.mutateAsync({ text: "Mine", favorite: false });
    });
    expect(removeFavorite).toHaveBeenCalledWith("treatment_plan", "Mine");
    await waitFor(() => expect(personal.result.current.data?.favorites).toEqual([]));
  });

  it("surfaces the server's rejection so the caller can show why (and changes nothing)", async () => {
    addFavorite.mockRejectedValue(new Error("422"));
    const { wrapper } = setup();
    const personal = renderHook(() => usePersonalSuggestions("chief_complaint", true), { wrapper });
    await waitFor(() => expect(personal.result.current.data).toBeDefined());
    const toggle = renderHook(() => useToggleFavoritePhrase("chief_complaint"), { wrapper });
    await act(async () => {
      await expect(toggle.result.current.mutateAsync({ text: "bad", favorite: true })).rejects.toThrow("422");
    });
    expect(personal.result.current.data).toEqual({ favorites: ["Mine"], recent: ["Recent", "Other"] });
  });
});
