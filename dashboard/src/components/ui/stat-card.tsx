'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowDown, ArrowUp, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card } from './card';
import { Tooltip } from './tooltip';

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
  /** An up-arrow is not automatically good — pass `deltaIsGood` to color it. */
  delta?: StatDelta;
  /** When unset, the delta renders neutral (`text-muted-foreground`). */
  deltaIsGood?: boolean;
  tooltip?: string;
  accent?: 'default' | 'destructive';
  /** Makes the whole card a link. */
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

export function StatCard({
  label,
  value,
  format,
  delta,
  deltaIsGood,
  tooltip,
  accent = 'default',
  href,
  linkLabel,
  chart,
  subStats,
  className,
}: StatCardProps) {
  const isDestructive = accent === 'destructive';

  const deltaClass =
    deltaIsGood === undefined
      ? 'text-muted-foreground'
      : deltaIsGood
        ? 'text-foreground'
        : 'text-destructive';

  const DeltaArrow = delta?.direction === 'down' ? ArrowDown : ArrowUp;

  return (
    <Card className={cn('relative', isDestructive && 'border-destructive/40', className)}>
      {href ? (
        <Link
          href={href}
          aria-label={linkLabel ?? label}
          className="absolute inset-0 rounded-lg hover:bg-muted/20"
        />
      ) : null}

      <div className="flex flex-col gap-3 p-6">
        <div className="flex items-start justify-between gap-2">
          <span className="min-w-0 flex-1 break-words text-sm font-medium leading-snug text-muted-foreground">
            {label}
          </span>
          {tooltip ? (
            <span className="relative z-10 shrink-0">
              <Tooltip label={`More information about ${label}`} content={tooltip}>
                <Info className="h-4 w-4" aria-hidden="true" />
              </Tooltip>
            </span>
          ) : null}
        </div>

        <div
          className={cn(
            'text-3xl font-semibold tabular-nums',
            isDestructive ? 'text-destructive' : 'text-foreground',
          )}
        >
          {formatValue(value, format)}
        </div>

        {delta ? (
          <div className={cn('flex items-center gap-1 text-sm', deltaClass)}>
            <DeltaArrow className="h-4 w-4" aria-hidden="true" />
            <span className="font-medium tabular-nums">{Math.abs(delta.value).toLocaleString()}</span>
            <span className="text-muted-foreground">{delta.caption}</span>
          </div>
        ) : null}

        {subStats && subStats.length > 0 ? (
          <dl className="flex flex-col gap-1 border-t border-border pt-3 text-sm">
            {subStats.map((s) => (
              <div key={s.label} className="flex items-center justify-between gap-2">
                <dt className="text-muted-foreground">{s.label}</dt>
                <dd className="font-medium tabular-nums">{s.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {chart ? <div className="relative z-10 pt-1">{chart}</div> : null}
      </div>
    </Card>
  );
}
