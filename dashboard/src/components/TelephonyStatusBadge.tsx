'use client';

import React from 'react';
import useSWR from 'swr';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { Badge } from '@/components/ui/badge';

export function TelephonyStatusBadge() {
  const { data: readiness, error, isLoading } = useSWR(
    swrKeys.telephonyReadiness,
    swrFetchers.telephonyReadiness,
    { refreshInterval: 60_000 },
  );

  if (isLoading) {
    return (
      <Badge variant="secondary" dot="muted">
        Checking phone…
      </Badge>
    );
  }

  if (error || !readiness) {
    return (
      <Badge variant="warning" dot="warning">
        Phone unconfigured
      </Badge>
    );
  }

  const isReady = readiness.is_ready ?? readiness.ready ?? false;
  const reasons = readiness.reasons ?? readiness.missing_steps ?? [];

  if (isReady) {
    return (
      <Badge variant="success" dot="success">
        Phone active
      </Badge>
    );
  }

  const missingCount = reasons.length;
  return (
    <Badge variant="outline" dot="muted">
      Phone setup · {missingCount} step{missingCount !== 1 ? 's' : ''} left
    </Badge>
  );
}
