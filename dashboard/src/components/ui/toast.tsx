'use client';

import React, { useCallback, useState } from 'react';
import { Check } from 'lucide-react';

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
