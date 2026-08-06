import { describe, expect, test } from "vitest";
import { deriveInitials, formatTtsTemplate } from "./format";

describe("deriveInitials", () => {
  test("derives initials from first and last name", () => {
    expect(deriveInitials("Juan", "Dela Cruz")).toBe("JD");
  });

  test("uppercases lowercase input", () => {
    expect(deriveInitials("maria", "santos")).toBe("MS");
  });

  test("falls back to ?? when both names are empty", () => {
    expect(deriveInitials("", "")).toBe("??");
  });

  test("handles a missing last name gracefully", () => {
    expect(deriveInitials("Juan", "")).toBe("J");
  });
});

describe("formatTtsTemplate", () => {
  test("fills in the default template", () => {
    expect(formatTtsTemplate(null, { queueNumber: "A001", room: "Room 2" })).toBe(
      "Queue A001, please proceed to Room 2."
    );
  });

  test("uses a custom template with multiple placeholders", () => {
    const result = formatTtsTemplate("{queue_number} for {doctor} in {room} ({patient_initials})", {
      queueNumber: "A002",
      room: "Room 1",
      doctor: "Santos",
      patientInitials: "JD",
    });
    expect(result).toBe("A002 for Santos in Room 1 (JD)");
  });

  test("falls back to 'the counter' when room is missing", () => {
    expect(formatTtsTemplate(null, { queueNumber: "A003" })).toBe("Queue A003, please proceed to the counter.");
  });
});
