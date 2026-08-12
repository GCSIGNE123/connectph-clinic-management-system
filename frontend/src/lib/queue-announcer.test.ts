import { describe, expect, it } from "vitest";
import { buildAnnouncementText } from "./queue-announcer";

describe("buildAnnouncementText", () => {
  it("uses the room label when one is configured, even if a doctor is also assigned", () => {
    const text = buildAnnouncementText("A001", { doctorName: "Aurora Canora", roomName: "Room #1" });
    expect(text).toBe("Now serving Patient A001, please proceed to Room #1.");
  });

  it("never speaks the doctor's name once a room is configured", () => {
    const text = buildAnnouncementText("A004", { doctorName: "Carlos Mendoza", roomName: "Room #2" });
    expect(text).toBe("Now serving Patient A004, please proceed to Room #2.");
    expect(text).not.toContain("Carlos Mendoza");
  });

  it("uses the room label for a department-only ticket too", () => {
    const text = buildAnnouncementText("L006", { departmentName: "Laboratory", roomName: "Room 103" });
    expect(text).toBe("Now serving Patient L006, please proceed to Room 103.");
  });

  it("falls back to the doctor name when no room is configured", () => {
    const text = buildAnnouncementText("A001", { doctorName: "Aurora Canora", roomName: null });
    expect(text).toBe("Now serving Patient A001, please proceed to Dr. Aurora Canora.");
  });

  it("falls back to the department name when no room and no doctor (Laboratory)", () => {
    const text = buildAnnouncementText("L006", { departmentName: "Laboratory" });
    expect(text).toBe("Now serving Patient L006, please proceed to the Laboratory.");
  });

  it("falls back to the department name when no room and no doctor (Radiology)", () => {
    const text = buildAnnouncementText("R001", { departmentName: "Radiology" });
    expect(text).toBe("Now serving Patient R001, please proceed to the Radiology.");
  });

  it("keeps the original unadorned phrasing for existing non-TV callers (no destination info at all)", () => {
    const text = buildAnnouncementText("A001");
    expect(text).toBe("Now serving Patient A001");
  });
});
