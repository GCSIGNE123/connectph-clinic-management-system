import { z } from "zod";
import { emailSchema, nameSchema, passwordSchema } from "@/lib/validation";
import { Role, UserStatus } from "@/types";

const mobileNumberSchema = z
  .string()
  .min(1, "Mobile number is required")
  .regex(/^\+?[0-9\s-]{7,15}$/, "Enter a valid mobile number");

const usernameSchema = z
  .string()
  .min(3, "Username must be at least 3 characters")
  .max(32, "Username must be 32 characters or fewer")
  .regex(/^[a-zA-Z0-9_.]+$/, "Only letters, numbers, dots and underscores are allowed");

/** Shared base fields for both create and edit. */
const baseUserFields = {
  firstName: nameSchema,
  middleName: z.string().max(100).optional().or(z.literal("")),
  lastName: nameSchema,
  email: emailSchema,
  mobileNumber: mobileNumberSchema,
  username: usernameSchema,
  role: z.nativeEnum(Role, { errorMap: () => ({ message: "Select a role" }) }),
  branchId: z.string().optional().or(z.literal("")),
};

export const createUserSchema = z.object({
  ...baseUserFields,
  password: passwordSchema,
});
export type CreateUserInput = z.infer<typeof createUserSchema>;

export const editUserSchema = z.object({
  ...baseUserFields,
  status: z.nativeEnum(UserStatus),
});
export type EditUserInput = z.infer<typeof editUserSchema>;

/** Admin-initiated password reset for another user - requires complexity too. */
export const adminResetPasswordSchema = z
  .object({
    newPassword: passwordSchema,
    confirmPassword: z.string().min(1, "Please confirm the new password"),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });
export type AdminResetPasswordInput = z.infer<typeof adminResetPasswordSchema>;

export const userSearchSchema = z.object({
  search: z.string().optional(),
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(10),
});
export type UserSearchInput = z.infer<typeof userSearchSchema>;
