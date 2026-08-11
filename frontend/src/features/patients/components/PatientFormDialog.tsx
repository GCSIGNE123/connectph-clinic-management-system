"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createPatientSchema,
  editPatientSchema,
  type CreatePatientInput,
  type EditPatientInput,
} from "@/features/patients/schemas/patients-schemas";
import { useCreatePatient, useUpdatePatient } from "@/features/patients/hooks/use-patient-mutations";
import { DuplicateWarningDialog } from "@/features/patients/components/DuplicateWarningDialog";
import { PatientBloodType, PatientCivilStatus, PatientGender } from "@/features/patients/types";
import type { DuplicateCandidate, Patient } from "@/features/patients/types";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { Role } from "@/types";

export interface PatientFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When provided, the dialog edits this patient; otherwise it creates a new one. */
  patient?: Patient | null;
}

type FormValues = CreatePatientInput;

const emptyDefaults: FormValues = {
  firstName: "",
  middleName: "",
  lastName: "",
  suffix: "",
  birthDate: "",
  gender: PatientGender.Male,
  civilStatus: PatientCivilStatus.Single,
  nationality: "Filipino",
  addressLine: "",
  barangay: "",
  city: "",
  province: "",
  zipCode: "",
  mobileNumber: "",
  telephoneNumber: "",
  email: "",
  occupation: "",
  employer: "",
  bloodType: "",
  allergies: "",
  medicalNotes: "",
  remarks: "",
  branchId: "",
  legacyPatientId: "",
  isYakapBeneficiary: false,
};

/**
 * Add/Edit patient dialog covering the full demographic/contact/medical
 * profile, grouped into Identity, Contact/Address, and Medical Info
 * sections. On duplicate-warning responses from the backend, shows
 * `DuplicateWarningDialog` and (for Owner/Administrator users) lets them
 * resubmit with the override flag.
 */
export function PatientFormDialog({ open, onOpenChange, patient }: PatientFormDialogProps) {
  const isEdit = Boolean(patient);
  const schema = isEdit ? editPatientSchema : createPatientSchema;

  const { data: currentUser } = useCurrentUser();
  const canOverride = currentUser?.role === Role.Owner || currentUser?.role === Role.Administrator;

  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const [pendingValues, setPendingValues] = useState<FormValues | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema as never),
    defaultValues: emptyDefaults,
  });

  useEffect(() => {
    if (open) {
      reset(
        patient
          ? {
              firstName: patient.firstName,
              middleName: patient.middleName ?? "",
              lastName: patient.lastName,
              suffix: patient.suffix ?? "",
              birthDate: patient.birthDate.slice(0, 10),
              gender: patient.gender,
              civilStatus: patient.civilStatus,
              nationality: patient.nationality,
              addressLine: patient.addressLine ?? "",
              barangay: patient.barangay ?? "",
              city: patient.city ?? "",
              province: patient.province ?? "",
              zipCode: patient.zipCode ?? "",
              mobileNumber: patient.mobileNumber,
              telephoneNumber: patient.telephoneNumber ?? "",
              email: patient.email ?? "",
              occupation: patient.occupation ?? "",
              employer: patient.employer ?? "",
              bloodType: patient.bloodType ?? "",
              allergies: patient.allergies ?? "",
              medicalNotes: patient.medicalNotes ?? "",
              remarks: patient.remarks ?? "",
              branchId: patient.branchId ?? "",
              legacyPatientId: patient.legacyPatientId ?? "",
              isYakapBeneficiary: patient.isYakapBeneficiary,
            }
          : emptyDefaults
      );
      setDuplicates([]);
      setPendingValues(null);
    }
  }, [open, patient, reset]);

  const createPatient = useCreatePatient();
  const updatePatient = useUpdatePatient(patient?.id ?? "");
  const mutation = isEdit ? updatePatient : createPatient;

  const submit = (values: FormValues, override: boolean) => {
    const onResult = (result: { patient: unknown; duplicates: DuplicateCandidate[] }) => {
      if (result.patient) {
        onOpenChange(false);
      } else {
        setDuplicates(result.duplicates);
        setPendingValues(values);
      }
    };

    if (isEdit) {
      updatePatient.mutate({ input: values as EditPatientInput, override }, { onSuccess: onResult });
    } else {
      createPatient.mutate({ input: values, override }, { onSuccess: onResult });
    }
  };

  const onSubmit = handleSubmit((values) => submit(values, false));

  return (
    <>
      <Dialog open={open && duplicates.length === 0} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl" onClose={() => onOpenChange(false)}>
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit patient" : "Add patient"}</DialogTitle>
          </DialogHeader>

          <form onSubmit={onSubmit} noValidate className="space-y-6">
            <fieldset className="space-y-4">
              <legend className="text-sm font-semibold text-foreground">Identity</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="firstName">First name</Label>
                  <Input id="firstName" invalid={Boolean(errors.firstName)} {...register("firstName")} />
                  {errors.firstName ? <p className="text-xs text-destructive">{errors.firstName.message}</p> : null}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="middleName">Middle name</Label>
                  <Input id="middleName" {...register("middleName")} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="suffix">Suffix</Label>
                  <Input id="suffix" placeholder="Jr., Sr., III" {...register("suffix")} />
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="lastName">Last name</Label>
                  <Input id="lastName" invalid={Boolean(errors.lastName)} {...register("lastName")} />
                  {errors.lastName ? <p className="text-xs text-destructive">{errors.lastName.message}</p> : null}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="birthDate">Date of birth</Label>
                  <Input
                    id="birthDate"
                    type="date"
                    invalid={Boolean(errors.birthDate)}
                    {...register("birthDate")}
                  />
                  {errors.birthDate ? <p className="text-xs text-destructive">{errors.birthDate.message}</p> : null}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="gender">Gender</Label>
                  <Select id="gender" invalid={Boolean(errors.gender)} {...register("gender")}>
                    {Object.values(PatientGender).map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="civilStatus">Civil status</Label>
                  <Select id="civilStatus" invalid={Boolean(errors.civilStatus)} {...register("civilStatus")}>
                    {Object.values(PatientCivilStatus).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="nationality">Nationality</Label>
                  <Input id="nationality" invalid={Boolean(errors.nationality)} {...register("nationality")} />
                </div>
              </div>
            </fieldset>

            <fieldset className="space-y-4">
              <legend className="text-sm font-semibold text-foreground">Contact &amp; address</legend>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="mobileNumber">Mobile number</Label>
                  <Input id="mobileNumber" invalid={Boolean(errors.mobileNumber)} {...register("mobileNumber")} />
                  {errors.mobileNumber ? (
                    <p className="text-xs text-destructive">{errors.mobileNumber.message}</p>
                  ) : null}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="telephoneNumber">Telephone number</Label>
                  <Input id="telephoneNumber" {...register("telephoneNumber")} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" invalid={Boolean(errors.email)} {...register("email")} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="addressLine">Address</Label>
                <Input id="addressLine" {...register("addressLine")} />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
                <Input placeholder="Barangay" aria-label="Barangay" {...register("barangay")} />
                <Input placeholder="City" aria-label="City" {...register("city")} />
                <Input placeholder="Province" aria-label="Province" {...register("province")} />
                <Input placeholder="ZIP code" aria-label="ZIP code" {...register("zipCode")} />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Input placeholder="Occupation" aria-label="Occupation" {...register("occupation")} />
                <Input placeholder="Employer" aria-label="Employer" {...register("employer")} />
              </div>
            </fieldset>

            <fieldset className="space-y-4">
              <legend className="text-sm font-semibold text-foreground">Medical info</legend>
              <div className="space-y-1.5">
                <Label htmlFor="bloodType">Blood type</Label>
                <Select id="bloodType" {...register("bloodType")}>
                  <option value="">Unspecified</option>
                  {Object.values(PatientBloodType).map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="allergies">Allergies</Label>
                <Textarea id="allergies" rows={2} {...register("allergies")} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="medicalNotes">Medical notes</Label>
                <Textarea id="medicalNotes" rows={2} {...register("medicalNotes")} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="remarks">Remarks</Label>
                <Textarea id="remarks" rows={2} {...register("remarks")} />
              </div>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold text-foreground">Patient classification</legend>
              <label htmlFor="isYakapBeneficiary" className="flex items-center gap-2 text-sm">
                <input
                  id="isYakapBeneficiary"
                  type="checkbox"
                  className="h-4 w-4 rounded border-border"
                  {...register("isYakapBeneficiary")}
                />
                YAKAP beneficiary
              </label>
              <p className="text-xs text-muted-foreground">
                Marks this patient as a PhilHealth YAKAP beneficiary. Each queue ticket still lets the receptionist
                confirm or change how that specific visit is classified.
              </p>
            </fieldset>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" isLoading={isSubmitting || mutation.isPending}>
                {isEdit ? "Save changes" : "Add patient"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <DuplicateWarningDialog
        open={duplicates.length > 0}
        onOpenChange={(next) => {
          if (!next) setDuplicates([]);
        }}
        duplicates={duplicates}
        canOverride={canOverride}
        isSaving={mutation.isPending}
        onConfirmAnyway={() => {
          if (pendingValues) submit(pendingValues, true);
        }}
      />
    </>
  );
}
