import { NextResponse, type NextRequest } from "next/server";

const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_AUTH_COOKIE_NAME ?? "cph_session";
// Phase 15: a completely separate presence-check cookie for the Platform
// Administration Portal (see src/features/platform-admin/api/client.ts).
// This is deliberately NOT the same cookie/prefix logic as the clinic
// portal below - a platform-admin session must never satisfy the clinic
// portal's check, and vice versa.
const PLATFORM_SESSION_COOKIE_NAME = "platform_session";
// Phase 18: a THIRD, completely separate presence-check cookie for the
// Patient Portal (see src/features/patient-portal/api/client.ts). Same
// rationale as the platform-admin cookie above - never satisfies the
// clinic or platform-admin session checks, and vice versa.
const PATIENT_SESSION_COOKIE_NAME = "patient_session";

const PROTECTED_PREFIXES = ["/dashboard", "/users"];
const PUBLIC_AUTH_PATHS = ["/login", "/forgot-password", "/reset-password"];

const PLATFORM_PROTECTED_PREFIXES = ["/platform/dashboard", "/platform/tenants"];
const PLATFORM_PUBLIC_PATHS = ["/platform/login"];

const PATIENT_PROTECTED_PREFIXES = [
  "/patient-portal/dashboard", "/patient-portal/appointments", "/patient-portal/laboratory",
  "/patient-portal/prescriptions", "/patient-portal/records", "/patient-portal/billing",
  "/patient-portal/notifications", "/patient-portal/profile",
];
const PATIENT_PUBLIC_PATHS = ["/patient-portal/login"];

/**
 * Basic route protection: checks for the presence of the lightweight,
 * non-httpOnly session cookie set on login (see src/lib/api-client.ts).
 *
 * TODO: this is a presence check only, not a signature/JWT verification.
 * Once the backend exposes a way to verify sessions at the edge (or we
 * move to httpOnly cookies issued by the backend), replace this with a
 * real verification call.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Platform Administration Portal routes are checked against their own,
  // separate session cookie and redirect to /platform/login (never the
  // clinic portal's /login).
  if (pathname.startsWith("/platform")) {
    const hasPlatformSession = Boolean(request.cookies.get(PLATFORM_SESSION_COOKIE_NAME)?.value);
    const isPlatformProtected = PLATFORM_PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
    if (isPlatformProtected && !hasPlatformSession) {
      const loginUrl = new URL("/platform/login", request.url);
      loginUrl.searchParams.set("redirectTo", pathname);
      return NextResponse.redirect(loginUrl);
    }
    const isPlatformPublicPath = PLATFORM_PUBLIC_PATHS.some((path) => pathname.startsWith(path));
    if (isPlatformPublicPath && hasPlatformSession) {
      return NextResponse.redirect(new URL("/platform/dashboard", request.url));
    }
    return NextResponse.next();
  }

  // Patient Portal routes are checked against their own, separate session
  // cookie and redirect to /patient-portal/login (never /login or
  // /platform/login).
  if (pathname.startsWith("/patient-portal")) {
    const hasPatientSession = Boolean(request.cookies.get(PATIENT_SESSION_COOKIE_NAME)?.value);
    const isPatientProtected = PATIENT_PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
    if (isPatientProtected && !hasPatientSession) {
      const loginUrl = new URL("/patient-portal/login", request.url);
      loginUrl.searchParams.set("redirectTo", pathname);
      return NextResponse.redirect(loginUrl);
    }
    const isPatientPublicPath = PATIENT_PUBLIC_PATHS.some((path) => pathname.startsWith(path));
    if (isPatientPublicPath && hasPatientSession) {
      return NextResponse.redirect(new URL("/patient-portal/dashboard", request.url));
    }
    return NextResponse.next();
  }

  const hasSession = Boolean(request.cookies.get(AUTH_COOKIE_NAME)?.value);

  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  if (isProtected && !hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectTo", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const isPublicAuthPath = PUBLIC_AUTH_PATHS.some((path) => pathname.startsWith(path));
  if (isPublicAuthPath && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/users/:path*",
    "/login",
    "/forgot-password",
    "/reset-password",
    "/platform/:path*",
    "/patient-portal/:path*",
  ],
};
