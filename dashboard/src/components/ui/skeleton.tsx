import React from 'react';

import { cn } from '@/lib/utils';

/** Loading placeholder. `aria-hidden` since a screen reader should hear a status message
 *  from the caller, not have empty grey boxes described to it. */
export function Skeleton({ className }: { className?: string }): React.JSX.Element {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-md bg-muted', className)} />;
}

export function StatCardSkeleton(): React.JSX.Element {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-9 w-20" />
        <Skeleton className="h-4 w-36" />
      </div>
    </div>
  );
}

export function StatGridSkeleton({ cards = 4 }: { cards?: number }): React.JSX.Element {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      {Array.from({ length: cards }, (_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function DataTableSkeleton({ rows = 8 }: { rows?: number }): React.JSX.Element {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <Skeleton className="mb-4 h-9 w-full" />
      <div className="flex flex-col gap-3">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  );
}
