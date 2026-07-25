'use client';

import React, { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { Download } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { StatCard } from '@/components/ui/stat-card';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Skeleton, StatCardSkeleton, DataTableSkeleton } from '@/components/ui/skeleton';

const KIND_LABELS: Record<string, string> = {
  stt_sec: 'STT Seconds',
  tts_sec: 'TTS Seconds',
  llm_tokens: 'LLM Tokens',
  agent_sec: 'Agent Seconds',
};

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

function DailyBarChart({ data }: { data: Array<{ day: string; total_qty: number }> }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">No usage recorded in this window.</p>;
  }

  const max = Math.max(1, ...data.map((d) => d.total_qty));

  return (
    <div>
      <div className="flex h-40 items-end gap-1 overflow-x-auto pb-1">
        {data.map((d) => {
          const heightPct = Math.max(2, (d.total_qty / max) * 100);
          return (
            <div
              key={d.day}
              title={`${d.day}: ${d.total_qty.toLocaleString()}`}
              className="flex h-full min-w-[8px] flex-1 flex-col justify-end"
            >
              <div className="w-full rounded-t bg-primary" style={{ height: `${heightPct}%` }} />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground">
        <span>{data[0]?.day}</span>
        <span>{data[data.length - 1]?.day}</span>
      </div>
    </div>
  );
}

export default function UsagePage() {
  const { data: usage, isLoading: loading, error } = useSWR(swrKeys.usage, swrFetchers.usage);

  const dailyByKind = useMemo(() => {
    const map = new Map<string, Array<{ day: string; total_qty: number }>>();
    for (const row of usage?.daily ?? []) {
      const list = map.get(row.kind) ?? [];
      list.push({ day: row.day, total_qty: row.total_qty });
      map.set(row.kind, list);
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.day.localeCompare(b.day));
    }
    return map;
  }, [usage]);

  const kinds = useMemo(() => Array.from(dailyByKind.keys()).sort(), [dailyByKind]);
  const [activeKind, setActiveKind] = useState<string>('');

  useEffect(() => {
    if (!activeKind && kinds.length > 0) {
      setActiveKind(kinds[0]);
    }
  }, [kinds, activeKind]);

  const handleExport = () => {
    if (!usage) return;
    const csv = toCsv(
      ['Day', 'Kind', 'Quantity'],
      usage.daily.map((row) => [row.day, kindLabel(row.kind), String(row.total_qty)]),
    );
    downloadCsv(`usage-${usage.window_days}d.csv`, csv);
  };

  return (
    <div>
      <PageHeader
        title="Usage"
        description="Provider usage and quota consumption for the last 30 days."
        actions={
          usage ? (
            <Button variant="secondary" onClick={handleExport}>
              <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Export CSV
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load usage data'}
        </div>
      ) : null}

      {loading ? (
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 pt-6">
              <Skeleton className="h-4 w-16" />
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-2 w-full" />
              </div>
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-2 w-full" />
              </div>
            </CardContent>
          </Card>
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 4 }, (_, i) => (
              <StatCardSkeleton key={i} />
            ))}
          </div>
          <Card>
            <CardContent className="pt-6">
              <DataTableSkeleton rows={3} />
            </CardContent>
          </Card>
        </div>
      ) : usage ? (
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 pt-6">
              <h2 className="text-sm font-semibold text-foreground">Quota</h2>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Concurrent calls</span>
                  <span className="font-medium text-foreground">
                    {usage.quota.concurrent_now} / {usage.quota.max_concurrent}
                  </span>
                </div>
                <Progress value={usage.quota.concurrent_now} max={usage.quota.max_concurrent} />
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Monthly minutes</span>
                  <span className="font-medium text-foreground">
                    {usage.quota.minutes_this_month.toFixed(1)} / {usage.quota.max_minutes_month}
                  </span>
                </div>
                <Progress value={usage.quota.minutes_this_month} max={usage.quota.max_minutes_month} />
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4">
            {['stt_sec', 'tts_sec', 'llm_tokens', 'agent_sec'].map((kind) => {
              const total = usage.totals.find((t) => t.kind === kind)?.total_qty ?? 0;
              return <StatCard key={kind} label={kindLabel(kind)} value={total} format="number" />;
            })}
          </div>

          <Card>
            <CardContent className="pt-6">
              <h2 className="mb-4 text-sm font-semibold text-foreground">
                Daily usage (last {usage.window_days} days)
              </h2>

              {kinds.length === 0 ? (
                <p className="text-sm text-muted-foreground">No usage recorded in this window.</p>
              ) : (
                <Tabs value={activeKind} onValueChange={setActiveKind}>
                  <TabsList label="Usage kind" className="mb-4">
                    {kinds.map((kind) => (
                      <TabsTrigger key={kind} value={kind}>
                        {kindLabel(kind)}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {kinds.map((kind) => (
                    <TabsContent key={kind} value={kind}>
                      <DailyBarChart data={dailyByKind.get(kind) ?? []} />
                    </TabsContent>
                  ))}
                </Tabs>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
