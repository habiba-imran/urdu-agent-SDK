'use client';

import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScrollLock } from '@/hooks/use-scroll-lock';

/**
 * Centered pop-up dialog, built on @radix-ui/react-dialog (real focus trap, ARIA wiring,
 * Escape-to-close, focus restoration). Sibling to `Drawer` (the right-side slide-over used
 * for record detail views) — this one is for on-demand content that belongs front-and-center
 * rather than beside the page: a form, a chart, a confirmation.
 *
 * `modal={false}` + `useScrollLock`, not Radix's built-in scroll lock: the built-in lock uses
 * a body `padding-right` scrollbar-compensation trick that is unreliable on mobile (overlay
 * scrollbars are zero-width) and can shove the whole page left when it fires.
 */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  footer,
  children,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  footer?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}): React.JSX.Element {
  useScrollLock(open);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <Dialog.Portal>
        {/*
          A plain `<div>`, not `Dialog.Overlay`: Radix's own overlay component hard-codes
          `return context.modal ? <Presence>… : null` — with `modal={false}` (required above
          to dodge the padding-right scroll-lock bug) it silently renders nothing at all, no
          matter what className is passed. This div reproduces the same dimmed backdrop
          without depending on `modal`; outside-click-to-close still works because Radix's
          dismiss handling listens for pointerdown outside `Dialog.Content`, not specifically
          on the overlay element.
        */}
        <div aria-hidden="true" className="fixed inset-0 z-[100] bg-foreground/60" />
        <Dialog.Content
          className={cn(
            // `max-h-[85dvh]`, not `vh` — this is `position: fixed`, so a `vh` height
            // resolves against the initial viewport size, which doesn't track the mobile
            // browser's address-bar collapse the way `dvh` does.
            'fixed left-1/2 top-1/2 z-[100] flex max-h-[85dvh] w-[calc(100vw-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border border-border bg-card text-card-foreground shadow-lg',
            'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95',
            className,
          )}
        >
          <div className="sticky top-0 z-10 flex shrink-0 items-start justify-between gap-4 rounded-t-lg border-b border-border bg-card px-6 py-4">
            <div className="flex flex-col gap-1">
              <Dialog.Title className="text-lg font-semibold leading-none tracking-tight">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="text-sm text-muted-foreground">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label="Close"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-4">{children}</div>

          {footer ? (
            <div className="shrink-0 rounded-b-lg border-t border-border bg-card px-6 py-4">{footer}</div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
