import { beforeEach, describe, expect, it, vi } from "vitest";
import { consultationApi } from "./consultation-api";

const putMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: (...a: unknown[]) => putMock(...a) },
  apiFetchBlob: vi.fn(),
}));

const RAW_CONSULTATION = {
  id: "c1", visit_id: "v1", branch_id: "b1", doctor_id: "d1", patient_id: "p1", status: "InProgress",
  started_at: "2026-01-01T00:00:00Z", lock: { locked: false }, soap_note: null, diagnoses: [], attachments: [],
};

beforeEach(() => putMock.mockReset().mockResolvedValue(RAW_CONSULTATION));
const body = () => putMock.mock.calls.at(-1)?.[1] as Record<string, unknown>;
const url = () => String(putMock.mock.calls.at(-1)?.[0]);

describe("consultationApi SOAP payloads send only the keys supplied (Task #6)", () => {
  it("saveSoap omits every field the caller did not supply (no implicit nulls that would wipe stored values)", async () => {
    await consultationApi.saveSoap("c1", { treatmentPlan: "Rest" });
    expect(url()).toBe("/consultations/c1/soap");
    expect(body()).toEqual({ treatment_plan: "Rest" });
  });

  it("an explicit null is kept (it means 'clear this field'); empty string is sent as-is", async () => {
    await consultationApi.saveSoap("c1", { chiefComplaint: null, familyHistory: "", pulseRate: 0 });
    expect(body()).toEqual({ chief_complaint: null, family_history: "", pulse_rate: 0 });
  });

  it("saveSubjectiveObjective sends only supplied Subjective/Objective keys, in API naming", async () => {
    await consultationApi.saveSubjectiveObjective("c1", { chiefComplaint: "Cough", painScore: 3, headCircumferenceCm: 54.5 });
    expect(url()).toBe("/consultations/c1/soap/subjective-objective");
    expect(body()).toEqual({ chief_complaint: "Cough", pain_score: 3, head_circumference_cm: 54.5 });
  });

  it("saveSubjectiveObjective never sends Doctor-only fields, even if a caller passes them", async () => {
    await consultationApi.saveSubjectiveObjective("c1", {
      chiefComplaint: "Cough",
      physicalExamination: "x", clinicalFindings: "x", clinicalImpression: "x", differentialDiagnosis: "x",
      assessmentNotes: "x", treatmentPlan: "x", patientInstructions: "x", followupRecommendation: "x", referralNotes: "x",
    });
    expect(Object.keys(body())).toEqual(["chief_complaint"]);
  });

  it("every approved Subjective and vitals field can be sent", async () => {
    await consultationApi.saveSubjectiveObjective("c1", {
      chiefComplaint: "a", historyOfPresentIllness: "b", pastMedicalHistory: "c", familyHistory: "d", socialHistory: "e",
      reviewOfSystems: "f", subjectiveNotes: "g", bloodPressure: "120/80", pulseRate: 70, respiratoryRate: 16,
      temperature: 36.5, heightCm: 170, weightKg: 65, oxygenSaturation: 98, painScore: 2, headCircumferenceCm: 50,
    });
    expect(Object.keys(body()).sort()).toEqual(
      [
        "chief_complaint", "history_of_present_illness", "past_medical_history", "family_history", "social_history",
        "review_of_systems", "subjective_notes", "blood_pressure", "pulse_rate", "respiratory_rate", "temperature",
        "height_cm", "weight_kg", "oxygen_saturation", "pain_score", "head_circumference_cm",
      ].sort()
    );
  });
});
