'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Check, X, AlertCircle, CheckCircle2 } from 'lucide-react';

import { cn } from '@/lib/utils';

/** Minimal single-slot toast: enough for a "Copied!"-style confirmation, no queueing. */
export function useToast() {
  const [message, setMessage] = useState<string | null>(null);

  const showToast = useCallback((msg: string, durationMs = 2000) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(null), durationMs);
  }, []);

  return { message, showToast };
}

/**
 * Anchored above whatever it's rendered next to — wrap the trigger button in a
 * `relative` container and place this as a sibling; `bottom-full` pins it above.
 */
export function Toast({ message }: { message: string | null }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 flex -translate-x-1/2',
        'items-center gap-1.5 whitespace-nowrap rounded-md border border-border bg-foreground',
        'px-3 py-1.5 text-xs font-medium text-background shadow-lg transition-all duration-200',
        message ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0',
      )}
    >
      <Check className="h-3.5 w-3.5" />
      {message}
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Fixed (viewport-anchored) toast — appears at the bottom-right of the screen,
 * auto-dismisses, and supports success / error variants.
 * -------------------------------------------------------------------------*/

type FixedToastVariant = 'success' | 'error';

interface FixedToastState {
  message: string;
  variant: FixedToastVariant;
}

export function useFixedToast(defaultDuration = 4000) {
  const [state, setState] = useState<FixedToastState | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => setState(null), []);

  const showFixedToast = useCallback(
    (msg: string, variant: FixedToastVariant = 'success', durationMs?: number) => {
      // Clear any pending timer so rapid toggles don't leave stale toasts.
      if (timerRef.current) clearTimeout(timerRef.current);
      setState({ message: msg, variant });
      timerRef.current = setTimeout(() => setState(null), durationMs ?? defaultDuration);
    },
    [defaultDuration],
  );

  // Cleanup on unmount.
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  return { fixedToast: state, showFixedToast, dismissFixedToast: dismiss };
}

const variantStyles: Record<FixedToastVariant, string> = {
  success:
    'border-[var(--success)]/30 bg-[var(--surface)] text-[var(--success)] shadow-[0_4px_24px_rgba(31,157,85,0.12)]',
  error:
    'border-[var(--danger)]/30 bg-[var(--surface)] text-[var(--danger)] shadow-[0_4px_24px_rgba(214,69,69,0.12)]',
};

const VariantIcon: Record<FixedToastVariant, React.FC<{ className?: string }>> = {
  success: CheckCircle2,
  error: AlertCircle,
};

export function FixedToast({
  toast,
  onDismiss,
}: {
  toast: FixedToastState | null;
  onDismiss: () => void;
}) {
  const Icon = toast ? VariantIcon[toast.variant] : CheckCircle2;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-none fixed bottom-6 right-4 z-[9999] flex w-[calc(100%-2rem)] max-w-sm sm:right-6',
        'items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium',
        'transition-all duration-300 ease-out motion-reduce:transition-none',
        toast
          ? cn('pointer-events-auto translate-y-0 opacity-100', variantStyles[toast.variant])
          : 'translate-y-3 opacity-0',
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="text-[var(--text)]">{toast?.message}</span>
      {toast && (
        <button
          type="button"
          aria-label="Dismiss notification"
          onClick={onDismiss}
          className="ml-1 rounded-md p-0.5 opacity-60 transition-opacity hover:opacity-100 focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
