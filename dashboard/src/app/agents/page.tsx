'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Check, Copy, Download } from 'lucide-react';

import { createAgent } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
import { DataTableSkeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { RowOpenButton } from '@/components/ui/table';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export default function AgentsPage() {
  const router = useRouter();
  const {
    data: agents,
    isLoading: agentsLoading,
    error: agentsSWRError,
    mutate: mutateAgents,
  } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: voices } = useSWR(swrKeys.voices, swrFetchers.voices);

  const [agentName, setAgentName] = useState('New Portal Agent');
  const [systemPrompt, setSystemPrompt] = useState(
    'You are a polite Urdu customer support voice assistant.',
  );
  const [selectedVoice, setSelectedVoice] = useState('v_meklc281');
  const [llmModel, setLlmModel] = useState('gemini-2.5-flash');
  const [showModal, setShowModal] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copiedAgentId, setCopiedAgentId] = useState<string | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const handleCopyAgentId = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(agentId);
    setCopiedAgentId(agentId);
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => {
      setCopiedAgentId((current) => (current === agentId ? null : current));
    }, 1500);
  };

  const openCreateModal = () => {
    setAgentName('New Portal Agent');
    setSystemPrompt('You are a polite Urdu customer support voice assistant.');
    setSelectedVoice('v_meklc281');
    setLlmModel('gemini-2.5-flash');
    setShowModal(true);
  };

  const handleCreate = async () => {
    try {
      setSaving(true);
      const created = await createAgent({
        name: agentName,
        prompt: systemPrompt,
        voice_id: selectedVoice,
        llm_model: llmModel,
      });
      await mutateAgents((current) => [created, ...(current ?? [])], { revalidate: false });

      setShowModal(false);
      setSaveSuccessMessage(true);
      setSaveError(null);
      setTimeout(() => setSaveSuccessMessage(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to create agent');
    } finally {
      setSaving(false);
    }
  };

  const inputClassName =
    'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring';

  const handleExportAgents = () => {
    const csv = toCsv(
      ['Agent ID', 'Agent Name', 'Voice', 'Minutes Used', 'Created At'],
      (agents ?? []).map((agent) => [
        agent.id,
        agent.name,
        agent.voice_id,
        ((agent.total_agent_sec ?? 0) / 60).toFixed(1),
        agent.created_at ?? '',
      ]),
    );
    downloadCsv('agents.csv', csv);
  };

  return (
    <div>
      <PageHeader
        title="Manage Agent Configurations"
        description="Configure LLM system instructions, assigned Urdu voices, and connection settings."
        actions={
          <>
            <Button variant="secondary" onClick={handleExportAgents}>
              <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Export CSV
            </Button>
            <Button onClick={openCreateModal}>+ Configure Agent</Button>
          </>
        }
      />

      {agentsSWRError || saveError ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {saveError ??
            (agentsSWRError instanceof Error ? agentsSWRError.message : 'Failed to load agents')}
        </div>
      ) : null}

      {saveSuccessMessage ? (
        <div className="mb-6 rounded-md border border-border bg-muted px-4 py-3 text-sm font-medium text-foreground">
          Agent created successfully.
        </div>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          {agentsLoading ? (
            <DataTableSkeleton rows={4} />
          ) : (agents ?? []).length === 0 ? (
            <EmptyState
              title="No agents found yet"
              description="Create one to begin."
            />
          ) : (
            <div className="w-full text-sm">
              <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_2.5rem] border-b border-border">
                <div className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">
                  Agent Name
                </div>
                <div className="h-10 py-2 pl-20 pr-3 text-left align-middle font-medium text-muted-foreground">
                  Assigned Voice
                </div>
                <div className="h-10 px-3 text-center align-middle font-medium text-muted-foreground">
                  Minutes Used
                </div>
                <div className="h-10 px-1 align-middle">
                  <span className="sr-only">Copy ID</span>
                </div>
              </div>

              <div className="divide-y divide-border">
                {(agents ?? []).map((agent) => {
                  const isCopied = copiedAgentId === agent.id;
                  return (
                    <div
                      key={agent.id}
                      onClick={() => router.push(`/agents/${agent.id}`)}
                      className="group grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_2.5rem] items-center transition-colors hover:bg-muted/30"
                    >
                      <div className="truncate p-3 text-left align-middle font-medium">
                        <RowOpenButton
                          onClick={() => router.push(`/agents/${agent.id}`)}
                          ariaLabel={`Edit settings and voice for ${agent.name}`}
                        >
                          {agent.name}
                        </RowOpenButton>
                      </div>
                      <div className="truncate py-3 pl-20 pr-3 text-left align-middle">
                        <Badge>{agent.voice_id}</Badge>
                      </div>
                      <div className="truncate p-3 text-center align-middle">
                        {((agent.total_agent_sec ?? 0) / 60).toFixed(1)} min
                      </div>
                      <div className="flex items-center justify-center p-1 align-middle">
                        <button
                          type="button"
                          onClick={(e) => handleCopyAgentId(agent.id, e)}
                          aria-label={
                            isCopied ? `Copied ID for ${agent.name}` : `Copy ID for ${agent.name}`
                          }
                          title={isCopied ? 'Copied' : 'Copy ID'}
                          className={cn(
                            'inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-transparent text-muted-foreground opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100 focus-visible:opacity-100',
                            isCopied && 'opacity-100',
                          )}
                        >
                          {isCopied ? (
                            <Check className="h-3.5 w-3.5" aria-hidden="true" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                          )}
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

      <Modal
        open={showModal}
        onOpenChange={setShowModal}
        title="Create Agent"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreate()} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">Status</label>
            <div className={cn(inputClassName, 'cursor-not-allowed bg-muted text-muted-foreground')}>
              Active
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">Agent Display Name</label>
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              className={inputClassName}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">System Prompt</label>
            <textarea
              rows={4}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className={inputClassName}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">Assigned Urdu Voice</label>
            <Select
              value={selectedVoice}
              onValueChange={setSelectedVoice}
              options={(voices ?? []).map((voice) => ({
                value: voice.id,
                label: `${voice.displayName} (${capitalize(voice.gender)})`,
              }))}
              className="w-full"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
