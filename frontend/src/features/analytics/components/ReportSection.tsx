"use client";

import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export interface ReportSectionProps {
  title: string;
  isLoading: boolean;
  filters: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

export function ReportSection({ title, isLoading, filters, actions, children }: ReportSectionProps) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="text-base">{title}</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          {filters}
          {actions}
        </div>
      </CardHeader>
      <CardContent>{isLoading ? <Skeleton className="h-64 w-full" /> : children}</CardContent>
    </Card>
  );
}
