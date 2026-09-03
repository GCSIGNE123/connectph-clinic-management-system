import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const originalFetch = global.fetch;

describe("apiClient session-expiry signal", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("dispatches SESSION_EXPIRED_EVENT when a 401 survives a failed refresh, and clears stored tokens", async () => {
    const { apiClient, tokenStorage, SESSION_EXPIRED_EVENT, ApiError } = await import("./api-client");

    tokenStorage.setTokens({ accessToken: "expired-token", refreshToken: "irrelevant", expiresAt: 0 });

    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);

    // First call (the real request) and the `/auth/refresh` attempt both
    // 401 - simulating an access token that's expired AND a refresh-token
    // cookie the browser never actually sent (e.g. COOKIE_SECURE=true
    // behind plain HTTP - the production incident this guards against).
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 })
    );

    await expect(apiClient.get("/patients")).rejects.toBeInstanceOf(ApiError);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(tokenStorage.getAccessToken()).toBeNull();
    expect(tokenStorage.getRefreshToken()).toBeNull();

    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });

  it("does NOT dispatch SESSION_EXPIRED_EVENT when the refresh succeeds and the retry works", async () => {
    const { apiClient, tokenStorage, SESSION_EXPIRED_EVENT } = await import("./api-client");

    tokenStorage.setTokens({ accessToken: "expiring-token", refreshToken: "irrelevant", expiresAt: 0 });

    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);

    let call = 0;
    global.fetch = vi.fn().mockImplementation((url: string) => {
      call += 1;
      if (typeof url === "string" && url.includes("/auth/refresh")) {
        return Promise.resolve(
          new Response(JSON.stringify({ access_token: "fresh-token" }), { status: 200 })
        );
      }
      // First call 401s (expired access token), the retry (call 3, after
      // refresh) succeeds.
      if (call === 1) {
        return Promise.resolve(new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    });

    await expect(apiClient.get("/patients")).resolves.toEqual({ items: [] });

    expect(listener).not.toHaveBeenCalled();
    expect(tokenStorage.getAccessToken()).toBe("fresh-token");

    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });
});
