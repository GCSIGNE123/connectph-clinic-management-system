"use client";

import { AlertTriangle, ShieldAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AlertItem } from "@/features/analytics/types";

export interface AlertsPanelProps {
  alerts: AlertItem[] | undefined;
  isLoading: boolean;
}

export function AlertsPanel({ alerts, isLoading }: AlertsPanelProps) {
  if (isLoading) return null;
  if (!alerts || alerts.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
          No active alerts. Everything looks normal.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Owner Alerts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.category}
            className={
              "flex items-start gap-2 rounded-md border p-3 text-sm " +
              (alert.severity === "critical"
                ? "border-destructive/40 bg-destructive/10 text-destructive"
                : "border-amber-400/40 bg-amber-400/10 text-amber-700 dark:text-amber-400")
            }
          >
            {alert.severity === "critical" ? (
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <span>{alert.message}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
