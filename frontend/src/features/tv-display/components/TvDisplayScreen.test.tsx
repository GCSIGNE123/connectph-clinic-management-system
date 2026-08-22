import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TvDisplayScreen } from "./TvDisplayScreen";
import type { TvDisplayData } from "@/features/tv-display/types";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

let mockData: TvDisplayData | null = null;
vi.mock("@/features/tv-display/hooks/use-tv-display-realtime", () => ({
  useTvDisplayRealtime: () => ({ data: mockData, error: null, connectionStatus: "connected" }),
}));

vi.mock("@/lib/api-url", () => ({
  getApiBaseUrl: () => "http://api.test/api/v1",
  resolveMediaUrl: (path: string | null) => (path ? `http://api.test${path}` : null),
}));

function displayData(overrides: Partial<TvDisplayData> = {}): TvDisplayData {
  return {
    displayName: "Main Display",
    clinicName: "Canora Medical Clinic & Laboratory",
    branchName: null,
    theme: "Dark",
    fontSize: "Medium",
    animationSpeed: "Normal",
    queueSize: 5,
    refreshIntervalSeconds: 30,
    logoUrl: null,
    primaryColor: null,
    secondaryColor: null,
    nowServing: [],
    nextWaiting: [],
    announcements: [],
    infoContent: [],
    serverTime: "2026-01-01T00:00:00Z",
    wsChannelClinicId: "clinic-1",
    wsAuthSlug: "slug-1",
    ...overrides,
  };
}

describe("TvDisplayScreen - clinic logo header (Round 7)", () => {
  it("6: shows the clinic logo BEFORE the clinic name when a logo is configured", () => {
    mockData = displayData({ logoUrl: "/media/clinic-logo/clinic-1/logo-abc123.png" });
    const { container } = render(<TvDisplayScreen slug="canora" />);

    const img = container.querySelector("header img") as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("src", "http://api.test/media/clinic-logo/clinic-1/logo-abc123.png");
    const clinicName = screen.getByText("Canora Medical Clinic & Laboratory");
    const header = clinicName.closest("header") as HTMLElement;
    const children = Array.from(header.querySelectorAll("*"));
    expect(children.indexOf(img)).toBeLessThan(children.indexOf(clinicName));
  });

  it("7: gracefully falls back to the text-only header when no logo is configured", () => {
    mockData = displayData({ logoUrl: null });
    const { container } = render(<TvDisplayScreen slug="canora" />);

    expect(container.querySelector("header img")).toBeNull();
    expect(screen.getByText("Canora Medical Clinic & Laboratory")).toBeInTheDocument();
  });

  it("logo image uses object-contain (no distortion/stretching)", () => {
    mockData = displayData({ logoUrl: "/media/clinic-logo/clinic-1/logo-abc123.png" });
    const { container } = render(<TvDisplayScreen slug="canora" />);
    const img = container.querySelector("header img") as HTMLImageElement;
    expect(img.className).toContain("object-contain");
  });
});
