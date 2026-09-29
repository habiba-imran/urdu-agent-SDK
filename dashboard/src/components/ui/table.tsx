'use client';

import React from 'react';
import { cn } from '@/lib/utils';

export function Table({
  className,
  tableClassName,
  children,
  caption,
  captionSrOnly = true,
}: {
  className?: string;
  tableClassName?: string;
  children: React.ReactNode;
  caption?: React.ReactNode;
  captionSrOnly?: boolean;
}) {
  return (
    <div className={cn('w-full overflow-auto rounded-card border border-border bg-surface shadow-card', className)}>
      <table className={cn('w-full caption-bottom text-[15px]', tableClassName)}>
        {caption ? (
          <caption className={cn(captionSrOnly ? 'sr-only' : 'mt-4 text-sm text-text-muted')}>
            {caption}
          </caption>
        ) : null}
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return <thead className={cn(className)}>{children}</thead>;
}

export function TableBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <tbody className={cn('[&_tr:last-child]:border-0', className)}>{children}</tbody>;
}

export function TableRow({
  className,
  children,
  onClick,
}: {
  className?: string;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <tr
      className={cn(
        'h-14 border-b border-border transition-colors duration-console hover:bg-surface-muted',
        onClick && 'cursor-pointer',
        className,
      )}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

export function RowOpenButton({
  onClick,
  ariaLabel,
  children,
  className,
}: {
  onClick: () => void;
  ariaLabel: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      aria-label={ariaLabel}
      className={cn('text-left font-medium text-text transition-colors duration-console hover:text-accent', className)}
    >
      {children}
    </button>
  );
}

export function TableHead({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <th
      scope="col"
      className={cn(
        'h-12 px-4 text-left align-middle font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted',
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TableCell({ className, children }: { className?: string; children: React.ReactNode }) {
  return <td className={cn('px-4 py-3 align-middle text-text-body', className)}>{children}</td>;
}

export function TableCaption({ className, children }: { className?: string; children: React.ReactNode }) {
  return <caption className={cn('mt-4 text-sm text-text-muted', className)}>{children}</caption>;
}
