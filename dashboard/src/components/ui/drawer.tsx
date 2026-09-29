'use client';

import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Right-side slide-over, built on @radix-ui/react-dialog for a real focus trap, ARIA
 * wiring, Escape-to-close, and focus restoration on close. Sticky header with title +
 * close; scrollable body.
 */
export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  trigger,
  footer,
  children,
  className,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description?: string;
  trigger?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[150] bg-foreground/60 data-[state=open]:animate-in data-[state=open]:fade-in data-[state=closed]:animate-out data-[state=closed]:fade-out" />
        <Dialog.Content
          className={cn(
            // `h-dvh`, not `h-full`/`h-screen` — this is `position: fixed`, so a percentage
            // or `vh` height resolves against the *initial* viewport size, which on mobile
            // doesn't shrink as the browser's address bar collapses while scrolling.
            'fixed right-0 top-0 z-[150] flex h-dvh w-full max-w-[640px] flex-col border-l border-border bg-surface text-text shadow-float',
            'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right',
            className,
          )}
        >
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border bg-surface/95 px-6 py-5 backdrop-blur-sm">
            <div className="min-w-0 flex flex-col gap-1.5">
              <Dialog.Title className="truncate font-sans text-xl font-semibold tracking-[-0.01em] text-text">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="truncate text-[13px] text-text-muted">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label="Close"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-pill border border-border bg-surface text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto overscroll-contain px-6 py-5">{children}</div>

          {footer ? (
            <div className="border-t border-border bg-surface px-6 py-4">{footer}</div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
