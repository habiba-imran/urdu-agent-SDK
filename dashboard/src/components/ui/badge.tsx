'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeVariant = 'secondary' | 'outline' | 'destructive' | 'default' | 'warning' | 'success';

export function Badge({
  className,
  children,
  variant = 'secondary',
  dot,
}: {
  className?: string;
  children: React.ReactNode;
  variant?: BadgeVariant;
  /** Optional status color for the 6px leading dot */
  dot?: 'success' | 'warning' | 'danger' | 'muted';
}) {
  const base =
    'inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-mono text-[11px] font-medium uppercase tracking-[0.14em]';
  const variants: Record<BadgeVariant, string> = {
    secondary: 'bg-surface-muted text-text-body',
    outline: 'border border-border bg-surface text-text-body',
    destructive: 'bg-[#FBEAEA] text-danger',
    default: 'bg-text text-white',
    warning: 'bg-[#FBF0DC] text-warning',
    success: 'bg-[#E6F6EE] text-success',
  };

  const inferredDot =
    dot ??
    (variant === 'destructive'
      ? 'danger'
      : variant === 'warning'
        ? 'warning'
        : variant === 'success'
          ? 'success'
          : undefined);

  const dotColor =
    inferredDot === 'success'
      ? 'bg-success'
      : inferredDot === 'warning'
        ? 'bg-warning'
        : inferredDot === 'danger'
          ? 'bg-danger'
          : inferredDot === 'muted'
            ? 'bg-text-muted'
            : null;

  return (
    <span className={cn(base, variants[variant], className)}>
      {dotColor ? <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', dotColor)} aria-hidden /> : null}
      {children}
    </span>
  );
}
