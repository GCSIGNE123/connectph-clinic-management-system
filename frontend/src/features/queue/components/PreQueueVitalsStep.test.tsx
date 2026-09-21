import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PreQueueVitalsStep } from "./PreQueueVitalsStep";

vi.mock("@/components/ui/toast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

const mockOpenForReception = vi.fn();
const mockGetSubjectiveObjective = vi.fn();
const mockSaveSubjectiveObjective = vi.fn();
vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    openForReception: (...a: unknown[]) => mockOpenForReception(...a),
    getSubjectiveObjective: (...a: unknown[]) => mockGetSubjectiveObjective(...a),
    saveSubjectiveObjective: (...a: unknown[]) => mockSaveSubjectiveObjective(...a),
  },
}));

const useSoapSuggestionsMock = vi.fn();
vi.mock("@/features/consultation/hooks/use-soap-suggestions", () => ({
  useSoapSuggestions: (field: string, enabled: boolean) => useSoapSuggestionsMock(field, enabled),
}));

const inputFor = async (label: string) => (await screen.findByText(label)).parentElement!.querySelector("input")!;
const textareaFor = async (label: string) => (await screen.findByText(label)).parentElement!.querySelector("textarea")!;

const REQUIRED = [
  ["Blood pressure *", "120/80"], ["Pulse rate (bpm) *", "76"], ["Respiratory rate *", "18"], ["Temperature (°C) *", "36.8"],
  ["Height (cm) *", "170"], ["Weight (kg) *", "68"], ["SpO2 (%) *", "98"],
] as const;

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  for (const [label, value] of REQUIRED) await user.type(await inputFor(label), value);
}

function renderStep(onSaved = vi.fn(), onBack = vi.fn()) {
  render(<PreQueueVitalsStep visitId="visit-1" onSaved={onSaved} onBack={onBack} />);
  return { onSaved, onBack };
}

describe("PreQueueVitalsStep (Task #6: pre-queue intake, before the ticket exists)", () => {
  beforeEach(() => {
    mockOpenForReception.mockReset().mockResolvedValue({ id: "consult-1" });
    mockGetSubjectiveObjective.mockReset().mockResolvedValue(null);
    mockSaveSubjectiveObjective.mockReset().mockResolvedValue({ id: "consult-1" });
    useSoapSuggestionsMock.mockReset().mockReturnValue({ data: ["Persistent dry cough"] });
  });

  it("renders the approved Subjective fields and all vitals", async () => {
    renderStep();
    for (const label of [
      "Chief complaint", "History of present illness", "Past medical history", "Family history", "Social history",
      "Review of systems", "Subjective notes",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    for (const [label] of REQUIRED) expect(await screen.findByText(label)).toBeInTheDocument();
    expect(await screen.findByText("Pain score (0-10, optional)")).toBeInTheDocument();
    expect(await screen.findByText("Head circumference (cm, optional)")).toBeInTheDocument();
    expect(await screen.findByText("BMI (auto-computed)")).toBeInTheDocument();
  });

  it("offers no Doctor-only fields", async () => {
    renderStep();
    await screen.findByText("Chief complaint");
    for (const label of [
      "Physical examination", "Clinical findings", "Clinical impression", "Differential diagnosis", "Assessment notes",
      "Treatment plan", "Patient instructions", "Follow-up recommendation", "Referral notes", "ICD-10 code",
    ]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("keeps the required-vitals gate: it does not save until every required vital is entered", async () => {
    const user = userEvent.setup();
    renderStep();
    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Temperature (°C) *"), "36.5");
    await user.click(screen.getByRole("button", { name: "Save and Close" }));
    expect(await screen.findByText("Please fill in all required vitals before saving.")).toBeInTheDocument();
    expect(mockSaveSubjectiveObjective).not.toHaveBeenCalled();
  });

  it("saves the entered fields (and only those) and reports success without touching the queue", async () => {
    const user = userEvent.setup();
    const { onSaved } = renderStep();
    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await fillRequired(user);
    await user.type(await textareaFor("History of present illness"), "3 days");
    await user.type(await inputFor("Pain score (0-10, optional)"), "2");
    await user.click(screen.getByRole("button", { name: "Save and Close" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][0]).toBe("consult-1");
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toEqual({
      bloodPressure: "120/80", pulseRate: 76, respiratoryRate: 18, temperature: 36.8, heightCm: 170, weightKg: 68,
      oxygenSaturation: 98, historyOfPresentIllness: "3 days", painScore: 2,
    });
    expect(onSaved).toHaveBeenCalled();
    expect(mockOpenForReception).toHaveBeenCalledTimes(1); // no extra visit/queue calls from this step
  });

  it("does not resend loaded values it did not change, and shows the live BMI", async () => {
    const user = userEvent.setup();
    mockGetSubjectiveObjective.mockResolvedValue({
      chiefComplaint: "Cough", historyOfPresentIllness: "Earlier note", bloodPressure: "110/70", pulseRate: 70,
      respiratoryRate: 16, temperature: 36.6, heightCm: 170, weightKg: 68, oxygenSaturation: 99,
    });
    renderStep();
    await waitFor(async () => expect(await textareaFor("Chief complaint")).toHaveValue("Cough"));
    expect(await inputFor("BMI (auto-computed)")).toHaveValue("23.53");
    await user.type(await textareaFor("Subjective notes"), "New note");
    await user.click(screen.getByRole("button", { name: "Save and Close" }));
    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toEqual({ subjectiveNotes: "New note" });
  });

  it("Chief complaint reuses the Task #2 suggestions (and only that field asks for them); custom text still works", async () => {
    const user = userEvent.setup();
    renderStep();
    await user.click(await textareaFor("Chief complaint"));
    await user.click(await screen.findByRole("button", { name: "Persistent dry cough" }));
    expect(await textareaFor("Chief complaint")).toHaveValue("Persistent dry cough");
    await user.type(await textareaFor("Chief complaint"), " today");
    expect(await textareaFor("Chief complaint")).toHaveValue("Persistent dry cough today");
    expect(new Set(useSoapSuggestionsMock.mock.calls.map((c) => c[0]))).toEqual(new Set(["chief_complaint"]));
  });

  it("shows the backend's reason when opening the consultation fails (e.g. no doctor assigned)", async () => {
    const { ApiError } = await import("@/lib/api-client");
    mockOpenForReception.mockRejectedValue(new ApiError({ message: "This visit has no doctor assigned yet.", statusCode: 400 }));
    renderStep();
    expect(await screen.findByText("This visit has no doctor assigned yet.")).toBeInTheDocument();
  });

  it("Close calls onBack", async () => {
    const user = userEvent.setup();
    const { onBack } = renderStep();
    await user.click(await screen.findByRole("button", { name: "Close" }));
    expect(onBack).toHaveBeenCalled();
  });
});
