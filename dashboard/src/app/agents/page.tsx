'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { Check, Copy, Download } from 'lucide-react';

import { type PortalAgent } from '@/lib/portalApi';
import { type ManagedPhoneNumber } from '@/lib/telephonyApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { isPortalAuthFailure } from '@/lib/portalAuth';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Drawer } from '@/components/ui/drawer';
import { DataTableSkeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function formatProviderLabel(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => capitalize(part))
    .join(' ');
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h3 className="font-mono-label text-text-muted">{children}</h3>;
}

function ProviderReadonlyRow({
  label,
  provider,
  detail,
}: {
  label: string;
  provider?: string | null;
  detail?: string | null;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-input border border-border bg-surface-muted px-3.5 py-3">
      <span className="text-[12px] font-medium text-text-muted">{label}</span>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{provider ? formatProviderLabel(provider) : '—'}</Badge>
        {detail ? (
          <span className="truncate font-mono text-[12px] text-text-body" title={detail}>
            {detail}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function primaryNumberLabel(agent: PortalAgent, assigned: ManagedPhoneNumber[]): string {
  if (assigned.length > 0) return assigned[0]!.e164_number;
  if (agent.phone_number) return agent.phone_number;
  return '—';
}

export default function AgentsPage() {
  const {
    data: agents,
    isLoading: agentsLoading,
    error: agentsSWRError,
  } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: managedNumbers } = useSWR(swrKeys.telephonyNumbers, swrFetchers.telephonyNumbers);
  const { data: capabilities } = useSWR(swrKeys.providerCapabilities, swrFetchers.providerCapabilities, {
    dedupingInterval: 60_000,
    revalidateIfStale: false,
    keepPreviousData: true,
  });

  const [activeAgent, setActiveAgent] = useState<PortalAgent | null>(null);
  const [drawerIdCopied, setDrawerIdCopied] = useState(false);
  const [copiedAgentId, setCopiedAgentId] = useState<string | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drawerCopyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
      if (drawerCopyTimeoutRef.current) clearTimeout(drawerCopyTimeoutRef.current);
    };
  }, []);

  const numbersByAgent = useMemo(() => {
    const map = new Map<string, ManagedPhoneNumber[]>();
    for (const num of managedNumbers ?? []) {
      if (!num.assigned_agent_id) continue;
      const list = map.get(num.assigned_agent_id) ?? [];
      list.push(num);
      map.set(num.assigned_agent_id, list);
    }
    return map;
  }, [managedNumbers]);

  const activeLanguage = activeAgent?.agent_language || 'ur';
  const activeLangLabel =
    capabilities?.languages[activeLanguage]?.label ?? activeLanguage.toUpperCase();
  const activeVoiceId = activeAgent?.tts_voice_id || activeAgent?.voice_id || '—';
  const activeAssigned = activeAgent ? numbersByAgent.get(activeAgent.id) ?? [] : [];

  const handleCopyAgentId = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(agentId);
    setCopiedAgentId(agentId);
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => {
      setCopiedAgentId((current) => (current === agentId ? null : current));
    }, 1500);
  };

  const handleCopyDrawerId = () => {
    if (!activeAgent) return;
    navigator.clipboard.writeText(activeAgent.id);
    setDrawerIdCopied(true);
    if (drawerCopyTimeoutRef.current) clearTimeout(drawerCopyTimeoutRef.current);
    drawerCopyTimeoutRef.current = setTimeout(() => setDrawerIdCopied(false), 1500);
  };

  const openAgentDrawer = (agent: PortalAgent) => {
    setActiveAgent(agent);
    setDrawerIdCopied(false);
  };

  const closeAgentDrawer = () => {
    setActiveAgent(null);
    setDrawerIdCopied(false);
  };

  const handleExportAgents = () => {
    const csv = toCsv(
      ['Agent ID', 'Agent Name', 'Assigned Number', 'Minutes Used', 'Created At'],
      (agents ?? []).map((agent) => {
        const assigned = numbersByAgent.get(agent.id) ?? [];
        return [
          agent.id,
          agent.name,
          primaryNumberLabel(agent, assigned),
          ((agent.total_agent_sec ?? 0) / 60).toFixed(1),
          agent.created_at ?? '',
        ];
      }),
    );
    downloadCsv('agents.csv', csv);
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Agents"
        description="Read-only view of agents and assigned phone numbers. Create and update configuration from your host codebase via the agents and telephony SDKs."
        actions={
          <Button variant="secondary" onClick={handleExportAgents}>
            <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
            Export CSV
          </Button>
        }
      />

      {agentsSWRError && !isPortalAuthFailure(agentsSWRError) ? (
        <div className="mb-6 rounded-input border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {agentsSWRError instanceof Error ? agentsSWRError.message : 'Failed to load agents'}
        </div>
      ) : null}

      <Card className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
        <div
          role="status"
          aria-live="polite"
          className={cn(
            'pointer-events-none absolute right-5 top-5 z-20 flex items-center gap-1.5',
            'rounded-pill border border-border bg-text px-3 py-1.5 text-white shadow-float',
            'font-mono text-[11px] font-medium uppercase tracking-[0.12em]',
            'transition-all duration-200 ease-out',
            copiedAgentId ? 'translate-y-0 opacity-100' : '-translate-y-1 opacity-0',
          )}
        >
          <Check className="h-3.5 w-3.5" aria-hidden="true" />
          Agent ID copied
        </div>
        <CardContent className="flex min-h-0 flex-1 flex-col pt-6">
          {agentsLoading ? (
            <DataTableSkeleton rows={4} />
          ) : (agents ?? []).length === 0 ? (
            <EmptyState
              title="No agents found yet"
              description="Create agents from your host codebase with @awaazlabs-uva/agents."
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col text-sm">
              <div className="grid shrink-0 grid-cols-[minmax(0,2.5fr)_minmax(0,0.7fr)_minmax(0,1.2fr)_minmax(0,1fr)_3.25rem] border-b border-border">
                <div className="h-10 px-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
                  Agent Name
                </div>
                <div className="h-10 px-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
                  Language
                </div>
                <div className="h-10 px-3 text-left font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
                  Assigned Number
                </div>
                <div className="h-10 px-3 text-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
                  Minutes Used
                </div>
                <div className="h-10 px-3">
                  <span className="sr-only">Copy agent ID</span>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-border">
                {(agents ?? []).map((agent) => {
                  const isCopied = copiedAgentId === agent.id;
                  const assigned = numbersByAgent.get(agent.id) ?? [];
                  const numberLabel = primaryNumberLabel(agent, assigned);
                  const extraCount = Math.max(0, assigned.length - 1);
                  return (
                    <div
                      key={agent.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`Open details for ${agent.name}`}
                      onClick={() => openAgentDrawer(agent)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          openAgentDrawer(agent);
                        }
                      }}
                      className="group grid cursor-pointer grid-cols-[minmax(0,2.5fr)_minmax(0,0.7fr)_minmax(0,1.2fr)_minmax(0,1fr)_3.25rem] items-center transition-colors duration-console hover:bg-surface-muted focus-visible:bg-surface-muted focus-visible:outline-none"
                    >
                      <div className="truncate p-3 font-medium text-text">{agent.name}</div>
                      <div className="truncate p-3">
                        <Badge variant="outline">
                          {(agent.agent_language ?? 'ur').toUpperCase()}
                        </Badge>
                      </div>
                      <div className="truncate p-3">
                        {numberLabel === '—' ? (
                          <span className="text-text-muted">—</span>
                        ) : (
                          <span
                            className="font-mono text-[12px] tabular-nums text-text-body"
                            title={
                              extraCount > 0
                                ? assigned.map((n) => n.e164_number).join(', ')
                                : numberLabel
                            }
                          >
                            {numberLabel}
                            {extraCount > 0 ? (
                              <span className="ml-1 text-text-muted">+{extraCount}</span>
                            ) : null}
                          </span>
                        )}
                      </div>
                      <div className="truncate p-3 text-center tabular-nums text-text-body">
                        {((agent.total_agent_sec ?? 0) / 60).toFixed(1)} min
                      </div>
                      <div
                        className="flex items-center justify-center p-3"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          onClick={(e) => handleCopyAgentId(agent.id, e)}
                          aria-label={
                            isCopied
                              ? `Copied agent ID for ${agent.name}`
                              : `Copy agent ID for ${agent.name}`
                          }
                          title="Copy agent ID"
                          className={cn(
                            'relative inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-transparent text-muted-foreground transition-all duration-200 ease-out',
                            'opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-muted',
                            isCopied &&
                              'opacity-100 border-transparent bg-text text-white hover:bg-text hover:text-white',
                          )}
                        >
                          <Copy
                            className={cn(
                              'h-3.5 w-3.5 transition-all duration-200 ease-out',
                              isCopied ? 'scale-50 opacity-0' : 'scale-100 opacity-100',
                            )}
                            aria-hidden="true"
                          />
                          <Check
                            className={cn(
                              'pointer-events-none absolute h-3.5 w-3.5 transition-all duration-200 ease-out',
                              isCopied ? 'scale-100 opacity-100' : 'scale-50 opacity-0',
                            )}
                            aria-hidden="true"
                          />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Drawer
        open={activeAgent !== null}
        onOpenChange={(open) => {
          if (!open) closeAgentDrawer();
        }}
        title={activeAgent?.name || 'Agent'}
        description={`${activeLangLabel} · read-only`}
        className="max-w-[520px]"
        footer={
          <div className="flex justify-end">
            <Button variant="secondary" onClick={closeAgentDrawer}>
              Close
            </Button>
          </div>
        }
      >
        {activeAgent ? (
          <div className="flex flex-col gap-7">
            <p className="rounded-input border border-border bg-surface-muted px-3.5 py-3 text-[13px] leading-relaxed text-text-body">
              This console is read-only. Create agents, change prompts, providers, voices,
              recording, Telnyx connection, and number assignment from your host codebase with{' '}
              <code className="font-mono text-[12px]">@awaazlabs-uva/agents</code> and{' '}
              <code className="font-mono text-[12px]">@awaazlabs-uva/telephony</code>.
            </p>

            <div className="flex flex-col gap-1.5">
              <SectionLabel>Agent name</SectionLabel>
              <div className="rounded-input border border-border bg-surface-muted px-3 py-2.5 text-[15px] text-text">
                {activeAgent.name}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <SectionLabel>Agent ID</SectionLabel>
              <div className="flex items-center gap-2 rounded-input border border-border bg-surface-muted px-3 py-2.5">
                <span
                  title={activeAgent.id}
                  className="min-w-0 flex-1 truncate font-mono text-[12px] tabular-nums text-text"
                >
                  {activeAgent.id}
                </span>
                <button
                  type="button"
                  onClick={handleCopyDrawerId}
                  aria-label={drawerIdCopied ? 'Copied agent ID' : 'Copy agent ID'}
                  title={drawerIdCopied ? 'Copied' : 'Copy agent ID'}
                  className={cn(
                    'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-pill border border-border bg-surface text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text',
                    drawerIdCopied &&
                      'border-transparent bg-text text-white hover:bg-text hover:text-white',
                  )}
                >
                  {drawerIdCopied ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <SectionLabel>Language</SectionLabel>
              <div className="flex items-center gap-2 rounded-input border border-border bg-surface-muted px-3 py-2.5">
                <Badge variant="outline">{activeLanguage.toUpperCase()}</Badge>
                <span className="text-[13px] text-text-muted">{activeLangLabel}</span>
              </div>
            </div>

            <div className="flex flex-col gap-2.5">
              <SectionLabel>Assigned phone numbers</SectionLabel>
              {activeAssigned.length > 0 || activeAgent.phone_number ? (
                <ul className="flex flex-col gap-2">
                  {activeAssigned.length > 0
                    ? activeAssigned.map((num) => (
                        <li
                          key={num.id}
                          className="flex flex-wrap items-center gap-2 rounded-input border border-border bg-surface-muted px-3.5 py-3"
                        >
                          <span className="font-mono text-[13px] tabular-nums text-text">
                            {num.e164_number}
                          </span>
                          {num.country ? (
                            <Badge variant="outline">{num.country}</Badge>
                          ) : null}
                          {num.status ? (
                            <span className="text-[12px] text-text-muted">{num.status}</span>
                          ) : null}
                        </li>
                      ))
                    : (
                        <li className="rounded-input border border-border bg-surface-muted px-3.5 py-3 font-mono text-[13px] tabular-nums text-text">
                          {activeAgent.phone_number}
                        </li>
                      )}
                </ul>
              ) : (
                <p className="rounded-input border border-dashed border-border px-3.5 py-3 text-[13px] text-text-muted">
                  No number assigned. Wire routing with{' '}
                  <code className="font-mono text-[12px]">@awaazlabs-uva/telephony</code> in your
                  backend.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2.5">
              <SectionLabel>Providers</SectionLabel>
              <div className="grid gap-2">
                <ProviderReadonlyRow
                  label="Speech-to-text"
                  provider={activeAgent.stt_provider}
                  detail={activeAgent.stt_model}
                />
                <ProviderReadonlyRow
                  label="Language model"
                  provider={activeAgent.llm_provider}
                  detail={activeAgent.llm_model}
                />
                <ProviderReadonlyRow
                  label="Text-to-speech"
                  provider={activeAgent.tts_provider}
                  detail={activeVoiceId}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <SectionLabel>System prompt</SectionLabel>
              <div
                dir="auto"
                className="min-h-[120px] whitespace-pre-wrap rounded-input border border-border bg-surface-muted px-3 py-2.5 font-mono text-[13px] leading-relaxed text-text"
              >
                {activeAgent.prompt || '—'}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <SectionLabel>Recording</SectionLabel>
              <div className="flex flex-col gap-2 rounded-input border border-border bg-surface-muted px-3.5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-medium text-text">Call recording</span>
                  {activeAgent.recording_enabled ? (
                    <Badge variant="success">Enabled</Badge>
                  ) : (
                    <Badge variant="outline" dot="muted">
                      Disabled
                    </Badge>
                  )}
                </div>
                <p className="text-[13px] text-text-muted">
                  When enabled, callers hear a short disclosure and audio is stored with
                  retention limits. Change this from your host codebase.
                </p>
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
