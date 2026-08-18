import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

function renderDialog(onSaved = vi.fn()) {
  return render(
    <ReceptionVitalsDialog open onOpenChange={vi.fn()} visitId="visit-1" patientName="Juan Dela Cruz" onSaved={onSaved} />
  );
}

describe("ReceptionVitalsDialog - optional vitals fields", () => {
  beforeEach(() => {
    mockOpenForReception.mockReset().mockResolvedValue({ id: "consult-1" });
    mockGetSubjectiveObjective.mockReset().mockResolvedValue(null);
    mockSaveSubjectiveObjective.mockReset().mockResolvedValue({ id: "consult-1" });
  });

  it("A: saves successfully with only Temperature filled in", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    renderDialog(onSaved);

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    const temperature = (await screen.findByText("Temperature (°C)")).parentElement!.querySelector("input")!;
    await user.type(temperature, "36.5");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    const payload = mockSaveSubjectiveObjective.mock.calls[0][1];
    expect(payload).toMatchObject({
      temperature: 36.5,
      chiefComplaint: null, bloodPressure: null, pulseRate: null,
      respiratoryRate: null, heightCm: null, weightKg: null, oxygenSaturation: null,
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it("B: saves successfully with only Blood pressure filled in", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    const bp = (await screen.findByText("Blood pressure")).parentElement!.querySelector("input")!;
    await user.type(bp, "120/80");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toMatchObject({ bloodPressure: "120/80", temperature: null });
  });

  it("C: saves successfully with only Chief complaint filled in", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    const chiefComplaint = (await screen.findByText("Chief complaint")).parentElement!.querySelector("textarea")!;
    await user.type(chiefComplaint, "Headache");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toMatchObject({ chiefComplaint: "Headache" });
  });

  it("D: saves successfully with multiple, but not all, partial fields", async () => {
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(mockOpenForReception).toHaveBeenCalled());
    const pulse = (await screen.findByText("Pulse rate (bpm)")).parentElement!.querySelector("input")!;
    const temperature = (await screen.findByText("Temperature (°C)")).parentElement!.querySelector("input")!;
    await user.type(pulse, "72");
    await user.type(temperature, "37.0");
    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toMatchObject({ pulseRate: 72, temperature: 37 });
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
    await user.type((await screen.findByText("Blood pressure")).parentElement!.querySelector("input")!, "110/70");
    await user.type(screen.getByText("Pulse rate (bpm)").parentElement!.querySelector("input")!, "80");
    await user.type(screen.getByText("Respiratory rate").parentElement!.querySelector("input")!, "18");
    await user.type(screen.getByText("Temperature (°C)").parentElement!.querySelector("input")!, "36.8");
    await user.type(screen.getByText("Height (cm)").parentElement!.querySelector("input")!, "170");
    await user.type(screen.getByText("Weight (kg)").parentElement!.querySelector("input")!, "65");
    await user.type(screen.getByText("O2 saturation (%)").parentElement!.querySelector("input")!, "98");

    await user.click(screen.getByRole("button", { name: "Save and Print" }));

    await waitFor(() => expect(mockSaveSubjectiveObjective).toHaveBeenCalledTimes(1));
    expect(mockSaveSubjectiveObjective.mock.calls[0][1]).toMatchObject({
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
