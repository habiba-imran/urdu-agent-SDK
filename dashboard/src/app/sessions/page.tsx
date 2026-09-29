'use client';

import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import { Copy, Check, Download, ChevronLeft, ChevronRight } from 'lucide-react';

import { type PortalSession, getSession } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { isPortalAuthFailure } from '@/lib/portalAuth';
import { toCsv, downloadCsv } from '@/lib/csv';
import { cn } from '@/lib/utils';
import { stripTranscriptMarkup } from '@/lib/transcriptText';
import { PageHeader } from '@/components/ui/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Drawer } from '@/components/ui/drawer';
import { DataTableSkeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  RowOpenButton,
} from '@/components/ui/table';

function formatDuration(durationSec: number | null | undefined) {
  if (durationSec === null || durationSec === undefined || Number.isNaN(durationSec)) {
    return 'Unknown';
  }
  const total = Math.max(0, Math.round(durationSec));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes} min ${seconds} sec`;
}

function isNonBilledReason(reason: string | null | undefined): boolean {
  if (!reason) return false;
  const r = reason.toLowerCase();
  return (
    r === 'reconciled_stale' ||
    r === 'stale_reconciled' ||
    r === 'stale_no_participant' ||
    r === 'stale_orphan_dispatch' ||
    r.startsWith('stale_')
  );
}

/** Prefer billable agent_sec (payment truth). Never show reconciled wall-clock as call length. */
function formatSessionDuration(session: PortalSession): string {
  const billed = Number(session.billable_agent_sec ?? 0);
  if (billed > 0) {
    return formatDuration(billed);
  }
  if (session.live) {
    return 'In progress';
  }
  if (session.stale || isNonBilledReason(session.end_reason)) {
    return 'Not billed';
  }
  if (session.duration_sec != null) {
    return formatDuration(session.duration_sec);
  }
  return 'Unknown';
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return 'Unknown';
  }

  return new Date(timestamp).toLocaleString();
}

/** Middle-truncate long ids for table/drawer display; full value stays in title / clipboard. */
function shortId(value: string, head = 8, tail = 4): string {
  if (!value) return '';
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

// Known raw values written by control_plane/app.py, worker/main.py, and
// scripts/reconcile_sessions.py — mapped to plain, human-readable labels rather than
// showing the backend's internal snake_case string verbatim. Anything not explicitly
// listed still gets normalized (underscores/hyphens -> spaces, title case) as a fallback.
const END_REASON_LABELS: Record<string, string> = {
  normal: 'Normal',
  dispatch_failed: 'Dispatch Failed',
  reconciled_stale: 'Reconciled (Stale)',
  stale_reconciled: 'Reconciled (Stale)',
  // Written by worker/main.py's session-close handler, from LiveKit's CloseReason.
  participant_disconnected: 'Caller Hung Up',
  agent_ended: 'Ended by Agent',
  task_completed: 'Ended by Agent',
  job_shutdown: 'Worker Shut Down',
  'parent process shutdown': 'Worker Shut Down',
  error: 'Ended on Error',
};

function humanizeEndReason(reason: string | null): string {
  if (!reason) {
    return 'Unknown';
  }
  const known = END_REASON_LABELS[reason.toLowerCase()];
  if (known) {
    return known;
  }
  return reason
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

function StatusBadge({ session }: { session: PortalSession }) {
  if (session.live) {
    return <Badge className="bg-emerald-600 text-white">Live</Badge>;
  }
  if (session.stale) {
    return (
      <Badge variant="outline" className="border-amber-500 text-amber-700">
        Stale
      </Badge>
    );
  }
  return <Badge variant="outline">Ended</Badge>;
}

function IdChip({ value, className }: { value: string; className?: string }) {
  return (
    <span
      title={value}
      className={cn(
        'inline-flex max-w-full items-center rounded-pill border border-border bg-surface-muted px-2.5 py-1 font-mono text-[11px] tabular-nums tracking-tight text-text-body',
        className,
      )}
    >
      <span className="truncate">{shortId(value)}</span>
    </span>
  );
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-input border border-border bg-surface px-3.5 py-3">
      <div className="font-mono-label text-text-muted">{label}</div>
      <div className="mt-1.5 text-[15px] font-semibold leading-snug tracking-[-0.01em] text-text">
        {value}
      </div>
    </div>
  );
}

function CopyableId({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-mono-label text-text-muted">{label}</span>
      <div className="flex items-center gap-2 rounded-input border border-border bg-surface-muted px-3 py-2.5">
        <span title={value} className="min-w-0 flex-1 font-mono text-[12px] tabular-nums text-text">
          <span className="sm:hidden">{shortId(value, 10, 6)}</span>
          <span className="hidden break-all sm:inline">{value}</span>
        </span>
        <button
          type="button"
          onClick={onCopy}
          aria-label={copied ? `Copied ${label}` : `Copy ${label}`}
          title={copied ? 'Copied' : 'Copy'}
          className={cn(
            'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-pill border border-border bg-surface text-text-muted transition-colors duration-console',
            'hover:bg-surface-muted hover:text-text',
            copied && 'border-transparent bg-text text-white hover:bg-text hover:text-white',
          )}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h3 className="font-mono-label text-text-muted">{children}</h3>;
}

const PAGE_SIZE = 15;

export default function SessionsPage() {
  const { data: sessions, isLoading: loading, error } = useSWR(
    swrKeys.sessions,
    swrFetchers.sessions,
  );
  const [activeSession, setActiveSession] = useState<PortalSession | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil((sessions?.length ?? 0) / PAGE_SIZE));
  // Clamp rather than reset on every revalidation -- SWR hands back a new array reference on
  // each background refetch even when the content is unchanged, so resetting unconditionally
  // would kick the user back to page 1 while they're reading page 3.
  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);
  const paginatedSessions = (sessions ?? []).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const openSession = async (session: PortalSession) => {
    setActiveSession(session);
    setDetailLoading(true);
    try {
      const full = await getSession(session.id);
      setActiveSession(full);
    } catch {
      // Keep list row data if detail fails.
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCopy = (field: string, value: string) => {
    navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => {
      setCopiedField((current) => (current === field ? null : current));
    }, 1500);
  };

  const handleExportSessions = () => {
    const csv = toCsv(
      [
        'Session ID',
        'Agent',
        'Room',
        'Status',
        'Billable (sec)',
        'Billable (min)',
        'Recorded duration_sec',
        'End Reason',
        'Started At',
        'Ended At',
      ],
      (sessions ?? []).map((session) => {
        const billed = Number(session.billable_agent_sec ?? 0);
        return [
          session.id,
          session.agent_name,
          session.room_name,
          session.live ? 'Live' : session.stale ? 'Stale' : 'Ended',
          String(billed),
          billed > 0 ? (billed / 60).toFixed(4) : '0',
          String(session.duration_sec ?? ''),
          session.stale ? 'Never closed' : session.end_reason ?? '',
          session.started_at ?? '',
          session.ended_at ?? '',
        ];
      }),
    );
    downloadCsv('sessions.csv', csv);
  };

  const drawerTitle = activeSession?.agent_name ?? 'Session';
  const drawerDescription = activeSession
    ? `${activeSession.live ? 'Live' : activeSession.stale ? 'Stale' : 'Ended'} · ${formatTimestamp(activeSession.started_at)}`
    : undefined;

  return (
    <div>
      <PageHeader
        title="Sessions"
        description="Call history. Duration is billable agent time — the same minutes counted on Usage."
        actions={
          (sessions ?? []).length > 0 ? (
            <Button variant="secondary" onClick={handleExportSessions}>
              <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Export CSV
            </Button>
          ) : undefined
        }
      />

      {error && !isPortalAuthFailure(error) ? (
        <div className="mb-6 rounded-input border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load sessions'}
        </div>
      ) : null}

      {loading ? (
        <div className="rounded-card border border-border bg-surface p-6 shadow-card">
          <DataTableSkeleton rows={5} />
        </div>
      ) : (sessions ?? []).length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-6 shadow-card">
          <EmptyState title="No recent sessions found" />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <Table className="overflow-x-hidden" tableClassName="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[22%]">Session</TableHead>
                <TableHead className="hidden w-[22%] md:table-cell">Room</TableHead>
                <TableHead className="w-[18%]">Agent</TableHead>
                <TableHead className="w-[16%]">Duration</TableHead>
                <TableHead className="w-[12%]">Status</TableHead>
                <TableHead className="hidden w-[18%] lg:table-cell">Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedSessions.map((session) => (
                <TableRow key={session.id} onClick={() => void openSession(session)}>
                  <TableCell>
                    <RowOpenButton
                      onClick={() => void openSession(session)}
                      ariaLabel={`Open session ${session.id}`}
                      className="inline-flex max-w-full"
                    >
                      <IdChip value={session.id} />
                    </RowOpenButton>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <IdChip value={session.room_name} />
                  </TableCell>
                  <TableCell>
                    <span className="block truncate font-medium text-text">{session.agent_name}</span>
                  </TableCell>
                  <TableCell>
                    <span className="tabular-nums text-text-body">
                      {formatSessionDuration(session)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge session={session} />
                  </TableCell>
                  <TableCell className="hidden text-[13px] text-text-muted lg:table-cell">
                    {formatTimestamp(session.started_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {(sessions ?? []).length > PAGE_SIZE ? (
            <div className="flex items-center justify-between px-1 pt-1">
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
                {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, (sessions ?? []).length)} of{' '}
                {(sessions ?? []).length}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                </Button>
                <span className="font-mono text-[11px] tabular-nums text-text-muted">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}

      <Drawer
        open={activeSession !== null}
        onOpenChange={(open) => {
          if (!open) setActiveSession(null);
        }}
        title={drawerTitle}
        description={drawerDescription}
        className="max-w-[480px] sm:max-w-[520px]"
      >
        {activeSession ? (
          <div className="flex flex-col gap-7">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge session={activeSession} />
              {!activeSession.live && !activeSession.stale ? (
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
                  {humanizeEndReason(activeSession.end_reason)}
                </span>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <StatBlock label="Billable duration" value={formatSessionDuration(activeSession)} />
              <StatBlock
                label="End reason"
                value={
                  activeSession.stale
                    ? 'Never closed'
                    : humanizeEndReason(activeSession.end_reason)
                }
              />
              <StatBlock label="Started" value={formatTimestamp(activeSession.started_at)} />
              <StatBlock label="Ended" value={formatTimestamp(activeSession.ended_at)} />
            </div>

            {Number(activeSession.billable_agent_sec ?? 0) > 0 ? (
              <p className="rounded-input border border-border bg-surface-muted px-3.5 py-2.5 text-[13px] text-text-body">
                <span className="font-medium text-text">
                  {Number(activeSession.billable_agent_sec).toFixed(0)} sec
                </span>
                <span className="text-text-muted">
                  {' '}
                  ({(Number(activeSession.billable_agent_sec) / 60).toFixed(2)} min) billable
                </span>
                {activeSession.duration_sec != null &&
                Math.abs(Number(activeSession.billable_agent_sec) - activeSession.duration_sec) >
                  0.01
                  ? ` · recorded ${activeSession.duration_sec}s`
                  : null}
              </p>
            ) : null}

            {activeSession.stale ? (
              <p className="rounded-input border border-amber-500/25 bg-[#FDF3E0] px-3.5 py-2.5 text-[13px] text-amber-900">
                This session was never closed by the voice worker — it most likely exited
                ungracefully. It is not an active call and is not consuming a concurrency slot
                once reconciliation runs.
              </p>
            ) : null}

            <div className="flex flex-col gap-2.5">
              <SectionLabel>Call summary</SectionLabel>
              {detailLoading ? (
                <p className="rounded-input border border-border bg-surface-muted px-3.5 py-3 text-[13px] text-text-muted">
                  Loading transcript…
                </p>
              ) : activeSession.summary ? (
                <p className="rounded-input border border-border bg-surface px-3.5 py-3 text-[15px] leading-relaxed text-text">
                  {activeSession.summary}
                </p>
              ) : (
                <p className="rounded-input border border-border bg-surface-muted px-3.5 py-3 text-[13px] text-text-muted">
                  No summary available for this call.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-3">
              <SectionLabel>IDs</SectionLabel>
              <CopyableId
                label="Session ID"
                value={activeSession.id}
                copied={copiedField === 'id'}
                onCopy={() => handleCopy('id', activeSession.id)}
              />
              <CopyableId
                label="Agent ID"
                value={activeSession.agent_id}
                copied={copiedField === 'agent_id'}
                onCopy={() => handleCopy('agent_id', activeSession.agent_id)}
              />
              <CopyableId
                label="Room"
                value={activeSession.room_name}
                copied={copiedField === 'room_name'}
                onCopy={() => handleCopy('room_name', activeSession.room_name)}
              />
            </div>

            <div className="flex flex-col gap-2.5">
              <SectionLabel>Transcript</SectionLabel>
              {activeSession.transcript && activeSession.transcript.length > 0 ? (
                <div className="flex max-h-80 flex-col gap-2 overflow-y-auto rounded-input border border-border bg-surface p-3">
                  {activeSession.transcript.map((turn, i) => (
                    <div
                      key={i}
                      className={cn(
                        'max-w-[88%] rounded-input px-3 py-2 text-[14px] leading-relaxed',
                        turn.role === 'assistant'
                          ? 'self-start bg-surface-muted text-text'
                          : 'self-end bg-text text-white',
                      )}
                    >
                      {stripTranscriptMarkup(turn.text)}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-input border border-border bg-surface-muted px-3.5 py-3 text-[13px] text-text-muted">
                  No transcript available for this call.
                </p>
              )}
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
