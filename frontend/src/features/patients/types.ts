/**
 * Domain types for the patient management feature, mirroring the backend's
 * `schemas/patient.py`. This is the master patient record that future
 * modules (queue, appointments, billing, laboratory, pharmacy, medical
 * records, reports) will reference by `id`.
 */

export enum PatientGender {
  Male = "Male",
  Female = "Female",
  Other = "Other",
}

export enum PatientCivilStatus {
  Single = "Single",
  Married = "Married",
  Widowed = "Widowed",
  Separated = "Separated",
  Divorced = "Divorced",
}

export enum PatientBloodType {
  APos = "A+",
  ANeg = "A-",
  BPos = "B+",
  BNeg = "B-",
  ABPos = "AB+",
  ABNeg = "AB-",
  OPos = "O+",
  ONeg = "O-",
  Unknown = "Unknown",
}

export enum PatientStatus {
  Active = "Active",
  Archived = "Archived",
}

export type PatientSortOption = "newest" | "oldest" | "alphabetical" | "recently_visited";

export interface Patient {
  id: string;
  clinicId: string;
  branchId?: string | null;
  patientNumber: string;
  legacyPatientId?: string | null;

  firstName: string;
  middleName?: string | null;
  lastName: string;
  suffix?: string | null;

  birthDate: string;
  gender: PatientGender;
  civilStatus: PatientCivilStatus;
  nationality: string;

  addressLine?: string | null;
  barangay?: string | null;
  city?: string | null;
  province?: string | null;
  zipCode?: string | null;

  mobileNumber: string;
  telephoneNumber?: string | null;
  email?: string | null;

  occupation?: string | null;
  employer?: string | null;

  bloodType?: PatientBloodType | null;
  allergies?: string | null;
  medicalNotes?: string | null;
  remarks?: string | null;
  emergencyContactName?: string | null;
  emergencyContactPhone?: string | null;

  photoUrl?: string | null;
  qrCode?: string | null;

  /** Phase 2.7 (YAKAP Patient Classification): the patient's STANDING
   * PhilHealth YAKAP beneficiary status - separate from the per-encounter
   * classification set on each queue ticket. */
  isYakapBeneficiary: boolean;

  status: PatientStatus;
  dateRegistered: string;
  lastVisit?: string | null;

  createdAt: string;
  updatedAt: string;
}

/** Slim projection for table rows. */
export type PatientListItem = Pick<
  Patient,
  | "id"
  | "patientNumber"
  | "firstName"
  | "middleName"
  | "lastName"
  | "suffix"
  | "birthDate"
  | "gender"
  | "mobileNumber"
  | "photoUrl"
  | "branchId"
  | "isYakapBeneficiary"
  | "status"
  | "dateRegistered"
  | "lastVisit"
>;

export interface PatientListParams {
  search?: string;
  branchId?: string;
  gender?: PatientGender;
  status?: PatientStatus;
  ageMin?: number;
  ageMax?: number;
  registeredFrom?: string;
  registeredTo?: string;
  lastVisitFrom?: string;
  lastVisitTo?: string;
  sort?: PatientSortOption;
  page?: number;
  pageSize?: number;
}

export interface DuplicateCandidate {
  id: string;
  patientNumber: string;
  fullName: string;
  birthDate: string;
  mobileNumber: string;
  matchReason: string;
}

/** Result of a create/update call: either the saved patient, or a list of
 * duplicate candidates that need to be confirmed/overridden. */
export interface PatientMutationResult {
  patient: Patient | null;
  duplicates: DuplicateCandidate[];
}

export interface PatientQr {
  patientId: string;
  qrCode: string;
  payload: string;
}

export interface PatientPhotoUploadTarget {
  uploadUrl: string;
  publicUrl: string;
  expiresIn: number;
}
