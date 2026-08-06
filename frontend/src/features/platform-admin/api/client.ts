/**
 * A completely separate API client / token-storage instance for the
 * Platform Administration Portal. Uses distinct localStorage keys
 * (`platform_access_token`/`platform_refresh_token`) and a distinct
 * middleware-presence cookie (`platform_session`) so the platform-admin
 * auth state can never collide with the clinic portal's
 * (`cph_access_token`/`cph_refresh_token`/`cph_session` - see
 * src/lib/api-client.ts) even if both are open in the same browser.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api/v1";

const ACCESS_TOKEN_KEY = "platform_access_token";
const REFRESH_TOKEN_KEY = "platform_refresh_token";
const SESSION_COOKIE_NAME = "platform_session";

export interface PlatformTokens {
  accessToken: string;
  refreshToken: string;
}

export const platformTokenStorage = {
  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens(tokens: PlatformTokens): void {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.accessToken);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
    document.cookie = `${SESSION_COOKIE_NAME}=1; path=/; max-age=${60 * 60 * 24 * 7}; samesite=lax`;
  },
  clearTokens(): void {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    document.cookie = `${SESSION_COOKIE_NAME}=; path=/; max-age=0`;
  },
};

export class PlatformApiError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "PlatformApiError";
    this.statusCode = statusCode;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

export async function platformApiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Content-Type", "application/json");
  if (!skipAuth) {
    const token = platformTokenStorage.getAccessToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && !skipAuth) {
    platformTokenStorage.clearTokens();
    if (typeof window !== "undefined") window.location.href = "/platform/login";
    throw new PlatformApiError("Session expired", 401);
  }

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      message = data.detail ?? message;
    } catch {
      /* ignore parse errors */
    }
    throw new PlatformApiError(message, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function platformLogin(identifier: string, password: string): Promise<PlatformTokens> {
  const data = await platformApiFetch<{ access_token: string; refresh_token: string }>(
    "/platform-admin/auth/login",
    { method: "POST", body: { identifier, password }, skipAuth: true }
  );
  const tokens = { accessToken: data.access_token, refreshToken: data.refresh_token };
  platformTokenStorage.setTokens(tokens);
  return tokens;
}

export async function platformLogout(): Promise<void> {
  try {
    await platformApiFetch("/platform-admin/auth/logout", { method: "POST" });
  } finally {
    platformTokenStorage.clearTokens();
  }
}
