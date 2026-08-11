import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types";
import type {
  DuplicateCandidate,
  Patient,
  PatientListItem,
  PatientListParams,
  PatientMutationResult,
  PatientPhotoUploadTarget,
  PatientQr,
} from "@/features/patients/types";
import type { CreatePatientInput, EditPatientInput } from "@/features/patients/schemas/patients-schemas";

/** Raw shapes as returned by `api/v1/patients.py` (snake_case). */
interface RawPatient {
  id: string;
  clinic_id: string;
  branch_id?: string | null;
  patient_number: string;
  legacy_patient_id?: string | null;
  first_name: string;
  middle_name?: string | null;
  last_name: string;
  suffix?: string | null;
  birth_date: string;
  gender: string;
  civil_status: string;
  nationality: string;
  address_line?: string | null;
  barangay?: string | null;
  city?: string | null;
  province?: string | null;
  zip_code?: string | null;
  mobile_number: string;
  telephone_number?: string | null;
  email?: string | null;
  occupation?: string | null;
  employer?: string | null;
  blood_type?: string | null;
  allergies?: string | null;
  medical_notes?: string | null;
  remarks?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
  photo_url?: string | null;
  qr_code?: string | null;
  is_yakap_beneficiary: boolean;
  status: string;
  date_registered: string;
  last_visit?: string | null;
  created_at: string;
  updated_at: string;
}

interface RawPatientListItem {
  id: string;
  patient_number: string;
  first_name: string;
  middle_name?: string | null;
  last_name: string;
  suffix?: string | null;
  birth_date: string;
  gender: string;
  mobile_number: string;
  photo_url?: string | null;
  branch_id?: string | null;
  is_yakap_beneficiary: boolean;
  status: string;
  date_registered: string;
  last_visit?: string | null;
}

interface RawDuplicateCandidate {
  id: string;
  patient_number: string;
  full_name: string;
  birth_date: string;
  mobile_number: string;
  match_reason: string;
}

function toPatient(raw: RawPatient): Patient {
  return {
    id: raw.id,
    clinicId: raw.clinic_id,
    branchId: raw.branch_id,
    patientNumber: raw.patient_number,
    legacyPatientId: raw.legacy_patient_id,
    firstName: raw.first_name,
    middleName: raw.middle_name,
    lastName: raw.last_name,
    suffix: raw.suffix,
    birthDate: raw.birth_date,
    gender: raw.gender as Patient["gender"],
    civilStatus: raw.civil_status as Patient["civilStatus"],
    nationality: raw.nationality,
    addressLine: raw.address_line,
    barangay: raw.barangay,
    city: raw.city,
    province: raw.province,
    zipCode: raw.zip_code,
    mobileNumber: raw.mobile_number,
    telephoneNumber: raw.telephone_number,
    email: raw.email,
    occupation: raw.occupation,
    employer: raw.employer,
    bloodType: (raw.blood_type as Patient["bloodType"]) ?? null,
    allergies: raw.allergies,
    medicalNotes: raw.medical_notes,
    remarks: raw.remarks,
    emergencyContactName: raw.emergency_contact_name,
    emergencyContactPhone: raw.emergency_contact_phone,
    photoUrl: raw.photo_url,
    qrCode: raw.qr_code,
    isYakapBeneficiary: raw.is_yakap_beneficiary,
    status: raw.status as Patient["status"],
    dateRegistered: raw.date_registered,
    lastVisit: raw.last_visit,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toPatientListItem(raw: RawPatientListItem): PatientListItem {
  return {
    id: raw.id,
    patientNumber: raw.patient_number,
    firstName: raw.first_name,
    middleName: raw.middle_name,
    lastName: raw.last_name,
    suffix: raw.suffix,
    birthDate: raw.birth_date,
    gender: raw.gender as PatientListItem["gender"],
    mobileNumber: raw.mobile_number,
    photoUrl: raw.photo_url,
    branchId: raw.branch_id,
    isYakapBeneficiary: raw.is_yakap_beneficiary,
    status: raw.status as PatientListItem["status"],
    dateRegistered: raw.date_registered,
    lastVisit: raw.last_visit,
  };
}

function toDuplicateCandidate(raw: RawDuplicateCandidate): DuplicateCandidate {
  return {
    id: raw.id,
    patientNumber: raw.patient_number,
    fullName: raw.full_name,
    birthDate: raw.birth_date,
    mobileNumber: raw.mobile_number,
    matchReason: raw.match_reason,
  };
}

function toMutationResult(raw: { patient: RawPatient | null; duplicates: RawDuplicateCandidate[] }): PatientMutationResult {
  return {
    patient: raw.patient ? toPatient(raw.patient) : null,
    duplicates: raw.duplicates.map(toDuplicateCandidate),
  };
}

function toQueryString(params: PatientListParams): string {
  const search = new URLSearchParams();
  if (params.search) search.set("q", params.search);
  if (params.branchId) search.set("branch_id", params.branchId);
  if (params.gender) search.set("gender", params.gender);
  if (params.status) search.set("status", params.status);
  if (params.ageMin !== undefined) search.set("age_min", String(params.ageMin));
  if (params.ageMax !== undefined) search.set("age_max", String(params.ageMax));
  if (params.registeredFrom) search.set("registered_from", params.registeredFrom);
  if (params.registeredTo) search.set("registered_to", params.registeredTo);
  if (params.lastVisitFrom) search.set("last_visit_from", params.lastVisitFrom);
  if (params.lastVisitTo) search.set("last_visit_to", params.lastVisitTo);
  if (params.sort) search.set("sort", params.sort);

  const pageSize = params.pageSize ?? 10;
  const page = params.page ?? 1;
  search.set("limit", String(pageSize));
  search.set("offset", String((page - 1) * pageSize));

  return `?${search.toString()}`;
}

function toCreatePayload(input: CreatePatientInput) {
  return {
    first_name: input.firstName,
    middle_name: input.middleName || null,
    last_name: input.lastName,
    suffix: input.suffix || null,
    birth_date: input.birthDate,
    gender: input.gender,
    civil_status: input.civilStatus,
    nationality: input.nationality,
    address_line: input.addressLine || null,
    barangay: input.barangay || null,
    city: input.city || null,
    province: input.province || null,
    zip_code: input.zipCode || null,
    mobile_number: input.mobileNumber,
    telephone_number: input.telephoneNumber || null,
    email: input.email || null,
    occupation: input.occupation || null,
    employer: input.employer || null,
    blood_type: input.bloodType || null,
    allergies: input.allergies || null,
    medical_notes: input.medicalNotes || null,
    remarks: input.remarks || null,
    branch_id: input.branchId || null,
    legacy_patient_id: input.legacyPatientId || null,
    is_yakap_beneficiary: input.isYakapBeneficiary,
  };
}

function toUpdatePayload(input: EditPatientInput) {
  const { legacy_patient_id: _ignored, ...rest } = toCreatePayload({
    ...input,
    legacyPatientId: "",
  } as CreatePatientInput);
  void _ignored;
  return rest;
}

/** `/api/v1/patients/*` bindings for the master patient database. */
export const patientsApi = {
  async list(params: PatientListParams): Promise<PaginatedResponse<PatientListItem>> {
    const raw = await apiClient.get<{ items: RawPatientListItem[]; total: number; limit: number; offset: number }>(
      `/patients${toQueryString(params)}`
    );
    const pageSize = raw.limit || 1;
    return {
      data: raw.items.map(toPatientListItem),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },

  async get(id: string): Promise<Patient> {
    const raw = await apiClient.get<RawPatient>(`/patients/${id}`);
    return toPatient(raw);
  },

  async create(input: CreatePatientInput, options?: { override?: boolean }): Promise<PatientMutationResult> {
    const qs = options?.override ? "?override=true" : "";
    const raw = await apiClient.post<{ patient: RawPatient | null; duplicates: RawDuplicateCandidate[] }>(
      `/patients${qs}`,
      toCreatePayload(input)
    );
    return toMutationResult(raw);
  },

  async update(id: string, input: EditPatientInput, options?: { override?: boolean }): Promise<PatientMutationResult> {
    const qs = options?.override ? "?override=true" : "";
    const raw = await apiClient.put<{ patient: RawPatient | null; duplicates: RawDuplicateCandidate[] }>(
      `/patients/${id}${qs}`,
      toUpdatePayload(input)
    );
    return toMutationResult(raw);
  },

  async archive(id: string): Promise<Patient> {
    const raw = await apiClient.post<RawPatient>(`/patients/${id}/archive`);
    return toPatient(raw);
  },

  async restore(id: string): Promise<Patient> {
    const raw = await apiClient.post<RawPatient>(`/patients/${id}/restore`);
    return toPatient(raw);
  },

  async getQr(id: string): Promise<PatientQr> {
    const raw = await apiClient.get<{ patient_id: string; qr_code: string; payload: string }>(`/patients/${id}/qr`);
    return { patientId: raw.patient_id, qrCode: raw.qr_code, payload: raw.payload };
  },

  /**
   * Requests a presigned upload target from the backend stub, then "uploads"
   * the file. Until real Supabase Storage wiring lands (see backend
   * `PatientService.request_photo_upload_url` TODO), this just resolves the
   * public URL immediately instead of performing a real PUT.
   */
  async uploadPhoto(id: string, file: File): Promise<{ url: string }> {
    const target = await apiClient.post<{ upload_url: string; public_url: string; expires_in: number }>(
      `/patients/${id}/photo`
    );
    const photoUploadTarget: PatientPhotoUploadTarget = {
      uploadUrl: target.upload_url,
      publicUrl: target.public_url,
      expiresIn: target.expires_in,
    };
    void file;
    return { url: photoUploadTarget.publicUrl };
  },
};
