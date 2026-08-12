/**
 * A completely separate API client / token-storage instance for the
 * Patient Portal. Uses distinct localStorage keys
 * (`patient_access_token`/`patient_refresh_token`) and a distinct
 * middleware-presence cookie (`patient_session`) so patient auth state can
 * never collide with the clinic portal's (`cph_*` - src/lib/api-client.ts)
 * or the Platform Administration Portal's (`platform_*` -
 * src/features/platform-admin/api/client.ts) even if all three are open in
 * the same browser.
 */

import { getApiBaseUrl } from "@/lib/api-url";

const API_URL = getApiBaseUrl();

const ACCESS_TOKEN_KEY = "patient_access_token";
const REFRESH_TOKEN_KEY = "patient_refresh_token";
const SESSION_COOKIE_NAME = "patient_session";

export interface PatientTokens {
  accessToken: string;
  refreshToken: string;
}

export const patientTokenStorage = {
  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens(tokens: PatientTokens): void {
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

export class PatientApiError extends Error {
  statusCode: number;
  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "PatientApiError";
    this.statusCode = statusCode;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  skipAuth?: boolean;
}

export async function patientApiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, headers, ...rest } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Content-Type", "application/json");
  if (!skipAuth) {
    const token = patientTokenStorage.getAccessToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && !skipAuth) {
    patientTokenStorage.clearTokens();
    if (typeof window !== "undefined") window.location.href = "/patient-portal/login";
    throw new PatientApiError("Session expired", 401);
  }

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      message = data.detail ?? message;
    } catch {
      /* ignore parse errors */
    }
    throw new PatientApiError(message, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function patientLogin(identifier: string, password: string): Promise<PatientTokens> {
  const data = await patientApiFetch<{ access_token: string; refresh_token: string }>(
    "/patient-portal/auth/login",
    { method: "POST", body: { identifier, password }, skipAuth: true }
  );
  const tokens = { accessToken: data.access_token, refreshToken: data.refresh_token };
  patientTokenStorage.setTokens(tokens);
  return tokens;
}

export function patientLogout(): void {
  patientTokenStorage.clearTokens();
}
