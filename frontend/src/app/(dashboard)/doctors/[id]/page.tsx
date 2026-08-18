"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import type { Doctor } from "@/features/clinic-config/types";
import { DoctorSignatureSettings } from "@/features/doctors/components/DoctorSignatureSettings";

const doctorsApi = createCrudApi<Doctor>("/doctors");

/**
 * Doctor detail page: Settings → Doctors → Select Doctor → E-Signature.
 * A dedicated page (rather than squeezing into the existing generic
 * `MasterDataFormDialog` single-tab modal) since the doctor profile
 * modal has no tabs/sections and no file-upload field type - see the
 * Doctor E-Signature design investigation. Only the E-Signature section
 * exists here today; the rest of the doctor's profile (name, PRC/PTR,
 * department, fee, ...) is unchanged and still edited from the existing
 * Doctors list's "Edit" modal.
 */
export default function DoctorDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const doctorQuery = useQuery({
    queryKey: ["doctors", "detail", params.id],
    queryFn: () => doctorsApi.get(params.id),
  });
  const [doctor, setDoctor] = useState<Doctor | null>(null);
  const current = doctor ?? doctorQuery.data ?? null;

  if (doctorQuery.isLoading || !current) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/doctors")}>
          <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
          Back to Doctors
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-semibold">Dr. {current.first_name} {current.last_name}</h1>
        <p className="text-sm text-muted-foreground">{current.doctor_code}{current.specialization ? ` · ${current.specialization}` : ""}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>E-Signature</CardTitle>
        </CardHeader>
        <CardContent>
          <DoctorSignatureSettings doctor={current} onDoctorUpdated={setDoctor} />
        </CardContent>
      </Card>
    </div>
  );
}
