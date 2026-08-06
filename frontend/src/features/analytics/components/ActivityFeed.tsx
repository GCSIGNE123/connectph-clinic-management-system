"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ActivityFeedItem } from "@/features/analytics/types";

export interface ActivityFeedProps {
  items: ActivityFeedItem[] | undefined;
  isLoading: boolean;
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffSec = Math.max(0, Math.floor(diffMs / 1000));
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

export function ActivityFeed({ items, isLoading }: ActivityFeedProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Real-time Activity Feed</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : !items || items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No recent activity.</p>
        ) : (
          <ul className="max-h-96 space-y-1 overflow-y-auto" data-testid="activity-feed-list">
            {items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 border-b border-border/50 py-2 text-sm last:border-0">
                <span className="text-foreground">{item.description}</span>
                <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{timeAgo(item.occurredAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
