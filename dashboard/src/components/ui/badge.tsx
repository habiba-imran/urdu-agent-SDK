'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeVariant = 'secondary' | 'outline' | 'destructive' | 'default' | 'warning';

export function Badge({
  className,
  children,
  variant = 'secondary',
}: {
  className?: string;
  children: React.ReactNode;
  variant?: BadgeVariant;
}) {
  const base =
    'inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors';
  const variants: Record<BadgeVariant, string> = {
    secondary: 'border-transparent bg-muted text-muted-foreground',
    outline: 'border-border bg-transparent text-foreground',
    destructive: 'border-destructive/30 bg-destructive/10 text-destructive',
    default: 'border-border bg-foreground text-background',
    // Amber is low contrast by design: the caller always supplies a text label so the
    // color is reinforcement, not the signal.
    warning: 'border-transparent bg-status-warning text-foreground',
  };

  return <span className={cn(base, variants[variant], className)}>{children}</span>;
}
