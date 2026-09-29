'use client';

import React from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Card } from './card';

export type StatFormat = 'number' | 'percent' | 'currency' | 'text';

export interface StatDelta {
  value: number;
  direction: 'up' | 'down';
  caption: string;
}

export interface SubStat {
  label: string;
  value: string;
}

export interface StatCardProps {
  label: string;
  value: string | number;
  format?: StatFormat;
  delta?: StatDelta;
  deltaIsGood?: boolean;
  tooltip?: string;
  accent?: 'default' | 'destructive';
  href?: string;
  linkLabel?: string;
  chart?: React.ReactNode;
  subStats?: SubStat[];
  className?: string;
}

function formatValue(value: string | number, format?: StatFormat): string {
  if (typeof value === 'string') return value;
  switch (format) {
    case 'percent':
      return `${value.toLocaleString()}%`;
    case 'currency':
      return `$${value.toLocaleString()}`;
    case 'number':
      return value.toLocaleString();
    case 'text':
    default:
      return String(value);
  }
}

/** Editorial stat: mono label + large tabular number. Charts/icons intentionally omitted. */
export function StatCard({
  label,
  value,
  format,
  accent = 'default',
  href,
  linkLabel,
  className,
}: StatCardProps) {
  const isDestructive = accent === 'destructive';

  return (
    <Card className={cn('relative overflow-hidden', className)}>
      {href ? (
        <Link
          href={href}
          aria-label={linkLabel ?? label}
          className="absolute inset-0 rounded-card transition-colors duration-console hover:bg-surface-muted/40"
        />
      ) : null}

      <div className="flex flex-col gap-3 p-6">
        <span className="font-mono-label text-text-muted">{label}</span>
        <div
          className={cn(
            'font-sans text-[40px] font-bold leading-none tracking-[-0.03em] tabular-nums',
            isDestructive ? 'text-danger' : 'text-text',
          )}
        >
          {formatValue(value, format)}
        </div>
      </div>
    </Card>
  );
}
