import { toCsv } from '@/lib/csv';

export type UsageExportInput = {
  period_start: string;
  period_end: string;
  timezone?: string;
  billable_minutes?: number;
  billable_agent_sec?: number;
  quota: { minutes_this_month: number };
  totals: Array<{ kind: string; total_qty: number }>;
  daily: Array<{ day: string; kind: string; total_qty: number }>;
};

/** Canonical kind ids for machine-readable exports (not UI labels). */
const KIND_UNIT: Record<string, string> = {
  agent_sec: 'sec',
  stt_sec: 'sec',
  tts_sec: 'sec',
  llm_tokens: 'tokens',
};

/**
 * Build an invoice-safe CSV for one calendar month.
 *
 * Layout (one table, unambiguous):
 *   section,period_start,period_end,timezone,day,kind,quantity,unit
 *   - summary rows: billable_minutes + billable_agent_sec
 *   - total rows: per-kind month totals (same as API totals)
 *   - daily rows: per day × kind (stable kind ids, ascending day)
 *
 * Summing `daily` rows where kind=agent_sec MUST equal billable_agent_sec.
 */
export function buildUsageExportCsv(usage: UsageExportInput): string {
  const timezone = usage.timezone ?? 'UTC';
  const billableSec = Number(usage.billable_agent_sec ?? 0);
  const billableMin = Number(
    usage.billable_minutes ?? usage.quota.minutes_this_month ?? 0,
  );

  const dailyAgentSec = usage.daily
    .filter((r) => r.kind === 'agent_sec')
    .reduce((sum, r) => sum + Number(r.total_qty), 0);

  if (Math.abs(dailyAgentSec - billableSec) > 0.0001) {
    throw new Error(
      `CSV export blocked: daily agent_sec (${dailyAgentSec}) does not match billable_agent_sec (${billableSec})`,
    );
  }

  const expectedMin = billableSec / 60;
  if (Math.abs(billableMin - expectedMin) > 0.00015) {
    throw new Error(
      `CSV export blocked: billable_minutes (${billableMin}) does not match agent_sec/60 (${expectedMin})`,
    );
  }

  const totalsAgentSec = usage.totals
    .filter((r) => r.kind === 'agent_sec')
    .reduce((sum, r) => sum + Number(r.total_qty), 0);
  if (Math.abs(totalsAgentSec - billableSec) > 0.0001) {
    throw new Error(
      `CSV export blocked: totals agent_sec (${totalsAgentSec}) does not match billable_agent_sec (${billableSec})`,
    );
  }

  const base = [usage.period_start, usage.period_end, timezone] as const;

  const summaryRows: string[][] = [
    ['summary', ...base, '', 'billable_minutes', formatQty(billableMin), 'min'],
    ['summary', ...base, '', 'billable_agent_sec', formatQty(billableSec), 'sec'],
  ];

  const totalRows = [...usage.totals]
    .sort((a, b) => a.kind.localeCompare(b.kind))
    .map((row) => [
      'total',
      ...base,
      '',
      row.kind,
      formatQty(row.total_qty),
      KIND_UNIT[row.kind] ?? 'qty',
    ]);

  const dailyRows = [...usage.daily]
    .sort((a, b) => a.day.localeCompare(b.day) || a.kind.localeCompare(b.kind))
    .map((row) => [
      'daily',
      ...base,
      row.day,
      row.kind,
      formatQty(row.total_qty),
      KIND_UNIT[row.kind] ?? 'qty',
    ]);

  return toCsv(
    ['section', 'period_start', 'period_end', 'timezone', 'day', 'kind', 'quantity', 'unit'],
    [...summaryRows, ...totalRows, ...dailyRows],
  );
}

export function usageExportFilename(usage: UsageExportInput): string {
  return `usage-${usage.period_start}_to_${usage.period_end}.csv`;
}

function formatQty(n: number): string {
  // Avoid scientific notation; keep enough precision for seconds / 4dp minutes.
  if (Number.isInteger(n)) return String(n);
  return String(Number(n.toFixed(6)));
}
