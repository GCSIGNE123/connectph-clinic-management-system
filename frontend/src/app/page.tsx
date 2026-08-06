import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_AUTH_COOKIE_NAME ?? "cph_session";

/**
 * Root route: redirects to /dashboard when a session cookie is present,
 * otherwise to /login. This is a coarse presence check only - real
 * authorization happens against the backend via the access token.
 */
export default async function RootPage() {
  const cookieStore = await cookies();
  const hasSession = Boolean(cookieStore.get(AUTH_COOKIE_NAME)?.value);

  redirect(hasSession ? "/dashboard" : "/login");
}
