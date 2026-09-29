'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export function Progress({
  value,
  max,
  className,
}: {
  value: number;
  max: number;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn('h-2 w-full overflow-hidden rounded-pill bg-surface-muted', className)}
    >
      <div
        className="h-full rounded-pill bg-text transition-all duration-console"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
