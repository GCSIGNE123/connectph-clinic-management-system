import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { InformationPanel } from "./InformationPanel";
import type { TvInfoContentItem } from "@/features/tv-display/types";

vi.mock("@/features/tv-display/api/tv-display-api", () => ({
  resolveTvMediaUrl: (url: string | null) => (url ? `http://api.test${url}` : null),
}));

function item(overrides: Partial<TvInfoContentItem> = {}): TvInfoContentItem {
  return {
    id: "item-1",
    title: "Flu Shots Now Available",
    body: "Visit our front desk to schedule your flu shot today.",
    contentType: "Promotion",
    durationSeconds: 10,
    displayOrder: 0,
    isActive: true,
    imageUrl: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("InformationPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("maximizes the image and adds no external title/body/eyebrow text when the item has an image", () => {
    render(<InformationPanel items={[item({ imageUrl: "/media/tv-info-content/clinic-1/ad.jpg" })]} />);

    // The image itself is the entire visual - no duplicated text around it.
    expect(screen.queryByText("Clinic Information")).not.toBeInTheDocument();
    expect(screen.queryByText("Promotion")).not.toBeInTheDocument();
    expect(screen.queryByText("Flu Shots Now Available")).not.toBeInTheDocument();
    expect(screen.queryByText(/Visit our front desk/)).not.toBeInTheDocument();

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "http://api.test/media/tv-info-content/clinic-1/ad.jpg");
    // Fills the panel, preserves aspect ratio (no distortion).
    expect(img.className).toContain("object-contain");
    expect(img.className).toContain("h-full");
    expect(img.className).toContain("w-full");
  });

  it("still shows the label/title/body for a text-only item with no image", () => {
    render(<InformationPanel items={[item({ contentType: "HealthTip", title: "Stay Hydrated", body: "Drink 8 glasses of water a day." })]} />);

    expect(screen.getByText("Clinic Information")).toBeInTheDocument();
    expect(screen.getByText("Health Tip")).toBeInTheDocument();
    expect(screen.getByText("Stay Hydrated")).toBeInTheDocument();
    expect(screen.getByText("Drink 8 glasses of water a day.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no active items", () => {
    render(<InformationPanel items={[]} />);
    expect(screen.getByText("No information to display")).toBeInTheDocument();
  });

  it("still renders rotation dots (one per item) for multiple items, regardless of image/text mix", () => {
    const { container } = render(
      <InformationPanel
        items={[item({ id: "a", imageUrl: "/media/a.jpg" }), item({ id: "b" }), item({ id: "c", imageUrl: "/media/c.jpg" })]}
      />
    );
    const dots = container.querySelectorAll("span.rounded-full");
    expect(dots.length).toBe(3);
  });
});
