import React from 'react';

import { cn } from '@/lib/utils';

export function Skeleton({ className }: { className?: string }): React.JSX.Element {
  return (
    <div aria-hidden="true" className={cn('animate-pulse rounded-input bg-surface-muted', className)} />
  );
}

export function StatCardSkeleton(): React.JSX.Element {
  return (
    <div className="rounded-card border border-border bg-surface p-6 shadow-card">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-10 w-20" />
      </div>
    </div>
  );
}

export function StatGridSkeleton({ cards = 4 }: { cards?: number }): React.JSX.Element {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: cards }, (_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function DataTableSkeleton({ rows = 8 }: { rows?: number }): React.JSX.Element {
  return (
    <div className="rounded-card border border-border bg-surface p-4 shadow-card">
      <Skeleton className="mb-4 h-9 w-full" />
      <div className="flex flex-col gap-3">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}
