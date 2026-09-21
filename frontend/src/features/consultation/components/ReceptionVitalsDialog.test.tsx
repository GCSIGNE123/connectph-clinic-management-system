import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReceptionVitalsDialog } from "./ReceptionVitalsDialog";

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

const mockOpenForReception = vi.fn();
const mockGetSubjectiveObjective = vi.fn();
const mockSaveSubjectiveObjective = vi.fn();
vi.mock("@/features/consultation/api/consultation-api", () => ({
  consultationApi: {
    openForReception: (...args: unknown[]) => mockOpenForReception(...args),
    getSubjectiveObjective: (...args: unknown[]) => mockGetSubjectiveObjective(...args),
    saveSubjectiveObjective: (...args: unknown[]) => mockSaveSubjectiveObjective(...args),
  },
}));

// Task #2 suggestions (Chief complaint is the only suggestion field inside the reception scope).
const useSoapSuggestionsMock = vi.fn();
vi.mock("@/features/consultation/hooks/use-soap-suggestions", () => ({
  useSoapSuggestions: (field: string, enabled: boolean) => useSoapSuggestionsMock(field, enabled),
}));

function renderDialog(onSaved = vi.fn()) {
  return render(
    <ReceptionVitalsDialog open onOpenChange={vi.fn()} visitId="visit-1" patientName="Juan Dela Cruz" onSaved={onSaved} />
  );
}

const inputFor = async (label: string) => (await screen.findByText(label)).parentElement!.querySelector("input")!;
const textareaFor = async (label: string) => (await screen.findByText(label)).parentElement!.querySelector("textarea")!;
const payload = () => mockSaveSubjectiveObjective.mock.calls[0][1];

describe("ReceptionVitalsDialog - optional vitals fields", () => {
  beforeEach(() => {
    mockOpenForReception.mockReset().mockResolvedValue({ id: "consult-1" });
    mockGetSubjectiveObjective.mockReset().mockResolvedValue(null);
    mockSaveSubjectiveObjective.mockReset().mockResolvedValue({ id: "consult-1" });
    useSoapSuggestionsMock.mockReset().mockReturnValue({ data: [] });
  });

  it("A: saves successfully with only Temperature filled in - and sends ONLY that field", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    renderDialog(onSaved);

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Temperature (°C)"), "36.5");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    // Task #6: unsupplied fields are omitted (they used to be sent as null, which wiped stored values).
    expect(payload()).toEqual({ temperature: 36.5 });
    expect(onSaved).toHaveBeenCalled();
  });

  it("B: saves successfully with only Blood pressure filled in", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Blood pressure"), "120/80");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ bloodPressure: "120/80" });
  });

  it("C: saves successfully with only Chief complaint filled in", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await textareaFor("Chief complaint"), "Headache");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ chiefComplaint: "Headache" });
  });

  it("D: saves successfully with multiple, but not all, partial fields", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Pulse rate (bpm)"), "72");
    await user.type(await inputFor("Temperature (°C)"), "37.0");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ pulseRate: 72, temperature: 37 });
  });

  it("E: rejects save with a clear message when every field is empty", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    expect(await screen.findByText("Enter at least one vital sign or chief complaint before saving.")).toBeInTheDocument();
    expect(mockSaveSubjectiveObjective).not.toHaveBeenCalled();
  });

  it("G: still saves a fully-filled-in vitals entry (existing complete-entry behavior unchanged)", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Blood pressure"), "110/70");
    await user.type(await inputFor("Pulse rate (bpm)"), "80");
    await user.type(await inputFor("Respiratory rate"), "18");
    await user.type(await inputFor("Temperature (°C)"), "36.8");
    await user.type(await inputFor("Height (cm)"), "170");
    await user.type(await inputFor("Weight (kg)"), "65");
    await user.type(await inputFor("O2 saturation (%)"), "98");

    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({
      bloodPressure: "110/70", pulseRate: 80, respiratoryRate: 18,
      temperature: 36.8, heightCm: 170, weightKg: 65, oxygenSaturation: 98,
    });
  });

  it("does not render a required-field asterisk on any now-optional vitals label", async () => {
    renderDialog();
    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    for (const label of [
      "Blood pressure", "Pulse rate (bpm)", "Respiratory rate",
      "Temperature (°C)", "Height (cm)", "Weight (kg)", "O2 saturation (%)",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
      expect(screen.queryByText(`${label} *`)).not.toBeInTheDocument();
    }
  });
});

describe("ReceptionVitalsDialog - approved pre-entry scope (Task #6)", () => {
  beforeEach(() => {
    mockOpenForReception.mockReset().mockResolvedValue({ id: "consult-1" });
    mockGetSubjectiveObjective.mockReset().mockResolvedValue(null);
    mockSaveSubjectiveObjective.mockReset().mockResolvedValue({ id: "consult-1" });
    useSoapSuggestionsMock.mockReset().mockReturnValue({ data: [] });
  });

  it("shows all seven approved Subjective fields", async () => {
    renderDialog();
    for (const label of [
      "Chief complaint", "History of present illness", "Past medical history", "Family history",
      "Social history", "Review of systems", "Subjective notes",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
      expect((await textareaFor(label)).tagName).toBe("TEXTAREA");
    }
  });

  it("shows all approved vitals, including pain score and head circumference", async () => {
    renderDialog();
    for (const label of [
      "Blood pressure", "Pulse rate (bpm)", "Respiratory rate", "Temperature (°C)", "Height (cm)", "Weight (kg)",
      "O2 saturation (%)", "Pain score (0-10)", "Head circumference (cm)",
    ]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
  });

  it("offers NO Doctor-only fields (physical exam, findings, Assessment, Plan, ICD-10)", async () => {
    renderDialog();
    await screen.findByText("Chief complaint");
    for (const label of [
      "Physical examination", "Clinical findings", "Clinical impression", "Differential diagnosis", "Assessment notes",
      "Treatment plan", "Patient instructions", "Follow-up recommendation", "Referral notes", "ICD-10 code", "ICD-10 description",
    ]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox", { name: /impression|treatment|assessment|referral|physical|findings|icd/i })).not.toBeInTheDocument();
  });

  it("loads existing values into every field (Doctor-entered and previous pre-entry)", async () => {
    mockGetSubjectiveObjective.mockResolvedValue({
      chiefComplaint: "Cough", historyOfPresentIllness: "3 days", pastMedicalHistory: "Asthma", familyHistory: "HTN",
      socialHistory: "Non-smoker", reviewOfSystems: "No chest pain", subjectiveNotes: "Note",
      bloodPressure: "120/80", pulseRate: 76, respiratoryRate: 18, temperature: 36.8, heightCm: 170, weightKg: 65,
      oxygenSaturation: 98, painScore: 3, headCircumferenceCm: 54.5,
    });
    renderDialog();
    await waitFor(() => expect(mockGetSubjectiveObjective).toHaveBeenCalled());
    expect(await textareaFor("Chief complaint")).toHaveValue("Cough");
    expect(await textareaFor("History of present illness")).toHaveValue("3 days");
    expect(await textareaFor("Past medical history")).toHaveValue("Asthma");
    expect(await textareaFor("Family history")).toHaveValue("HTN");
    expect(await textareaFor("Social history")).toHaveValue("Non-smoker");
    expect(await textareaFor("Review of systems")).toHaveValue("No chest pain");
    expect(await textareaFor("Subjective notes")).toHaveValue("Note");
    expect(await inputFor("Blood pressure")).toHaveValue("120/80");
    expect(await inputFor("Pain score (0-10)")).toHaveValue(3);
    expect(await inputFor("Head circumference (cm)")).toHaveValue(54.5);
  });

  it("saves only what THIS user changed - untouched loaded fields are not re-sent (cannot overwrite the Doctor)", async () => {
    const user = userEvent.setup();
    mockGetSubjectiveObjective.mockResolvedValue({
      chiefComplaint: "Cough", historyOfPresentIllness: "Doctor's HPI", temperature: 36.8, pulseRate: 76,
    });
    renderDialog();
    await waitFor(() => expect(mockGetSubjectiveObjective).toHaveBeenCalled());
    await waitFor(async () => expect(await textareaFor("Chief complaint")).toHaveValue("Cough"));

    await user.type(await inputFor("Respiratory rate"), "18");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ respiratoryRate: 18 }); // no chiefComplaint / HPI / temperature / pulse
  });

  it("clearing a loaded value sends an explicit null for that field only", async () => {
    const user = userEvent.setup();
    mockGetSubjectiveObjective.mockResolvedValue({ chiefComplaint: "Cough", familyHistory: "HTN" });
    renderDialog();
    await waitFor(async () => expect(await textareaFor("Family history")).toHaveValue("HTN"));

    await user.clear(await textareaFor("Family history"));
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ familyHistory: null });
  });

  it("saves every approved Subjective field and vital together, in one request", async () => {
    const user = userEvent.setup();
    renderDialog();
    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    const text: Record<string, string> = {
      "History of present illness": "hpi", "Past medical history": "pmh", "Family history": "fh",
      "Social history": "sh", "Review of systems": "ros", "Subjective notes": "notes",
    };
    for (const [label, value] of Object.entries(text)) await user.type(await textareaFor(label), value);
    await user.type(await textareaFor("Chief complaint"), "cc");
    await user.type(await inputFor("Pain score (0-10)"), "4");
    await user.type(await inputFor("Head circumference (cm)"), "50.5");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({
      chiefComplaint: "cc", historyOfPresentIllness: "hpi", pastMedicalHistory: "pmh", familyHistory: "fh",
      socialHistory: "sh", reviewOfSystems: "ros", subjectiveNotes: "notes", painScore: 4, headCircumferenceCm: 50.5,
    });
  });

  it("shows the backend's message when the save fails (e.g. a signed consultation)", async () => {
    const user = userEvent.setup();
    mockSaveSubjectiveObjective.mockRejectedValue(new Error("Cannot edit a signed consultation."));
    renderDialog();
    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    await user.type(await inputFor("Temperature (°C)"), "36.5");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));
    expect(await screen.findByText("Could not save. The consultation may already be signed.")).toBeInTheDocument();
  });

  it("the form scrolls inside the dialog (bounded height) instead of growing off-screen", async () => {
    renderDialog();
    await screen.findByText("Chief complaint");
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toMatch(/max-h-\[90vh\]/);
    expect(dialog.className).toMatch(/overflow-y-auto/);
    expect(dialog.className).toMatch(/max-w-2xl/);
  });
});

describe("ReceptionVitalsDialog - Chief complaint suggestions reuse Task #2 (Task #6)", () => {
  beforeEach(() => {
    mockOpenForReception.mockReset().mockResolvedValue({ id: "consult-1" });
    mockGetSubjectiveObjective.mockReset().mockResolvedValue(null);
    mockSaveSubjectiveObjective.mockReset().mockResolvedValue({ id: "consult-1" });
    useSoapSuggestionsMock.mockReset().mockReturnValue({ data: ["Persistent dry cough"] });
  });

  it("requests suggestions for chief_complaint only - no other (Doctor-only) suggestion field", async () => {
    renderDialog();
    await screen.findByText("Chief complaint");
    const fields = new Set(useSoapSuggestionsMock.mock.calls.map((c) => c[0]));
    expect(fields).toEqual(new Set(["chief_complaint"]));
  });

  it("shows learned suggestions first, then the static starters, on focus", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(await textareaFor("Chief complaint"));
    const list = (await screen.findByRole("button", { name: "Persistent dry cough" })).closest("ul") as HTMLElement;
    const labels = within(list).getAllByRole("button").map((b) => b.textContent);
    expect(labels[0]).toBe("Persistent dry cough");
    expect(labels).toContain("Fever");
  });

  it("selecting a suggestion fills the field, stays editable, and is saved", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(await textareaFor("Chief complaint"));
    await user.click(await screen.findByRole("button", { name: "Persistent dry cough" }));
    expect(await textareaFor("Chief complaint")).toHaveValue("Persistent dry cough");
    await user.type(await textareaFor("Chief complaint"), ", 2 weeks");
    expect(await textareaFor("Chief complaint")).toHaveValue("Persistent dry cough, 2 weeks");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));
    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(payload()).toEqual({ chiefComplaint: "Persistent dry cough, 2 weeks" });
  });

  it("completely custom text is accepted without any suggestion", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(await textareaFor("Chief complaint"), "Something not in any list");
    expect(await textareaFor("Chief complaint")).toHaveValue("Something not in any list");
  });

  it("the other Subjective fields are plain textareas with no suggestion list", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(await textareaFor("History of present illness"));
    expect(screen.queryByRole("button", { name: "Persistent dry cough" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fever" })).not.toBeInTheDocument();
  });
});
