import { apiClient, tokenStorage } from "@/lib/api-client";
import type { AuthSession, AuthTokens, Branch, Clinic, User } from "@/types";
import type {
  ForgotPasswordInput,
  LoginInput,
  ResendVerificationInput,
  ResetPasswordInput,
  VerifyEmailInput,
} from "@/features/auth/schemas/auth-schemas";

/** Raw shape returned by `POST /auth/login` and `POST /auth/register` (flat, snake_case). */
interface RawTokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  clinic_id: string | null;
  role: string | null;
}

/** Raw shape returned by `GET /auth/me` and `PATCH /auth/me`. */
interface RawMe {
  id: string;
  email: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  mobile_number: string | null;
  role: string;
  clinic_id: string;
  clinic: {
    id: string;
    name: string;
    slug: string;
    logo_url: string | null;
    timezone: string;
    created_at: string;
  } | null;
  branch_id: string | null;
  branch: { id: string; clinic_id: string; name: string } | null;
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

function toTokens(raw: RawTokenResponse): AuthTokens {
  // The backend does not issue/track refresh tokens via the JSON body (it
  // uses an httpOnly cookie set by the server on /auth/login), and access
  // tokens are short-lived JWTs without an explicit expiry echoed back here.
  // We still populate refreshToken with the access token as a harmless
  // placeholder so `/auth/refresh` (which reads the httpOnly cookie, not
  // this value) continues to be triggered correctly on 401s.
  return {
    accessToken: raw.access_token,
    refreshToken: raw.access_token,
    expiresAt: Date.now() + 30 * 60 * 1000,
  };
}

function toUser(raw: RawMe): User {
  const clinic: Clinic | undefined = raw.clinic
    ? {
        id: raw.clinic.id,
        name: raw.clinic.name,
        slug: raw.clinic.slug,
        logoUrl: raw.clinic.logo_url,
        timezone: raw.clinic.timezone,
        createdAt: raw.clinic.created_at,
      }
    : undefined;
  const branch: Branch | undefined = raw.branch
    ? { id: raw.branch.id, clinicId: raw.branch.clinic_id, name: raw.branch.name }
    : undefined;

  return {
    id: raw.id,
    email: raw.email,
    firstName: raw.first_name,
    middleName: raw.middle_name,
    lastName: raw.last_name,
    mobileNumber: raw.mobile_number,
    role: raw.role as User["role"],
    clinicId: raw.clinic_id,
    clinic,
    branchId: raw.branch_id,
    branch,
    avatarUrl: raw.avatar_url,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

/**
 * Auth API bindings for the backend `/api/v1/auth/*` endpoints. The backend
 * returns response bodies directly (no `{ data }` envelope), so these
 * functions parse the raw shape and map it to the frontend's camelCase
 * domain types.
 */
export const authApi = {
  async login(input: LoginInput): Promise<AuthSession> {
    const raw = await apiClient.post<RawTokenResponse>(
      "/auth/login",
      { email_or_username: input.email, password: input.password, remember_me: input.rememberMe },
      { skipAuth: true }
    );
    const tokens = toTokens(raw);
    tokenStorage.setTokens(tokens);
    const user = await authApi.me();
    return { user, tokens };
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post<void>("/auth/logout");
    } finally {
      tokenStorage.clearTokens();
    }
  },

  async me(): Promise<User> {
    const raw = await apiClient.get<RawMe>("/auth/me");
    return toUser(raw);
  },

  /** Self-service profile update (name/mobile number only - see the
   * backend's `UpdateOwnProfileRequest` docstring for why role/branch/
   * email/username aren't reachable here). */
  async updateProfile(input: {
    firstName?: string;
    middleName?: string | null;
    lastName?: string;
    mobileNumber?: string | null;
  }): Promise<User> {
    const raw = await apiClient.patch<RawMe>("/auth/me", {
      first_name: input.firstName,
      middle_name: input.middleName,
      last_name: input.lastName,
      mobile_number: input.mobileNumber,
    });
    return toUser(raw);
  },

  async changePassword(input: { currentPassword: string; newPassword: string }): Promise<void> {
    await apiClient.post<{ detail: string }>("/auth/me/change-password", {
      current_password: input.currentPassword,
      new_password: input.newPassword,
    });
  },

  async forgotPassword(input: ForgotPasswordInput): Promise<void> {
    await apiClient.post<{ detail: string }>("/auth/forgot-password", input, { skipAuth: true });
  },

  async resetPassword(input: ResetPasswordInput): Promise<void> {
    await apiClient.post<{ detail: string }>(
      "/auth/reset-password",
      { token: input.token, new_password: input.password },
      { skipAuth: true }
    );
  },

  async refresh(): Promise<AuthTokens> {
    // The refresh token itself lives in an httpOnly cookie set by the
    // backend on login; the browser sends it automatically with
    // `credentials: "include"`. The body is optional.
    const raw = await apiClient.post<RawTokenResponse>("/auth/refresh", {}, { skipAuth: true });
    const tokens = toTokens(raw);
    tokenStorage.setTokens(tokens);
    return tokens;
  },

  async verifyEmail(input: VerifyEmailInput): Promise<void> {
    await apiClient.post<{ detail: string }>("/auth/verify-email", input, { skipAuth: true });
  },

  async resendVerification(input: ResendVerificationInput): Promise<void> {
    await apiClient.post<{ detail: string }>("/auth/resend-verification", input, {
      skipAuth: true,
    });
  },
};
