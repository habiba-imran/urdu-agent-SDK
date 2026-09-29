'use client';

import React, { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Check, Copy } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { isPortalAuthFailure } from '@/lib/portalAuth';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { StatCardSkeleton } from '@/components/ui/skeleton';
import { TelephonyStatusBadge } from '@/components/TelephonyStatusBadge';
import { cn } from '@/lib/utils';

function CopyableMono({
  label,
  value,
  loading,
}: {
  label: string;
  value: string | null | undefined;
  loading?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = () => {
    if (!value) return;
    void navigator.clipboard.writeText(value);
    setCopied(true);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <p className="font-mono-label text-text-muted">{label}</p>
      {loading ? (
        <p className="font-mono text-[13px] text-text-muted">Loading…</p>
      ) : (
        <div className="flex items-center gap-2 rounded-input border border-border bg-surface-muted px-3 py-2.5">
          <span
            title={value ?? undefined}
            className="min-w-0 flex-1 break-all font-mono text-[13px] text-text"
          >
            {value || 'Unavailable'}
          </span>
          {value ? (
            <button
              type="button"
              onClick={handleCopy}
              aria-label={copied ? `Copied ${label}` : `Copy ${label}`}
              title={copied ? 'Copied' : `Copy ${label}`}
              className={cn(
                'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-pill border border-border bg-surface text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text',
                copied && 'border-transparent bg-text text-white hover:bg-text hover:text-white',
              )}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              )}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function ChecklistRow({
  ok,
  label,
  detail,
  href,
  linkLabel,
}: {
  ok: boolean;
  label: string;
  detail: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <li className="flex items-start justify-between gap-3 border-b border-border/70 pb-3 last:border-0 last:pb-0">
      <div className="min-w-0 flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[15px] font-medium text-text">{label}</span>
          {ok ? (
            <Badge variant="success">Ready</Badge>
          ) : (
            <Badge variant="outline" dot="muted">
              Pending
            </Badge>
          )}
        </div>
        <p className="text-[13px] leading-relaxed text-text-muted">{detail}</p>
      </div>
      {href && linkLabel ? (
        <Link
          href={href}
          className="shrink-0 pt-0.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text underline-offset-4 hover:underline"
        >
          {linkLabel}
        </Link>
      ) : null}
    </li>
  );
}

export default function DashboardPage() {
  const { data: agents, isLoading: agentsLoading, error: agentsError } = useSWR(
    swrKeys.agents,
    swrFetchers.agents,
  );
  const { data: credentials, isLoading: credentialsLoading, error: credentialsError } = useSWR(
    swrKeys.credentials,
    swrFetchers.credentials,
  );
  const { data: usage, isLoading: usageLoading, error: usageError } = useSWR(
    swrKeys.usage,
    swrFetchers.usage,
  );
  const { data: managedNumbers } = useSWR(
    swrKeys.telephonyNumbers,
    swrFetchers.telephonyNumbers,
  );
  const { data: readiness } = useSWR(
    swrKeys.telephonyReadiness,
    swrFetchers.telephonyReadiness,
    { refreshInterval: 60_000 },
  );

  const error = agentsError ?? credentialsError ?? usageError;
  const showError = error && !isPortalAuthFailure(error);

  const concurrentNow = usage?.quota.concurrent_now ?? 0;
  const usedMinutes = usage?.quota.minutes_this_month ?? 0;
  const liveCount = concurrentNow;
  const totalNumbers = managedNumbers?.length ?? 0;

  const assignedNumberCount = useMemo(
    () => (managedNumbers ?? []).filter((n) => Boolean(n.assigned_agent_id)).length,
    [managedNumbers],
  );

  const hmacProvisioned = Boolean(
    credentials?.secret_provisioned ?? credentials?.hmac_secret_hash,
  );
  const originsCount = credentials?.allowed_origins?.filter((o) => o.trim()).length ?? 0;
  const hasAgents = (agents?.length ?? 0) > 0;
  const phoneReady = Boolean(readiness?.is_ready ?? readiness?.ready);

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Overview"
        description="Workspace status at a glance — agents, phone numbers, live calls, and keys."
        actions={<TelephonyStatusBadge />}
      />

      {showError ? (
        <div className="rounded-card border border-danger/30 bg-[#FBEAEA] px-4 py-3 text-[15px] text-danger">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load dashboard data'}
        </div>
      ) : null}

      <Card className="console-grid-hero overflow-hidden">
        <CardContent className="grid gap-4 p-6 pt-6 sm:grid-cols-2 lg:grid-cols-4">
          {agentsLoading ? (
            <StatCardSkeleton />
          ) : (
            <StatCard
              label="Agents"
              value={agents?.length ?? 0}
              href="/agents"
              linkLabel="View all agents"
              className="border-0 shadow-none"
            />
          )}
          <StatCard
            label="Phone numbers"
            value={totalNumbers}
            href="/agents"
            linkLabel="View on agents"
            className="border-0 shadow-none"
          />
          {usageLoading ? (
            <StatCardSkeleton />
          ) : (
            <StatCard
              label="Live calls"
              value={liveCount}
              href="/sessions"
              linkLabel="View sessions"
              className="border-0 shadow-none"
            />
          )}
          {usageLoading ? (
            <StatCardSkeleton />
          ) : (
            <StatCard
              label="Minutes this month"
              value={Number(usedMinutes.toFixed(1))}
              href="/usage"
              linkLabel="View usage"
              className="border-0 shadow-none"
            />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardContent className="flex flex-col gap-5 p-6 pt-6">
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono-label text-text-muted">Workspace keys</p>
              <Link
                href="/credentials"
                className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text underline-offset-4 hover:underline"
              >
                API Keys
              </Link>
            </div>

            <CopyableMono
              label="Publishable key"
              value={credentials?.publishable_key}
              loading={credentialsLoading}
            />
            <CopyableMono
              label="Tenant ID"
              value={credentials?.tenant_id}
              loading={credentialsLoading}
            />

            <div className="flex flex-col gap-1.5">
              <p className="font-mono-label text-text-muted">HMAC secret</p>
              <div className="flex flex-wrap items-center gap-2">
                {credentialsLoading ? (
                  <span className="text-[13px] text-text-muted">Loading…</span>
                ) : hmacProvisioned ? (
                  <Badge variant="success">Provisioned</Badge>
                ) : (
                  <Badge variant="warning">Not provisioned</Badge>
                )}
                {hmacProvisioned && credentials?.secret_masked ? (
                  <span className="font-mono text-[12px] text-text-muted">
                    {credentials.secret_masked}
                  </span>
                ) : null}
              </div>
              <p className="text-[13px] text-text-muted">
                Reveal or rotate only on API Keys — never embed the secret in a frontend.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <p className="font-mono-label text-text-muted">Allowed origins</p>
              <div className="flex flex-wrap items-center gap-2">
                {credentialsLoading ? (
                  <span className="text-[13px] text-text-muted">Loading…</span>
                ) : (
                  <Badge variant="outline" dot={originsCount > 0 ? 'success' : 'muted'}>
                    {originsCount} origin{originsCount === 1 ? '' : 's'}
                  </Badge>
                )}
                <Link
                  href="/credentials"
                  className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text underline-offset-4 hover:underline"
                >
                  Manage
                </Link>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-5 p-6 pt-6">
            <div className="flex items-center justify-between gap-3">
              <p className="font-mono-label text-text-muted">Readiness</p>
              <Link
                href="/docs/overview"
                className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text underline-offset-4 hover:underline"
              >
                Docs
              </Link>
            </div>
            <p className="text-[15px] leading-relaxed text-text-body">
              This console is read-only for agents and phone routing. Provision from your host
              codebase, then confirm status here.
            </p>
            <ul className="flex flex-col gap-3">
              <ChecklistRow
                ok={hasAgents}
                label="Agents"
                detail={
                  hasAgents
                    ? `${agents?.length ?? 0} agent${(agents?.length ?? 0) === 1 ? '' : 's'} visible`
                    : 'Create agents with @awaazlabs-uva/agents'
                }
                href="/agents"
                linkLabel="View"
              />
              <ChecklistRow
                ok={assignedNumberCount > 0}
                label="Number assignment"
                detail={
                  assignedNumberCount > 0
                    ? `${assignedNumberCount} number${assignedNumberCount === 1 ? '' : 's'} assigned`
                    : 'Assign numbers with @awaazlabs-uva/telephony'
                }
                href="/agents"
                linkLabel="View"
              />
              <ChecklistRow
                ok={hmacProvisioned}
                label="HMAC secret"
                detail={
                  hmacProvisioned
                    ? 'Backend signing secret is provisioned'
                    : 'Reveal or rotate from API Keys after sign-in'
                }
                href="/credentials"
                linkLabel="Keys"
              />
              <ChecklistRow
                ok={phoneReady}
                label="Phone path"
                detail={
                  phoneReady
                    ? 'Telephony outbound readiness reports ready'
                    : 'Connect Telnyx and routing from your backend SDK'
                }
                href="/docs/telephony"
                linkLabel="Guide"
              />
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
