'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { ChevronLeft, ChevronRight, Download } from 'lucide-react';

import { getUsageSummary } from '@/lib/portalApi';
import { isPortalAuthFailure } from '@/lib/portalAuth';
import { downloadCsv } from '@/lib/csv';
import { buildUsageExportCsv, usageExportFilename } from '@/lib/usageExport';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Toast, useToast } from '@/components/ui/toast';

const KIND_META: Record<
  string,
  { label: string; unit: string; toDisplay: (qty: number) => string }
> = {
  agent_sec: {
    label: 'Agent time',
    unit: 'min',
    toDisplay: (q) => (q / 60).toFixed(1),
  },
  stt_sec: {
    label: 'STT',
    unit: 'sec',
    toDisplay: (q) => q.toLocaleString(undefined, { maximumFractionDigits: 1 }),
  },
  tts_sec: {
    label: 'TTS',
    unit: 'sec',
    toDisplay: (q) => q.toLocaleString(undefined, { maximumFractionDigits: 1 }),
  },
  llm_tokens: {
    label: 'LLM tokens',
    unit: 'tok',
    toDisplay: (q) => q.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  },
};

const BREAKDOWN_ORDER = ['agent_sec', 'stt_sec', 'tts_sec', 'llm_tokens'] as const;

/** "2026-07-01" -> "July 2026". Parses Y/M/D directly (not UTC Date parse). */
function monthLabel(periodStartIso: string | undefined): string {
  const [year, month] = (periodStartIso ?? '').split('-').map(Number);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return 'This month';
  }
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  });
}

function todayIso(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-${String(now.getUTCDate()).padStart(2, '0')}`;
}

function shortDay(iso: string): string {
  const [, m, d] = iso.split('-').map(Number);
  if (!Number.isFinite(m) || !Number.isFinite(d)) return iso;
  return `${m}/${d}`;
}

/** Zero-fill every day from period start through fillEnd (exclusive), matching period_end semantics. */
function fillMissingDays(
  data: ReadonlyArray<{ day: string; total_qty: number }>,
  periodStart: string,
  fillEndExclusive: string,
): Array<{ day: string; total_qty: number }> {
  const [sy, sm, sd] = periodStart.split('-').map(Number);
  const [ey, em, ed] = fillEndExclusive.split('-').map(Number);
  if (![sy, sm, sd, ey, em, ed].every(Number.isFinite)) {
    return [...data].sort((a, b) => a.day.localeCompare(b.day));
  }

  // Build calendar days in UTC so chart buckets match billing day keys.
  const start = Date.UTC(sy, sm - 1, sd);
  const end = Date.UTC(ey, em - 1, ed);

  const byDay = new Map(data.map((d) => [d.day, d.total_qty]));
  const out: Array<{ day: string; total_qty: number }> = [];
  for (let t = start; t < end; t += 24 * 60 * 60 * 1000) {
    const d = new Date(t);
    const iso = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
    out.push({ day: iso, total_qty: byDay.get(iso) ?? 0 });
  }
  return out;
}

function chartFillEnd(_periodStart: string, periodEnd: string, isCurrent: boolean): string {
  if (!isCurrent) return periodEnd;
  const today = todayIso();
  const [y, m, d] = today.split('-').map(Number);
  const tomorrow = new Date(Date.UTC(y, m - 1, d + 1));
  const tomorrowIso = `${tomorrow.getUTCFullYear()}-${String(tomorrow.getUTCMonth() + 1).padStart(2, '0')}-${String(tomorrow.getUTCDate()).padStart(2, '0')}`;
  return tomorrowIso < periodEnd ? tomorrowIso : periodEnd;
}

function toMonthKeyUTC(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

function currentMonthKey(): string {
  return toMonthKeyUTC(new Date());
}

function shiftMonth(monthKey: string, delta: number): string {
  const [y, m] = monthKey.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return toMonthKeyUTC(d);
}

function earliestMonthKey(): string {
  const d = new Date();
  return toMonthKeyUTC(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 35, 1)));
}

type QuotaTone = 'ok' | 'high' | 'limit';

function quotaTone(used: number, max: number): QuotaTone {
  if (max <= 0) return 'ok';
  const pct = used / max;
  if (pct >= 1) return 'limit';
  if (pct >= 0.8) return 'high';
  return 'ok';
}

function toneLabel(tone: QuotaTone): string {
  if (tone === 'limit') return 'At limit';
  if (tone === 'high') return 'High';
  return 'OK';
}

function Meter({
  value,
  max,
  tone,
}: {
  value: number;
  max: number;
  tone: QuotaTone;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className="h-2 w-full overflow-hidden rounded-pill bg-surface-muted"
    >
      <div
        className={cn(
          'h-full rounded-pill transition-all duration-console',
          tone === 'limit' && 'bg-danger',
          tone === 'high' && 'bg-warning',
          tone === 'ok' && 'bg-text',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function DailyMinutesChart({
  data,
  showTodayMarker = true,
}: {
  data: Array<{ day: string; minutes: number }>;
  showTodayMarker?: boolean;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const today = todayIso();
  const hasAny = data.some((d) => d.minutes > 0);
  const max = Math.max(...data.map((d) => d.minutes), 0);
  const hovered = data.find((d) => d.day === hover) ?? null;

  if (data.length === 0 || !hasAny) {
    return (
      <div className="flex min-h-[11rem] flex-col items-start justify-center gap-2 rounded-input bg-surface-muted/60 px-5 py-8">
        <p className="font-mono-label text-text-muted">No daily graph yet</p>
        <p className="max-w-md text-[15px] text-text-body">
          Agent minutes will plot here once you have session time this month. Totals above still
          update from quota.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex min-h-[1.25rem] items-baseline justify-between gap-3">
        <p className="font-mono text-[12px] text-text-muted">
          {hovered
            ? `${hovered.day} · ${hovered.minutes.toFixed(1)} min`
            : 'Hover a day'}
        </p>
        <p className="font-mono text-[12px] text-text-muted">max {max.toFixed(1)} min</p>
      </div>

      <div
        className="flex h-44 items-stretch gap-0.5"
        onMouseLeave={() => setHover(null)}
      >
        {data.map((d) => {
          const heightPct = d.minutes > 0 ? Math.max(6, (d.minutes / max) * 100) : 0;
          const isToday = showTodayMarker && d.day === today;
          const isHover = hover === d.day;
          return (
            <button
              key={d.day}
              type="button"
              title={`${d.day}: ${d.minutes.toFixed(1)} min`}
              aria-label={`${d.day}: ${d.minutes.toFixed(1)} minutes`}
              className="relative flex h-full min-w-[3px] flex-1 flex-col justify-end outline-none"
              onMouseEnter={() => setHover(d.day)}
              onFocus={() => setHover(d.day)}
            >
              {d.minutes > 0 ? (
                <div
                  className={cn(
                    'w-full min-h-[6px] rounded-t-sm bg-[#0a0a0a] transition-opacity duration-console',
                    isHover || isToday ? 'opacity-100' : 'opacity-75',
                  )}
                  style={{ height: `${heightPct}%` }}
                />
              ) : isToday ? (
                <div className="h-0.5 w-full bg-border" aria-hidden />
              ) : (
                <div className="h-px w-full bg-border/60" aria-hidden />
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex justify-between font-mono text-[11px] text-text-muted">
        <span>{shortDay(data[0].day)}</span>
        <span>{showTodayMarker ? 'Today' : shortDay(data[Math.floor(data.length / 2)]?.day ?? '')}</span>
        <span>{shortDay(data[data.length - 1].day)}</span>
      </div>
    </div>
  );
}

export default function UsagePage() {
  // undefined = follow server current UTC month (avoids local TZ / UTC drift at month edges)
  const [month, setMonth] = useState<string | undefined>(undefined);

  const { data: usage, error, isLoading, isValidating } = useSWR(
    ['usage', month ?? 'current'],
    () => getUsageSummary(month),
    { keepPreviousData: true, revalidateOnFocus: false },
  );

  const serverCurrent = usage?.current_month;
  const activeMonth = month ?? serverCurrent ?? currentMonthKey();
  const isCurrentPeriod = usage?.is_current_period ?? month === undefined;
  const canGoPrev = activeMonth > earliestMonthKey();
  const canGoNext = Boolean(serverCurrent && activeMonth < serverCurrent);
  const switching = Boolean(usage) && isValidating;

  const goPrev = () => {
    setMonth(shiftMonth(activeMonth, -1));
  };
  const goNext = () => {
    if (!serverCurrent) return;
    const next = shiftMonth(activeMonth, 1);
    setMonth(next >= serverCurrent ? undefined : next);
  };

  const dailyMinutes = useMemo(() => {
    if (!usage?.period_start || !usage?.period_end) return [];
    const agentDays = (usage.daily ?? []).filter((r) => r.kind === 'agent_sec');
    const fillEnd = chartFillEnd(usage.period_start, usage.period_end, isCurrentPeriod);
    const filled = fillMissingDays(agentDays, usage.period_start, fillEnd);
    return filled.map((d) => ({ day: d.day, minutes: d.total_qty / 60 }));
  }, [usage, isCurrentPeriod]);

  const hasAgentTraffic = dailyMinutes.some((d) => d.minutes > 0);
  const hasAnyTotals = (usage?.totals ?? []).some((t) => t.total_qty > 0);

  const { message: toastMessage, showToast } = useToast();

  const handleExport = () => {
    if (!usage) return;
    try {
      const csv = buildUsageExportCsv(usage);
      downloadCsv(usageExportFilename(usage), csv);
      showToast('CSV exported');
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'CSV export failed');
    }
  };

  const minutesUsed = usage?.billable_minutes ?? usage?.quota.minutes_this_month ?? 0;
  const minutesMax = usage?.quota.max_minutes_month ?? 0;
  const concurrentNow = usage?.quota.concurrent_now ?? 0;
  const concurrentMax = usage?.quota.max_concurrent ?? 0;
  const minutesTone = quotaTone(minutesUsed, minutesMax);
  const concurrentTone = quotaTone(concurrentNow, concurrentMax);
  const minutesPct =
    minutesMax > 0 ? Math.min(100, Math.max(0, (minutesUsed / minutesMax) * 100)) : 0;
  const minutesLeft = Math.max(0, minutesMax - minutesUsed);
  const agentSec = usage?.billable_agent_sec ?? 0;

  const monthNav = (
    <div className="flex items-center gap-1 rounded-pill border border-border bg-surface p-1">
      <button
        type="button"
        aria-label="Previous month"
        disabled={!canGoPrev || switching}
        onClick={goPrev}
        className="inline-flex h-9 w-9 items-center justify-center rounded-pill text-text transition-colors duration-console hover:bg-surface-muted disabled:pointer-events-none disabled:opacity-30"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
      </button>
      <span className="min-w-[7.5rem] text-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text">
        {monthLabel(`${activeMonth}-01`)}
      </span>
      <button
        type="button"
        aria-label="Next month"
        disabled={!canGoNext || switching}
        onClick={goNext}
        className="inline-flex h-9 w-9 items-center justify-center rounded-pill text-text transition-colors duration-console hover:bg-surface-muted disabled:pointer-events-none disabled:opacity-30"
      >
        <ChevronRight className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );

  const showInitialSkeleton = isLoading && !usage;

  return (
    <div>
      <PageHeader
        title="Usage"
        breadcrumbLabel="Usage"
        eyebrow="Usage"
        description={
          isCurrentPeriod
            ? 'Billable agent minutes for the current UTC calendar month — from usage_events, the billing source of truth.'
            : `Billable agent minutes for ${monthLabel(`${activeMonth}-01`)} (UTC). Live concurrent only applies to the current month.`
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {monthNav}
            {usage ? (
              <div className="relative">
                <Toast message={toastMessage} />
                <Button variant="secondary" onClick={handleExport} disabled={switching}>
                  <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
                  Export CSV
                </Button>
              </div>
            ) : null}
          </div>
        }
      />

      {error && !isPortalAuthFailure(error) ? (
        <div className="mb-6 rounded-card border border-danger/30 bg-[#FBEAEA] px-4 py-3 text-[15px] text-danger">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load usage data'}
        </div>
      ) : null}

      {showInitialSkeleton ? (
        <div className="flex flex-col gap-8">
          <Card className="console-grid-hero overflow-hidden">
            <CardContent className="flex flex-col gap-6 p-6 pt-6 sm:p-8">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-12 w-64" />
              <Skeleton className="h-2 w-full" />
              <Skeleton className="h-3 w-40" />
            </CardContent>
          </Card>
          <Skeleton className="h-56 w-full rounded-card" />
          <Skeleton className="h-40 w-full rounded-card" />
        </div>
      ) : usage ? (
        <div
          className={cn(
            'flex flex-col gap-8 transition-opacity duration-console',
            switching && 'opacity-60',
          )}
        >
          <Card className="console-grid-hero overflow-hidden">
            <CardContent className="flex flex-col gap-8 p-6 pt-6 sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex flex-col gap-3">
                  <p className="font-mono-label text-text-muted">
                    {monthLabel(usage.period_start)} · UTC
                    {!isCurrentPeriod ? ' · history' : ''}
                    {switching ? ' · loading' : ''}
                  </p>
                  <div className="flex flex-wrap items-end gap-3">
                    <p
                      className={cn(
                        'font-sans text-[48px] font-bold leading-none tracking-[-0.03em] tabular-nums',
                        minutesTone === 'limit' ? 'text-danger' : 'text-text',
                      )}
                    >
                      {minutesUsed.toFixed(2)}
                      <span className="text-[28px] font-semibold text-text-muted">
                        {' '}
                        / {minutesMax.toLocaleString()}
                      </span>
                    </p>
                    <span className="mb-1 font-mono text-[13px] text-text-muted">min</span>
                  </div>
                  <p className="text-[15px] text-text-body">
                    {agentSec.toLocaleString(undefined, { maximumFractionDigits: 0 })} agent sec
                    {isCurrentPeriod
                      ? ` · ${minutesLeft.toFixed(2)} min left · ${minutesPct.toFixed(0)}% used`
                      : ` · ${minutesPct.toFixed(0)}% of plan that month`}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'rounded-pill px-3 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em]',
                      minutesTone === 'ok' && 'bg-surface-muted text-text',
                      minutesTone === 'high' && 'bg-[#FDF3E0] text-warning',
                      minutesTone === 'limit' && 'bg-[#FBEAEA] text-danger',
                    )}
                  >
                    {toneLabel(minutesTone)}
                  </span>
                  {isCurrentPeriod ? (
                    <Link
                      href="/sessions"
                      className={cn(
                        'rounded-pill border border-border bg-surface px-3 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] transition-colors duration-console hover:bg-surface-muted',
                        concurrentTone === 'limit' ? 'text-danger' : 'text-text',
                      )}
                    >
                      {concurrentNow} live
                      {concurrentMax > 0 ? ` / ${concurrentMax}` : ''}
                    </Link>
                  ) : null}
                </div>
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono-label text-text-muted">Billable minutes</span>
                  <span className="font-mono text-[12px] tabular-nums text-text">
                    {minutesUsed.toFixed(2)} / {minutesMax.toLocaleString()}
                  </span>
                </div>
                <Meter value={minutesUsed} max={minutesMax} tone={minutesTone} />
              </div>

              {isCurrentPeriod ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-mono-label text-text-muted">Concurrent calls</span>
                    <span className="font-mono text-[12px] tabular-nums text-text">
                      {concurrentNow} / {concurrentMax}
                    </span>
                  </div>
                  <Meter value={concurrentNow} max={concurrentMax} tone={concurrentTone} />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <section className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <h2 className="font-mono-label text-text-muted">Daily agent minutes</h2>
              <p className="text-[15px] text-text-body">
                Agent session time by UTC day for {monthLabel(usage.period_start)}.
              </p>
            </div>

            {!hasAgentTraffic && !hasAnyTotals ? (
              <Card>
                <CardContent className="flex flex-col gap-4 p-6 pt-6 sm:p-8">
                  <p className="text-[15px] text-text-body">
                    {isCurrentPeriod
                      ? 'No usage this month yet. Make a test call, then check back here and in Sessions.'
                      : 'No usage recorded for this month.'}
                  </p>
                  {isCurrentPeriod ? (
                    <div className="flex flex-wrap gap-2">
                      <Link
                        href="/sessions"
                        className="inline-flex rounded-pill bg-text px-5 py-3 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-white transition-opacity duration-console hover:opacity-90"
                      >
                        Sessions
                      </Link>
                      <Link
                        href="/docs/quickstart"
                        className="inline-flex rounded-pill border border-border bg-surface px-5 py-3 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text transition-colors duration-console hover:bg-surface-muted"
                      >
                        Quickstart
                      </Link>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-6 pt-6 sm:p-8">
                  <DailyMinutesChart data={dailyMinutes} showTodayMarker={isCurrentPeriod} />
                </CardContent>
              </Card>
            )}
          </section>

          <section className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <h2 className="font-mono-label text-text-muted">Provider breakdown</h2>
              <p className="text-[15px] text-text-body">
                Raw provider totals for {monthLabel(usage.period_start)}. Billable minutes use agent
                time only.
              </p>
            </div>

            <Card>
              <CardContent className="divide-y divide-border p-0">
                {BREAKDOWN_ORDER.map((kind) => {
                  const meta = KIND_META[kind];
                  const raw = usage.totals.find((t) => t.kind === kind)?.total_qty ?? 0;
                  return (
                    <div
                      key={kind}
                      className="flex items-baseline justify-between gap-4 px-6 py-4 sm:px-8"
                    >
                      <span className="font-mono-label text-text-muted">{meta.label}</span>
                      <span className="font-mono text-[13px] tabular-nums text-text">
                        {meta.toDisplay(raw)}{' '}
                        <span className="text-text-muted">{meta.unit}</span>
                      </span>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </section>
        </div>
      ) : null}
    </div>
  );
}
