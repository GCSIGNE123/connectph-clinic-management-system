"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { pathologistsApi } from "@/features/pathologists/api/pathologists-api";
import type { Pathologist } from "@/features/pathologists/types";
import { PathologistSignatureSettings } from "@/features/pathologists/components/PathologistSignatureSettings";

/**
 * Pathologist detail page: Settings → Pathologists → Select Pathologist →
 * E-Signature. Mirrors `doctors/[id]/page.tsx` exactly (see that file's
 * own docstring for why this is a dedicated page rather than a modal tab).
 */
export default function PathologistDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const pathologistQuery = useQuery({
    queryKey: ["pathologists", "detail", params.id],
    queryFn: () => pathologistsApi.get(params.id),
  });
  const [pathologist, setPathologist] = useState<Pathologist | null>(null);
  const current = pathologist ?? pathologistQuery.data ?? null;

  if (pathologistQuery.isLoading || !current) {
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
        <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/pathologists")}>
          <ArrowLeft className="mr-1.5 h-4 w-4" aria-hidden="true" />
          Back to Pathologists
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-semibold">{current.name}</h1>
        <p className="text-sm text-muted-foreground">{current.license_number ?? "No license number on file"}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>E-Signature</CardTitle>
        </CardHeader>
        <CardContent>
          <PathologistSignatureSettings pathologist={current} onPathologistUpdated={setPathologist} />
        </CardContent>
      </Card>
    </div>
  );
}
