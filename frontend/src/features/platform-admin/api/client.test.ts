import { describe, expect, it, beforeEach } from "vitest";
import { platformTokenStorage } from "./client";

describe("platformTokenStorage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.cookie = "platform_session=; path=/; max-age=0";
    document.cookie = "cph_session=; path=/; max-age=0";
  });

  it("stores platform tokens under keys distinct from the clinic portal's", () => {
    platformTokenStorage.setTokens({ accessToken: "pa-access", refreshToken: "pa-refresh" }, true);

    expect(window.localStorage.getItem("platform_access_token")).toBe("pa-access");
    expect(window.localStorage.getItem("platform_refresh_token")).toBe("pa-refresh");
    // Never written to the clinic portal's keys.
    expect(window.localStorage.getItem("cph_access_token")).toBeNull();
    expect(window.localStorage.getItem("cph_refresh_token")).toBeNull();
  });

  it("sets a platform_session cookie distinct from the clinic portal's cph_session cookie", () => {
    platformTokenStorage.setTokens({ accessToken: "a", refreshToken: "b" }, true);
    expect(document.cookie).toContain("platform_session=1");
    expect(document.cookie).not.toContain("cph_session=1");
  });

  it("clearTokens removes only the platform tokens", () => {
    window.localStorage.setItem("cph_access_token", "clinic-token");
    platformTokenStorage.setTokens({ accessToken: "a", refreshToken: "b" }, true);

    platformTokenStorage.clearTokens();

    expect(window.localStorage.getItem("platform_access_token")).toBeNull();
    expect(window.localStorage.getItem("platform_refresh_token")).toBeNull();
    // Clinic portal's own token, if present, is untouched.
    expect(window.localStorage.getItem("cph_access_token")).toBe("clinic-token");
  });

  it("returns null when no token has been set", () => {
    expect(platformTokenStorage.getAccessToken()).toBeNull();
    expect(platformTokenStorage.getRefreshToken()).toBeNull();
  });
});
