import { z } from "zod";
import { QueuePriority, VisitClassification } from "@/features/queue/types";

export const newQueueSchema = z.object({
  patientId: z.string().min(1, "Select a patient"),
  branchId: z.string().min(1, "Select a branch"),
  departmentId: z.string().min(1, "Select a department"),
  doctorId: z.string().optional().or(z.literal("")),
  serviceId: z.string().min(1, "Select a service"),
  priority: z.nativeEnum(QueuePriority, { errorMap: () => ({ message: "Select a priority" }) }),
  notes: z.string().max(1000).optional().or(z.literal("")),
  visitClassification: z.nativeEnum(VisitClassification),
});

export type NewQueueInput = z.infer<typeof newQueueSchema>;

export const queueStatusUpdateSchema = z.object({
  status: z.string().min(1),
  note: z.string().max(500).optional().or(z.literal("")),
});

export type QueueStatusUpdateInput = z.infer<typeof queueStatusUpdateSchema>;

export const editQueueSchema = z.object({
  departmentId: z.string().optional(),
  doctorId: z.string().optional().or(z.literal("")),
  serviceId: z.string().optional(),
  priority: z.nativeEnum(QueuePriority).optional(),
  notes: z.string().max(1000).optional().or(z.literal("")),
  visitClassification: z.nativeEnum(VisitClassification).optional(),
});

export type EditQueueInput = z.infer<typeof editQueueSchema>;
