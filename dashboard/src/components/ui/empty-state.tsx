'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export function EmptyState({
  icon: _icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-4 rounded-card border border-border bg-surface px-6 py-16 text-center shadow-card',
        className,
      )}
    >
      <div className="flex max-w-md flex-col gap-2">
        <p className="font-sans text-xl font-semibold tracking-[-0.01em] text-text">{title}</p>
        {description ? <p className="text-[15px] leading-relaxed text-text-body">{description}</p> : null}
      </div>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
