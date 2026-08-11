import { describe, expect, it } from "vitest";
import { buildAnnouncementText } from "./queue-announcer";

describe("buildAnnouncementText", () => {
  it("uses the room label when one is configured, even if a doctor is also assigned", () => {
    const text = buildAnnouncementText("A001", { doctorName: "Aurora Canora", roomName: "Room 101" });
    expect(text).toBe("Now serving patient number A001. Please proceed to Room 101.");
  });

  it("uses the room label for a department-only ticket too", () => {
    const text = buildAnnouncementText("L006", { departmentName: "Laboratory", roomName: "Room 103" });
    expect(text).toBe("Now serving patient number L006. Please proceed to Room 103.");
  });

  it("falls back to the doctor name when no room is configured", () => {
    const text = buildAnnouncementText("A001", { doctorName: "Aurora Canora", roomName: null });
    expect(text).toBe("Now serving patient number A001. Please proceed to Dr. Aurora Canora.");
  });

  it("falls back to the department name when no room and no doctor", () => {
    const text = buildAnnouncementText("L006", { departmentName: "Laboratory" });
    expect(text).toBe("Now serving patient number L006. Please proceed to the Laboratory.");
  });

  it("keeps the original unadorned phrasing for existing non-TV callers (no destination info at all)", () => {
    const text = buildAnnouncementText("A001");
    expect(text).toBe("Now serving patient number A001");
  });
});
