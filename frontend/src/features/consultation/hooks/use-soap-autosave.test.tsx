import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useSoapAutosave, changedSoapFields } from "./use-soap-autosave";

const saveSoap = vi.fn();
vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: { saveSoap: (...args: unknown[]) => saveSoap(...args) },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const BASELINE = {
  chiefComplaint: "Cough",
  historyOfPresentIllness: "HPI by reception",
  clinicalImpression: "Viral URI",
  treatmentPlan: "Rest and fluids",
  pulseRate: 76,
};

beforeEach(() => {
  saveSoap.mockReset().mockResolvedValue({ id: "c1", visitId: "v1", soapNote: null });
});
afterEach(() => vi.useRealTimers());

function hook(consultationId: string | null = "c1") {
  return renderHook(({ id }) => useSoapAutosave(id, true), { wrapper, initialProps: { id: consultationId } });
}

const lastPayload = () => saveSoap.mock.calls.at(-1)?.[1];

describe("useSoapAutosave dirty tracking", () => {
  it("starts idle, becomes unsaved after edit, and saved after a matching initialize", () => {
    const { result } = hook();

    act(() => result.current.initialize({ chiefComplaint: "Fever" }));
    expect(result.current.status).toBe("idle");
    expect(result.current.isDirty).toBe(false);

    act(() => result.current.setValues({ chiefComplaint: "Fever and cough" }));
    expect(result.current.status).toBe("unsaved");
    expect(result.current.isDirty).toBe(true);

    act(() => result.current.setValues({ chiefComplaint: "Fever" }));
    // Back to the baseline - dirty tracking should reflect that, not just "any edit ever happened".
    expect(result.current.isDirty).toBe(false);
  });

  it("does not call the API when saveNow is invoked while not dirty", () => {
    const { result } = hook(null);
    act(() => result.current.saveNow());
    // No consultationId - guarded, should not throw.
    expect(result.current.status).toBe("idle");
    expect(saveSoap).not.toHaveBeenCalled();
  });
});

describe("useSoapAutosave changed-fields-only payload (Task #6 race fix)", () => {
  it("sends ONLY the field the Doctor changed - never a full snapshot", async () => {
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    // Reception saves a different Subjective field on the server meanwhile (the Doctor's page doesn't know).
    act(() => result.current.setValues({ ...BASELINE, treatmentPlan: "Rest, fluids and paracetamol" }));
    await act(async () => result.current.saveNow());

    expect(saveSoap).toHaveBeenCalledTimes(1);
    expect(lastPayload()).toEqual({ treatmentPlan: "Rest, fluids and paracetamol" });
    // Nothing the Doctor did not touch is in the request - so Reception's newer HPI / chief complaint cannot be overwritten.
    for (const key of ["chiefComplaint", "historyOfPresentIllness", "clinicalImpression", "pulseRate"]) {
      expect(lastPayload()).not.toHaveProperty(key);
    }
  });

  it("the 30-second timer sends nothing when the Doctor changed nothing", async () => {
    vi.useFakeTimers();
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    await act(async () => vi.advanceTimersByTimeAsync(31_000));
    expect(saveSoap).not.toHaveBeenCalled();
    expect(result.current.isDirty).toBe(false);
  });

  it("the 30-second timer sends only the changed field when there is one", async () => {
    vi.useFakeTimers();
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "Cough and colds" }));
    await act(async () => vi.advanceTimersByTimeAsync(31_000));
    expect(saveSoap).toHaveBeenCalledTimes(1);
    expect(lastPayload()).toEqual({ chiefComplaint: "Cough and colds" });
  });

  it("a field changed and then put back to its baseline is not sent (and is not dirty)", async () => {
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "Something else" }));
    expect(result.current.isDirty).toBe(true);
    act(() => result.current.setValues({ ...BASELINE }));
    expect(result.current.isDirty).toBe(false);
    await act(async () => result.current.saveNow());
    expect(saveSoap).not.toHaveBeenCalled();
  });

  it("treats null / undefined / empty string as the same 'empty' value", () => {
    expect(changedSoapFields({ chiefComplaint: null }, { chiefComplaint: "" })).toEqual({});
    expect(changedSoapFields({}, { chiefComplaint: "" })).toEqual({});
    expect(changedSoapFields({ chiefComplaint: "" }, { chiefComplaint: undefined })).toEqual({});
    // ...but clearing an existing value IS a change, sent as-is so it clears the field.
    expect(changedSoapFields({ chiefComplaint: "Cough" }, { chiefComplaint: "" })).toEqual({ chiefComplaint: "" });
    expect(changedSoapFields({ chiefComplaint: "Cough" }, { chiefComplaint: null })).toEqual({ chiefComplaint: null });
  });

  it("handles numeric vitals: a real change is sent, an identical number is not", () => {
    expect(changedSoapFields({ pulseRate: 76, temperature: 36.8 }, { pulseRate: 80, temperature: 36.8 })).toEqual({ pulseRate: 80 });
    expect(changedSoapFields({ pulseRate: 76 }, { pulseRate: null })).toEqual({ pulseRate: null });
    expect(changedSoapFields({ pulseRate: null }, { pulseRate: 0 })).toEqual({ pulseRate: 0 }); // 0 is a real reading, not "empty"
  });

  it("a keys that is simply absent from the current values is not a change", () => {
    expect(changedSoapFields({ chiefComplaint: "Cough", pulseRate: 76 }, { chiefComplaint: "Cough" })).toEqual({});
  });

  it("after a successful save the baseline moves on: the next save carries only the NEW change", async () => {
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "First edit" }));
    await act(async () => result.current.saveNow());
    expect(lastPayload()).toEqual({ chiefComplaint: "First edit" });
    expect(result.current.status).toBe("saved");
    expect(result.current.isDirty).toBe(false);

    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "First edit", treatmentPlan: "Second edit" }));
    await act(async () => result.current.saveNow());
    expect(saveSoap).toHaveBeenCalledTimes(2);
    expect(lastPayload()).toEqual({ treatmentPlan: "Second edit" });
  });

  it("an edit made while a save is in flight stays dirty and is sent next time", async () => {
    let resolve!: (v: unknown) => void;
    saveSoap.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "A" }));
    act(() => result.current.saveNow());
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "A", treatmentPlan: "B" })); // typed during the request
    await act(async () => resolve({ id: "c1", visitId: "v1", soapNote: null }));
    expect(result.current.isDirty).toBe(true);
    expect(result.current.status).toBe("unsaved");
    await act(async () => result.current.saveNow());
    expect(lastPayload()).toEqual({ treatmentPlan: "B" });
  });

  it("Save Progress (saveNow) and autosave use the exact same partial payload", async () => {
    vi.useFakeTimers();
    const { result } = hook();
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, patientInstructions: "Return in 3 days" }));
    await act(async () => result.current.saveNow()); // what the Save Progress button calls
    const viaButton = lastPayload();
    saveSoap.mockClear();

    const second = hook("c2");
    act(() => second.result.current.initialize(BASELINE));
    act(() => second.result.current.setValues({ ...BASELINE, patientInstructions: "Return in 3 days" }));
    await act(async () => vi.advanceTimersByTimeAsync(31_000)); // the timer path
    expect(lastPayload()).toEqual(viaButton);
    expect(viaButton).toEqual({ patientInstructions: "Return in 3 days" });
  });

  it("switching consultations resets the baseline (no stale diff, nothing leaks across consultations)", async () => {
    const { result, rerender } = hook("c1");
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "Edited in c1" }));
    expect(result.current.isDirty).toBe(true);

    rerender({ id: "c2" });
    act(() => result.current.initialize({ chiefComplaint: "Other patient", treatmentPlan: "Other plan" }));
    expect(result.current.isDirty).toBe(false);
    expect(result.current.status).toBe("idle");
    await act(async () => result.current.saveNow());
    expect(saveSoap).not.toHaveBeenCalled();

    act(() => result.current.setValues({ chiefComplaint: "Other patient", treatmentPlan: "Changed in c2" }));
    await act(async () => result.current.saveNow());
    expect(saveSoap).toHaveBeenCalledWith("c2", { treatmentPlan: "Changed in c2" });
  });

  it("a save that finishes after switching consultations does not disturb the new baseline", async () => {
    let resolve!: (v: unknown) => void;
    saveSoap.mockReturnValueOnce(new Promise((r) => (resolve = r)));
    const { result, rerender } = hook("c1");
    act(() => result.current.initialize({ chiefComplaint: "c1 value" }));
    act(() => result.current.setValues({ chiefComplaint: "c1 edited" }));
    act(() => result.current.saveNow());

    rerender({ id: "c2" });
    act(() => result.current.initialize({ chiefComplaint: "c2 value" }));
    act(() => result.current.setValues({ chiefComplaint: "c2 edited" }));
    await act(async () => resolve({ id: "c1", visitId: "v1", soapNote: null }));
    // c2's own unsaved edit is still dirty - the late c1 response did not overwrite c2's baseline.
    expect(result.current.isDirty).toBe(true);
  });

  it("does not save when the user cannot edit", async () => {
    const { result } = renderHook(() => useSoapAutosave("c1", false), { wrapper });
    act(() => result.current.initialize(BASELINE));
    act(() => result.current.setValues({ ...BASELINE, chiefComplaint: "x" }));
    await act(async () => result.current.saveNow());
    expect(saveSoap).not.toHaveBeenCalled();
  });
});
