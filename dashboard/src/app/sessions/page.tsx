'use client';

import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import { Copy, Check, Download, ChevronLeft, ChevronRight } from 'lucide-react';

import { type PortalSession } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { toCsv, downloadCsv } from '@/lib/csv';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
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

function formatDuration(durationSec: number | null) {
  if (durationSec === null || durationSec === undefined) {
    return 'Unknown';
  }

  const minutes = Math.floor(durationSec / 60);
  const seconds = durationSec % 60;
  return `${minutes} min ${seconds} sec`;
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return 'Unknown';
  }

  return new Date(timestamp).toLocaleString();
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

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted px-3 py-2">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-foreground">{value}</div>
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
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex items-center justify-between gap-2 rounded-md border border-slate-300 bg-muted px-3 py-2">
        <span className="truncate font-mono text-xs text-foreground">{value}</span>
        <button
          type="button"
          onClick={onCopy}
          aria-label={copied ? `Copied ${label}` : `Copy ${label}`}
          title={copied ? 'Copied' : 'Copy'}
          className="inline-flex shrink-0 items-center justify-center rounded-md p-1 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
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

const PAGE_SIZE = 15;

export default function SessionsPage() {
  const { data: sessions, isLoading: loading, error } = useSWR(
    swrKeys.sessions,
    swrFetchers.sessions,
  );
  const [activeSession, setActiveSession] = useState<PortalSession | null>(null);
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

  const handleCopy = (field: string, value: string) => {
    navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => {
      setCopiedField((current) => (current === field ? null : current));
    }, 1500);
  };

  const handleExportSessions = () => {
    const csv = toCsv(
      ['Session ID', 'Agent', 'Room', 'Status', 'Duration (sec)', 'End Reason', 'Started At', 'Ended At'],
      (sessions ?? []).map((session) => [
        session.id,
        session.agent_name,
        session.room_name,
        session.live ? 'Live' : session.stale ? 'Stale' : 'Ended',
        String(session.duration_sec ?? ''),
        session.stale ? 'Never closed' : humanizeEndReason(session.end_reason),
        session.started_at ?? '',
        session.ended_at ?? '',
      ]),
    );
    downloadCsv('sessions.csv', csv);
  };

  return (
    <div>
      <PageHeader
        title="Call Sessions"
        description="Historical record of completed WebRTC calls. Open a row to inspect the session details currently exposed by the tenant API."
        actions={
          (sessions ?? []).length > 0 ? (
            <Button variant="secondary" onClick={handleExportSessions}>
              <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Export CSV
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load sessions'}
        </div>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          {loading ? (
            <DataTableSkeleton rows={5} />
          ) : (sessions ?? []).length === 0 ? (
            <EmptyState title="No recent sessions found" />
          ) : (
            <Table className="overflow-x-hidden" tableClassName="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead>Session ID</TableHead>
                  <TableHead className="hidden md:table-cell">Room Name</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden lg:table-cell">Started At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedSessions.map((session) => (
                  <TableRow key={session.id} onClick={() => setActiveSession(session)}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      <RowOpenButton
                        onClick={() => setActiveSession(session)}
                        ariaLabel={`Open session ${session.id}`}
                        className="block w-full truncate font-mono text-xs"
                      >
                        {session.id}
                      </RowOpenButton>
                    </TableCell>
                    <TableCell className="hidden truncate font-mono text-xs md:table-cell">
                      {session.room_name}
                    </TableCell>
                    <TableCell className="truncate">{session.agent_name}</TableCell>
                    <TableCell className="truncate">{formatDuration(session.duration_sec)}</TableCell>
                    <TableCell>
                      {session.live ? (
                        <Badge className="bg-emerald-600 text-white">Live</Badge>
                      ) : session.stale ? (
                        <Badge variant="outline" className="border-amber-500 text-amber-700">
                          Stale
                        </Badge>
                      ) : (
                        <Badge variant="outline">Ended</Badge>
                      )}
                    </TableCell>
                    <TableCell className="hidden truncate text-muted-foreground lg:table-cell">
                      {formatTimestamp(session.started_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {!loading && (sessions ?? []).length > PAGE_SIZE ? (
            <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
              <span className="text-xs text-muted-foreground">
                Showing {(page - 1) * PAGE_SIZE + 1}–
                {Math.min(page * PAGE_SIZE, (sessions ?? []).length)} of {(sessions ?? []).length}
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
                <span className="text-xs text-muted-foreground">
                  Page {page} of {totalPages}
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
        </CardContent>
      </Card>

      <Drawer
        open={activeSession !== null}
        onOpenChange={(open) => {
          if (!open) setActiveSession(null);
        }}
        title="Session Details"
        description={activeSession ? formatTimestamp(activeSession.started_at) : undefined}
      >
        {activeSession ? (
          <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-lg font-semibold text-foreground">
                  {activeSession.agent_name}
                </div>
                <div className="text-sm text-muted-foreground">Voice agent call session</div>
              </div>
              {activeSession.live ? (
                <Badge className="shrink-0 bg-emerald-600 text-white">Live</Badge>
              ) : activeSession.stale ? (
                <Badge variant="outline" className="shrink-0 border-amber-500 text-amber-700">
                  Stale
                </Badge>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <StatBlock label="Duration" value={formatDuration(activeSession.duration_sec)} />
              <StatBlock
                label="End Reason"
                value={
                  activeSession.stale
                    ? 'Never closed'
                    : humanizeEndReason(activeSession.end_reason)
                }
              />
              <StatBlock label="Started" value={formatTimestamp(activeSession.started_at)} />
              <StatBlock label="Ended" value={formatTimestamp(activeSession.ended_at)} />
            </div>

            {activeSession.stale ? (
              <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800">
                This session was never closed by the voice worker — it most likely exited
                ungracefully. It is not an active call and is not consuming a concurrency slot
                once reconciliation runs.
              </p>
            ) : null}

            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Call Summary
              </h3>
              {activeSession.summary ? (
                <p className="rounded-md bg-muted px-3 py-2 text-sm text-foreground">
                  {activeSession.summary}
                </p>
              ) : (
                <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
                  No summary available for this call.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Technical Details
              </h3>
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

            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Transcript
              </h3>
              {activeSession.transcript && activeSession.transcript.length > 0 ? (
                <div className="flex max-h-80 flex-col gap-2 overflow-y-auto rounded-md border border-border p-3">
                  {activeSession.transcript.map((turn, i) => (
                    <div
                      key={i}
                      className={cn(
                        'max-w-[85%] rounded-md px-3 py-1.5 text-sm',
                        turn.role === 'assistant'
                          ? 'self-start bg-muted text-foreground'
                          : 'self-end bg-primary text-primary-foreground',
                      )}
                    >
                      {turn.text}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
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
