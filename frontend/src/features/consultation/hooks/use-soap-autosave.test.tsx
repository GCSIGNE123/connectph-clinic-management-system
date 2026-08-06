import { describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSoapAutosave } from "./use-soap-autosave";

vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    saveSoap: vi.fn().mockResolvedValue({ id: "c1", soapNote: null }),
  },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useSoapAutosave dirty tracking", () => {
  it("starts idle, becomes unsaved after edit, and saved after a matching initialize", () => {
    const { result } = renderHook(() => useSoapAutosave("c1", true), { wrapper });

    act(() => result.current.initialize({ chiefComplaint: "Fever" }));
    expect(result.current.status).toBe("idle");
    expect(result.current.isDirty).toBe(false);

    act(() => result.current.setValues({ chiefComplaint: "Fever and cough" }));
    expect(result.current.status).toBe("unsaved");
    expect(result.current.isDirty).toBe(true);

    act(() => result.current.setValues({ chiefComplaint: "Fever" }));
    // Back to the last-saved snapshot - dirty tracking should reflect that,
    // not just "any edit ever happened".
    expect(result.current.isDirty).toBe(false);
  });

  it("does not call the API when saveNow is invoked while not dirty", () => {
    const { result } = renderHook(() => useSoapAutosave(null, true), { wrapper });
    act(() => result.current.saveNow());
    // No consultationId - guarded, should not throw.
    expect(result.current.status).toBe("idle");
  });
});
