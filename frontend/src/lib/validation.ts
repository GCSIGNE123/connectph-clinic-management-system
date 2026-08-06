import { z } from "zod";

/**
 * Shared, reusable Zod validation primitives. Feature-level schemas
 * (e.g. src/features/auth/schemas) should compose these rather than
 * redefining string rules ad-hoc.
 */

export const emailSchema = z
  .string()
  .min(1, "Email is required")
  .email("Enter a valid email address");

export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .max(72, "Password is too long")
  .regex(/[a-z]/, "Password must include a lowercase letter")
  .regex(/[A-Z]/, "Password must include an uppercase letter")
  .regex(/[0-9]/, "Password must include a number");

export const nameSchema = z
  .string()
  .min(1, "This field is required")
  .max(100, "Must be 100 characters or fewer");
