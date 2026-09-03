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

/**
 * Fired when the automatic 401-refresh-and-retry dance (below) exhausts
 * itself - the access token is gone/expired AND the refresh token could not
 * restore it (expired refresh token, or a browser that silently refused to
 * store/send the refresh cookie at all - e.g. `COOKIE_SECURE=true` behind
 * plain HTTP, see `docs/LOCAL_DEPLOYMENT.md`). Without this, the SPA stays
 * on the current page with a silently-dead session: every subsequent action
 * fails with a raw "Not authenticated" error (mutations) or a request that
 * looks like an empty result (queries, unless the page checks `isError` -
 * see `PatientsTable`'s `isError` prop), with nothing prompting the user to
 * sign in again. A listener (see `SessionExpiredListener`) sends them back
 * to `/login`. Never dispatched for a normal, user-initiated logout - that
 * flow (`useLogout`) already navigates to `/login` itself.
 */
export const SESSION_EXPIRED_EVENT = "cph:session-expired";

function notifySessionExpired(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
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
 * Shared low-level fetch: attaches the bearer token and transparently
 * refreshes it once on a 401 before retrying - the same auth/retry dance
 * `apiFetch` has always done, factored out so `apiFetchBlob`/`apiUploadFile`
 * (below) can reuse it instead of duplicating the refresh logic. Does NOT
 * set Content-Type or serialize the body - callers own that (JSON body vs.
 * FormData vs. no body at all all need different handling).
 */
async function performAuthedFetch(
  path: string,
  init: RequestInit,
  { skipAuth, skipRefresh }: { skipAuth?: boolean; skipRefresh?: boolean } = {}
): Promise<Response> {
  const doFetch = async (): Promise<Response> => {
    const finalHeaders = new Headers(init.headers);
    if (!skipAuth) {
      const token = tokenStorage.getAccessToken();
      if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
    }
    return fetch(`${API_URL}${path}`, { ...init, headers: finalHeaders, credentials: "include" });
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
      notifySessionExpired();
    }
  }

  return response;
}

/** Extracts the same `{message, statusCode, errors?}` shape from a failed
 * response that `apiFetch` has always produced - shared so `apiFetchBlob`
 * raises an equally useful `ApiError` on failure, not a generic one. */
async function toApiError(response: Response): Promise<ApiError> {
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
  return new ApiError({ ...payload, statusCode: payload.statusCode ?? response.status });
}

/**
 * Fetch wrapper for the CONNECT.PH backend API. Attaches the bearer token,
 * serializes JSON bodies, and transparently refreshes the access token once
 * on a 401 before retrying the original request.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, skipRefresh, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Content-Type", "application/json");

  const response = await performAuthedFetch(
    path,
    { ...rest, headers: finalHeaders, body: body !== undefined ? JSON.stringify(body) : undefined },
    { skipAuth, skipRefresh }
  );

  if (!response.ok) throw await toApiError(response);

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/**
 * Fetches an authenticated resource as a `Blob` - for content that isn't
 * JSON (e.g. a consultation attachment's actual image/PDF bytes, served by
 * an authenticated endpoint rather than a public static URL - see
 * `features/consultation/api/consultation-api.ts::getAttachmentFileBlob`).
 * A plain `<img src>` can't send the Authorization header, so viewing an
 * authenticated image means fetching it as a blob and pointing the `<img>`
 * at `URL.createObjectURL(blob)` instead.
 */
export async function apiFetchBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const { skipAuth, skipRefresh, headers } = options;
  // Round 6 fix: these endpoints (signature/attachment files) are served
  // from a STATIC url per entity (e.g. `/auth/me/signature/file`) that can
  // point at different underlying bytes over time (a replaced signature),
  // but the browser's HTTP cache has no way to know that - without
  // `no-store` a same-session replace-then-reload can keep showing the
  // PREVIOUS file's bytes even though the server-side pointer already
  // moved on and react-query's own cache was correctly invalidated.
  const response = await performAuthedFetch(
    path, { method: "GET", headers, cache: "no-store" }, { skipAuth, skipRefresh }
  );
  if (!response.ok) throw await toApiError(response);
  return response.blob();
}

/**
 * Uploads a real file as `multipart/form-data`. Deliberately does NOT set
 * Content-Type - the browser sets it (with the correct boundary) only when
 * given a `FormData` body directly, and setting it manually breaks that.
 */
export async function apiUploadFile<T>(path: string, formData: FormData): Promise<T> {
  const response = await performAuthedFetch(path, { method: "POST", body: formData });
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
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
