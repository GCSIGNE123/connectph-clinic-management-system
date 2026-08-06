/** Live client-side BMI calculation, mirrors the server-side computation in
 * `ConsultationService.save_soap` (`_compute_bmi`) so the SOAP tab shows the
 * same figure that will be persisted on save. */
export function computeBmi(heightCm: number | null | undefined, weightKg: number | null | undefined): number | null {
  if (!heightCm || !weightKg || heightCm <= 0) return null;
  const heightM = heightCm / 100;
  return Math.round((weightKg / (heightM * heightM)) * 100) / 100;
}
