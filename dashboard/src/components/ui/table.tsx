'use client';

import React from 'react';
import { cn } from '@/lib/utils';

/**
 * Data table primitive. Every dense table gets a `<caption>` (visually hidden by default
 * so it names the table for screen readers without changing the visual layout), and every
 * header cell carries `scope="col"`.
 */
export function Table({
  className,
  tableClassName,
  children,
  caption,
  captionSrOnly = true,
}: {
  className?: string;
  /** Extra classes on the `<table>` itself — e.g. `table-fixed` for a table sized to always
   *  fit its container (columns wrap instead of forcing horizontal scroll). */
  tableClassName?: string;
  children: React.ReactNode;
  /** Accessible name for the table. Hidden visually unless `captionSrOnly` is false. */
  caption?: React.ReactNode;
  captionSrOnly?: boolean;
}) {
  return (
    <div className={cn('w-full overflow-auto', className)}>
      <table className={cn('w-full caption-bottom text-sm', tableClassName)}>
        {caption ? (
          <caption className={cn(captionSrOnly ? 'sr-only' : 'mt-4 text-sm text-muted-foreground')}>
            {caption}
          </caption>
        ) : null}
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return <thead className={cn('[&_tr]:border-b', className)}>{children}</thead>;
}

export function TableBody({ className, children }: { className?: string; children: React.ReactNode }) {
  return <tbody className={cn('[&_tr:last-child]:border-0', className)}>{children}</tbody>;
}

/**
 * A row. Pass `onClick` for row-activated tables.
 *
 * `onClick` is a **mouse convenience only**. The row deliberately does NOT take
 * `role="button"` or `tabIndex` — keyboard/assistive-technology access is provided instead
 * by `RowOpenButton`, a real `<button>` inside the first cell.
 *
 * Cells containing their own controls must call `stopPropagation()` so a click on them
 * doesn't also fire the row's `onClick`.
 */
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
      className={cn('border-b transition-colors hover:bg-muted/30', onClick && 'cursor-pointer', className)}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

/**
 * The keyboard-reachable control that opens a row's detail view. Lives in the first cell.
 * Its accessible name must identify the row, not merely say "Open".
 */
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
      className={cn('text-left font-medium text-foreground hover:underline', className)}
    >
      {children}
    </button>
  );
}

export function TableHead({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <th
      scope="col"
      className={cn('h-10 px-3 text-left align-middle font-medium text-muted-foreground', className)}
    >
      {children}
    </th>
  );
}

export function TableCell({ className, children }: { className?: string; children: React.ReactNode }) {
  return <td className={cn('p-3 align-middle', className)}>{children}</td>;
}

export function TableCaption({ className, children }: { className?: string; children: React.ReactNode }) {
  return <caption className={cn('mt-4 text-sm text-muted-foreground', className)}>{children}</caption>;
}
