export type VaccinationStatus = "Requested" | "Administered" | "Cancelled";

export interface VaccinationAdministration {
  id: string;
  orderId: string;
  visitId: string;
  patientId: string;
  doctorId: string | null;
  vaccineName: string;
  status: VaccinationStatus;
  dose: string | null;
  lotNumber: string | null;
  site: string | null;
  route: string | null;
  notes: string | null;
  administeredAt: string | null;
  administeredBy: string | null;
  createdAt: string;
}

export interface VaccinationAdministerInput {
  vaccineName?: string;
  dose?: string;
  lotNumber?: string;
  site?: string;
  route?: string;
  notes?: string;
}
