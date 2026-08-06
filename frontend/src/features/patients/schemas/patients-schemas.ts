import { z } from "zod";
import { emailSchema, nameSchema } from "@/lib/validation";
import { PatientBloodType, PatientCivilStatus, PatientGender } from "@/features/patients/types";

const mobileNumberSchema = z
  .string()
  .min(1, "Mobile number is required")
  .regex(/^\+?[0-9\s-]{7,15}$/, "Enter a valid mobile number");

const optionalTelephoneSchema = z
  .string()
  .regex(/^\+?[0-9\s-]{7,20}$/, "Enter a valid telephone number")
  .optional()
  .or(z.literal(""));

const today = () => new Date(new Date().toDateString());

/** Shared identity/contact/medical fields for both create and edit. */
const basePatientFields = {
  firstName: nameSchema,
  middleName: z.string().max(100).optional().or(z.literal("")),
  lastName: nameSchema,
  suffix: z.string().max(20).optional().or(z.literal("")),

  birthDate: z
    .string()
    .min(1, "Date of birth is required")
    .refine((value) => new Date(value) <= today(), "Birth date cannot be in the future"),
  gender: z.nativeEnum(PatientGender, { errorMap: () => ({ message: "Select a gender" }) }),
  civilStatus: z.nativeEnum(PatientCivilStatus, { errorMap: () => ({ message: "Select a civil status" }) }),
  nationality: z.string().min(1, "Nationality is required").max(100),

  addressLine: z.string().max(255).optional().or(z.literal("")),
  barangay: z.string().max(150).optional().or(z.literal("")),
  city: z.string().max(150).optional().or(z.literal("")),
  province: z.string().max(150).optional().or(z.literal("")),
  zipCode: z.string().max(20).optional().or(z.literal("")),

  mobileNumber: mobileNumberSchema,
  telephoneNumber: optionalTelephoneSchema,
  email: z.union([emailSchema, z.literal("")]).optional(),

  occupation: z.string().max(150).optional().or(z.literal("")),
  employer: z.string().max(150).optional().or(z.literal("")),

  bloodType: z.nativeEnum(PatientBloodType).optional().or(z.literal("")),
  allergies: z.string().optional().or(z.literal("")),
  medicalNotes: z.string().optional().or(z.literal("")),
  remarks: z.string().optional().or(z.literal("")),

  branchId: z.string().optional().or(z.literal("")),
};

export const createPatientSchema = z.object({
  ...basePatientFields,
  legacyPatientId: z.string().max(64).optional().or(z.literal("")),
});
export type CreatePatientInput = z.infer<typeof createPatientSchema>;

export const editPatientSchema = z.object(basePatientFields);
export type EditPatientInput = z.infer<typeof editPatientSchema>;

export const patientSearchSchema = z.object({
  search: z.string().optional(),
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(10),
});
export type PatientSearchInput = z.infer<typeof patientSearchSchema>;
