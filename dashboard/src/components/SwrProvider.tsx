'use client';

import React from 'react';
import { SWRConfig } from 'swr';

/**
 * Client caching defaults for the tenant console.
 * - revalidateOnFocus off: switching browser tabs must not refetch sessions/Telnyx.
 * - longer dedupe: rapid nav / double-mount shares one in-flight request.
 */
export function SwrProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        revalidateOnReconnect: true,
        dedupingInterval: 5_000,
        errorRetryCount: 2,
      }}
    >
      {children}
    </SWRConfig>
  );
}
