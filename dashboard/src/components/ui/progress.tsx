'use client';

import React from 'react';
import { cn } from '@/lib/utils';

/** Simple determinate progress bar — not part of the vendored AwaazLabs set (they don't
 *  have one either), written fresh to match the same token-driven visual language. */
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
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
    >
      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}
