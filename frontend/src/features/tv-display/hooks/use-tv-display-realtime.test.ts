import { describe, expect, it } from "vitest";
import { resolveWsToken } from "./use-tv-display-realtime";

describe("resolveWsToken", () => {
  it("uses the resolved wsAuthSlug (the real public_slug) when present, not the raw URL identifier", () => {
    // This is the case that matters for the short-code feature: the
    // browser was navigated to /tv/canora (identifier = "canora"), but the
    // WebSocket must still authenticate with the display's real,
    // high-entropy public_slug from the snapshot response - never the
    // short code itself.
    expect(resolveWsToken("canora", "U7mdycAmZuJEXzq0mUQtbddX8k82awRW")).toBe(
      "U7mdycAmZuJEXzq0mUQtbddX8k82awRW"
    );
  });

  it("falls back to the raw identifier when wsAuthSlug is null (e.g. a non-public config)", () => {
    expect(resolveWsToken("some-identifier", null)).toBe("some-identifier");
  });

  it("is a no-op when the browser was already navigated with the real public_slug (existing long-URL behavior unchanged)", () => {
    const slug = "U7mdycAmZuJEXzq0mUQtbddX8k82awRW";
    expect(resolveWsToken(slug, slug)).toBe(slug);
  });
});
