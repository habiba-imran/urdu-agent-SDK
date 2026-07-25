'use client';

import React, { useId, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Hand-rolled tooltip. Opens on BOTH pointer hover and keyboard focus — never hover alone
 * — and closes on Escape, so its content is reachable without a mouse. The trigger is a
 * real `<button>` so it is in the tab order.
 */
export function Tooltip({
  content,
  children,
  label,
  className,
  contentClassName,
}: {
  /** Tooltip body. */
  content: React.ReactNode;
  /** Trigger contents (typically an icon). */
  children: React.ReactNode;
  /** Accessible name for the trigger button. Required — the trigger is usually icon-only. */
  label: string;
  className?: string;
  contentClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <span className={cn('relative inline-flex', className)}>
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? contentId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
        }}
        className="inline-flex items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
      >
        {children}
      </button>
      {open ? (
        <span
          role="tooltip"
          id={contentId}
          className={cn(
            'absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-xs -translate-x-1/2 rounded-md border border-border bg-popover px-3 py-2 text-left text-xs font-normal text-popover-foreground shadow-sm',
            contentClassName,
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
