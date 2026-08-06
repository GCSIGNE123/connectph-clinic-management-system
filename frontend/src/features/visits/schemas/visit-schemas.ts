import { z } from "zod";
import { VisitPriority, VisitStatus, VisitType } from "@/features/visits/types";

/** Client-side validation for the Visit List search/filter bar. */
export const visitFilterSchema = z.object({
  search: z.string().optional().or(z.literal("")),
  status: z.nativeEnum(VisitStatus).optional(),
  visitType: z.nativeEnum(VisitType).optional(),
  doctorId: z.string().optional().or(z.literal("")),
  departmentId: z.string().optional().or(z.literal("")),
  dateFrom: z.string().optional().or(z.literal("")),
  dateTo: z.string().optional().or(z.literal("")),
});

export type VisitFilterInput = z.infer<typeof visitFilterSchema>;

export const editVisitSchema = z.object({
  doctorId: z.string().optional().or(z.literal("")),
  departmentId: z.string().optional(),
  serviceId: z.string().optional(),
  priority: z.nativeEnum(VisitPriority).optional(),
  remarks: z.string().max(1000).optional().or(z.literal("")),
});

export type EditVisitInput = z.infer<typeof editVisitSchema>;

export const visitStatusUpdateSchema = z.object({
  status: z.nativeEnum(VisitStatus),
  note: z.string().max(500).optional().or(z.literal("")),
});

export type VisitStatusUpdateInput = z.infer<typeof visitStatusUpdateSchema>;
