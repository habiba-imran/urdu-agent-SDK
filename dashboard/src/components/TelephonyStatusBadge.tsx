'use client';

import React from 'react';
import useSWR from 'swr';
import { Phone, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';

export function TelephonyStatusBadge() {
  const { data: readiness, error, isLoading } = useSWR(
    swrKeys.telephonyReadiness,
    swrFetchers.telephonyReadiness,
    { refreshInterval: 30000 }
  );

  if (isLoading) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground">
        <RefreshCw className="h-3 w-3 animate-spin" />
        <span>Checking Telephony...</span>
      </div>
    );
  }

  if (error || !readiness) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
        <AlertCircle className="h-3 w-3 text-amber-600" />
        <span>Telephony Unconfigured</span>
      </div>
    );
  }

  const isReady = readiness.is_ready ?? readiness.ready ?? false;
  const reasons = readiness.reasons ?? readiness.missing_steps ?? [];

  if (isReady) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800">
        <CheckCircle2 className="h-3 w-3 text-emerald-600" />
        <span>Telephony Active</span>
      </div>
    );
  }

  const missingCount = reasons.length;
  return (
    <div className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs text-sky-800">
      <Phone className="h-3 w-3 text-sky-600" />
      <span>Telephony Setup ({missingCount} step{missingCount !== 1 ? 's' : ''} left)</span>
    </div>
  );
}
