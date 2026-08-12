import type { ApiErrorResponse, AuthTokens } from "@/types";
import { getApiBaseUrl } from "@/lib/api-url";

const API_URL = getApiBaseUrl();

const ACCESS_TOKEN_KEY = "cph_access_token";
const REFRESH_TOKEN_KEY = "cph_refresh_token";
const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_AUTH_COOKIE_NAME ?? "cph_session";

export class ApiError extends Error {
  statusCode: number;
  errors?: Record<string, string[]>;

  constructor(payload: ApiErrorResponse) {
    super(payload.message);
    this.name = "ApiError";
    this.statusCode = payload.statusCode;
    this.errors = payload.errors;
  }
}

/** Token storage helpers (localStorage + a lightweight cookie for middleware). */
export const tokenStorage = {
  getAccessToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens(tokens: AuthTokens): void {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.accessToken);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken);
    // Lightweight, non-httpOnly cookie so middleware can perform a presence
    // check on protected routes. The real session of record is the token
    // pair above; this cookie is not used for authorization on the backend.
    document.cookie = `${AUTH_COOKIE_NAME}=1; path=/; max-age=${60 * 60 * 24 * 7}; samesite=lax`;
  },
  clearTokens(): void {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0`;
  },
};

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip attaching the Authorization header (e.g. login/refresh calls). */
  skipAuth?: boolean;
  /** Skip the automatic 401 refresh-and-retry flow. */
  skipRefresh?: boolean;
}

let refreshPromise: Promise<AuthTokens | null> | null = null;

/**
 * The refresh token is not held in JS at all - the backend sets it as an
 * httpOnly cookie on `/auth/login` and reads it back from that cookie on
 * `/auth/refresh` (see `backend/app/api/v1/auth.py`). We must send
 * `credentials: "include"` so the browser attaches that cookie.
 */
async function refreshAccessToken(): Promise<AuthTokens | null> {
  try {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({}),
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as { access_token: string };
    const tokens: AuthTokens = {
      accessToken: raw.access_token,
      refreshToken: raw.access_token,
      expiresAt: Date.now() + 30 * 60 * 1000,
    };
    tokenStorage.setTokens(tokens);
    return tokens;
  } catch {
    return null;
  }
}

/**
 * Fetch wrapper for the CONNECT.PH backend API. Attaches the bearer token,
 * serializes JSON bodies, and transparently refreshes the access token once
 * on a 401 before retrying the original request.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, skipRefresh, headers, ...rest } = options;

  const doFetch = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    finalHeaders.set("Content-Type", "application/json");

    if (!skipAuth) {
      const token = tokenStorage.getAccessToken();
      if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    }

    return fetch(`${API_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      credentials: "include",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let response = await doFetch();

  if (response.status === 401 && !skipAuth && !skipRefresh) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      response = await doFetch();
    } else {
      tokenStorage.clearTokens();
    }
  }

  if (!response.ok) {
    let payload: ApiErrorResponse;
    try {
      const body = (await response.json()) as ApiErrorResponse & { detail?: unknown };
      // FastAPI's default error shape is `{"detail": "..."}` (or, for 422
      // validation errors, `{"detail": [{"msg": "...", "loc": [...]}, ...]}`),
      // not `{"message": "..."}`. Without this mapping every ApiError.message
      // is empty, so the UI silently drops real backend error text (e.g. the
      // duplicate-active-queue and validation messages) and falls back to a
      // generic toast.
      let message = body.message;
      if (!message && body.detail !== undefined) {
        message = typeof body.detail === "string"
          ? body.detail
          : Array.isArray(body.detail)
            ? body.detail
                .map((d) => (typeof d === "object" && d && "msg" in d ? String((d as { msg: unknown }).msg) : String(d)))
                .join("; ")
            : JSON.stringify(body.detail);
      }
      payload = { ...body, message: message ?? response.statusText };
    } catch {
      payload = { message: response.statusText, statusCode: response.status };
    }
    throw new ApiError({ ...payload, statusCode: payload.statusCode ?? response.status });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};
