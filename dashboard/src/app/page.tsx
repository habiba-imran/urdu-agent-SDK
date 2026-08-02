'use client';

import React from 'react';
import Link from 'next/link';
import useSWR from 'swr';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Progress } from '@/components/ui/progress';
import { Skeleton, StatCardSkeleton, DataTableSkeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';

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
  const { data: sessions, isLoading: sessionsLoading, error: sessionsError } = useSWR(
    swrKeys.sessions,
    swrFetchers.sessions,
  );

  const error = agentsError ?? credentialsError ?? usageError ?? sessionsError;

  const concurrentNow = usage?.quota.concurrent_now ?? 0;
  const maxConcurrent = usage?.quota.max_concurrent ?? 0;
  const usedMinutes = usage?.quota.minutes_this_month ?? 0;
  const monthlyCap = usage?.quota.max_minutes_month ?? 0;
  const liveCount = (sessions ?? []).filter((s) => s.live).length;

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Manage your Urdu voice agents, credentials, and real-time usage quotas."
      />

      {error ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load dashboard data'}
        </div>
      ) : null}

      <div className="mb-4 grid gap-4 grid-cols-2">
        {agentsLoading ? (
          <StatCardSkeleton />
        ) : (
          <StatCard label="Active Agents" value={agents?.length ?? 0} />
        )}
        {usageLoading ? (
          <StatCardSkeleton />
        ) : (
          <StatCard
            label="Concurrent Calls"
            value={`${concurrentNow} / ${maxConcurrent}`}
            chart={<Progress value={concurrentNow} max={maxConcurrent} />}
          />
        )}
      </div>

      <div className="mb-6 grid gap-4 grid-cols-2">
        {usageLoading ? (
          <StatCardSkeleton />
        ) : (
          <StatCard
            label="Monthly Usage"
            value={`${usedMinutes.toFixed(1)} min`}
            subStats={[{ label: 'Cap', value: `${monthlyCap} min` }]}
            chart={<Progress value={usedMinutes} max={monthlyCap} />}
            href="/usage"
            linkLabel="View full usage breakdown"
          />
        )}
        {sessionsLoading ? (
          <StatCardSkeleton />
        ) : (
          <StatCard
            label="Live Calls Now"
            value={liveCount}
            chart={
              liveCount > 0 ? (
                <div className="flex items-center gap-1.5 text-xs text-emerald-600">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-600" />
                  </span>
                  Live now
                </div>
              ) : undefined
            }
            href="/sessions"
            linkLabel="View call sessions"
          />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-6 py-4">
            <h2 className="text-lg font-semibold text-foreground">Configured Voice Agents</h2>
            <Link
              href="/agents"
              className={cn(
                'inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'bg-primary text-primary-foreground hover:bg-primary/90',
              )}
            >
              + New Agent
            </Link>
          </div>
          <CardContent className="pt-6">
            {agentsLoading ? (
              <DataTableSkeleton rows={4} />
            ) : (agents ?? []).length === 0 ? (
              <EmptyState
                title="No agents found for this tenant"
                description="Create your first agent to get started."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent Name</TableHead>
                    <TableHead>Selected Voice</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(agents ?? []).map((agent) => (
                    <TableRow key={agent.id}>
                      <TableCell className="font-medium">{agent.name}</TableCell>
                      <TableCell>
                        <Badge>{agent.voice_id}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">Active</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-4 pt-6">
            <h2 className="text-lg font-semibold text-foreground">Integration Specs</h2>
            <p className="text-sm text-muted-foreground">
              Your host backend signs HMAC tokens using your assigned secret key before
              dispatching client WebRTC sessions.
            </p>

            <div className="rounded-md bg-muted p-4">
              <div className="mb-1 text-xs font-medium text-muted-foreground">PUBLISHABLE KEY</div>
              {credentialsLoading ? (
                <Skeleton className="h-5 w-full" />
              ) : (
                <div className="break-all font-mono text-sm text-foreground">
                  {credentials?.publishable_key ?? 'Unavailable'}
                </div>
              )}
            </div>

            <Link
              href="/credentials"
              className={cn(
                'inline-flex w-full items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                'bg-muted text-foreground hover:bg-muted/70',
              )}
            >
              View Full Credentials
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
