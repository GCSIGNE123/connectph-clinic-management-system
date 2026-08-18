import { apiClient, apiFetchBlob, apiUploadFile } from "@/lib/api-client";
import type { Doctor } from "@/features/clinic-config/types";

/**
 * Doctor E-Signature: real, locally-stored PNG upload/replace/remove +
 * authenticated retrieval - see `api/v1/doctors.py`'s signature endpoints.
 * Deliberately its own small API module (not folded into the generic
 * `createCrudApi("/doctors")` factory used by the Doctors master-data
 * page) since file upload/blob-fetch don't fit that factory's plain-JSON
 * CRUD shape.
 */
export const doctorSignatureApi = {
  upload: async (doctorId: string, file: File): Promise<Doctor> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiUploadFile<Doctor>(`/doctors/${doctorId}/signature`, formData);
  },
  remove: async (doctorId: string): Promise<Doctor> => {
    return apiClient.delete<Doctor>(`/doctors/${doctorId}/signature`);
  },
  getSignatureBlob: (doctorId: string): Promise<Blob> => apiFetchBlob(`/doctors/${doctorId}/signature/file`),
};
