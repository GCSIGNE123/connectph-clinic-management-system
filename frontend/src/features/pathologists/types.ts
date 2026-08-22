/** Round 6 (Laboratory Report Signatories): Pathologist master data - a
 * clinic-configured list selected from during Laboratory result release,
 * never a login account (see backend `models/pathologist.py`). */
export interface Pathologist {
  id: string;
  clinic_id: string;
  name: string;
  license_number?: string | null;
  signature_url?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
