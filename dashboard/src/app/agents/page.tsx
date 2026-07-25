'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useSWR from 'swr';
import { Search, Play, Square, Copy, Check, Download, AlertCircle } from 'lucide-react';

import { type PortalAgent, createAgent, updateAgent } from '@/lib/portalApi';
import { type ApiVoice } from '@/lib/voicesApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
import { Skeleton, DataTableSkeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  RowOpenButton,
} from '@/components/ui/table';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export default function AgentsPage() {
  const {
    data: agents,
    isLoading: agentsLoading,
    error: agentsSWRError,
    mutate: mutateAgents,
  } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: voices, isLoading: voicesLoading, error: voicesSWRError } = useSWR(
    swrKeys.voices,
    swrFetchers.voices,
  );

  const [selectedVoice, setSelectedVoice] = useState('v_meklc281');
  const [searchQuery, setSearchQuery] = useState('');
  const [genderFilter, setGenderFilter] = useState('All');
  const [agentName, setAgentName] = useState('Customer Care Agent');
  const [systemPrompt, setSystemPrompt] = useState(
    'You are a polite Urdu customer support voice assistant.',
  );
  const [llmModel, setLlmModel] = useState('gemini-2.5-flash');
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const [playErrorVoiceId, setPlayErrorVoiceId] = useState<string | null>(null);
  const [copiedVoiceId, setCopiedVoiceId] = useState<string | null>(null);
  const [copyToastPosition, setCopyToastPosition] = useState<{ top: number; right: number } | null>(
    null,
  );
  const [showModal, setShowModal] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const seededFromFirstAgent = useRef(false);

  // Default the modal's fields to the tenant's first agent once, the first time the list
  // loads — mirrors the original behavior, but only runs once (not on every background
  // SWR revalidation) so it never clobbers in-progress edits.
  useEffect(() => {
    if (seededFromFirstAgent.current || !agents || agents.length === 0) return;
    seededFromFirstAgent.current = true;
    const first = agents[0];
    setEditingAgentId(first.id);
    setAgentName(first.name);
    setSystemPrompt(first.prompt);
    setSelectedVoice(first.voice_id);
    setLlmModel(first.llm_model);
  }, [agents]);

  // Stop any in-flight preview if the page is left mid-playback.
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  const filteredVoices = (voices ?? []).filter((voice) => {
    const matchesSearch =
      voice.displayName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      voice.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesGender =
      genderFilter === 'All' || voice.gender.toLowerCase() === genderFilter.toLowerCase();
    return matchesSearch && matchesGender;
  });

  const handlePlayAudio = (voice: ApiVoice, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!voice.previewUrl) return;

    audioRef.current?.pause();
    setPlayErrorVoiceId(null);

    if (playingVoice === voice.id) {
      // Clicking the currently-playing voice again just stops it.
      setPlayingVoice(null);
      return;
    }

    const audio = new Audio(voice.previewUrl);
    audioRef.current = audio;
    setPlayingVoice(voice.id);

    const handleFailure = () => {
      setPlayingVoice((current) => (current === voice.id ? null : current));
      setPlayErrorVoiceId(voice.id);
      setTimeout(() => {
        setPlayErrorVoiceId((current) => (current === voice.id ? null : current));
      }, 3000);
    };

    audio.addEventListener('ended', () => {
      setPlayingVoice((current) => (current === voice.id ? null : current));
    });
    // Signed preview URLs expire (7 days from generation) — a stale one fails here rather
    // than silently doing nothing, so the user gets a visible "preview unavailable" cue.
    audio.addEventListener('error', handleFailure);
    audio.play().catch(handleFailure);
  };

  const handleCopyId = (voiceId: string, e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setCopyToastPosition({ top: rect.top, right: window.innerWidth - rect.right });
    navigator.clipboard.writeText(voiceId);
    setCopiedVoiceId(voiceId);
    setTimeout(() => {
      setCopiedVoiceId((current) => (current === voiceId ? null : current));
    }, 2000);
  };

  const openCreateModal = () => {
    setEditingAgentId(null);
    setAgentName('New Portal Agent');
    setSystemPrompt('You are a polite Urdu customer support voice assistant.');
    setSelectedVoice('v_meklc281');
    setLlmModel('gemini-2.5-flash');
    setShowModal(true);
  };

  const openEditModal = (agent: PortalAgent) => {
    setEditingAgentId(agent.id);
    setAgentName(agent.name);
    setSystemPrompt(agent.prompt);
    setSelectedVoice(agent.voice_id);
    setLlmModel(agent.llm_model);
    setShowModal(true);
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      if (editingAgentId) {
        const updated = await updateAgent(editingAgentId, {
          name: agentName,
          prompt: systemPrompt,
          voice_id: selectedVoice,
          llm_model: llmModel,
        });
        await mutateAgents(
          (current) =>
            (current ?? []).map((agent) =>
              agent.id === updated.id ? { ...agent, ...updated } : agent,
            ),
          { revalidate: false },
        );
      } else {
        const created = await createAgent({
          name: agentName,
          prompt: systemPrompt,
          voice_id: selectedVoice,
          llm_model: llmModel,
        });
        await mutateAgents((current) => [created, ...(current ?? [])], { revalidate: false });
        setEditingAgentId(created.id);
      }

      setShowModal(false);
      setSaveSuccessMessage(true);
      setSaveError(null);
      setTimeout(() => setSaveSuccessMessage(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setSaving(false);
    }
  };

  const inputClassName =
    'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring';

  const handleExportAgents = () => {
    const csv = toCsv(
      ['Agent ID', 'Agent Name', 'Voice', 'LLM Model', 'Minutes Used', 'Created At'],
      (agents ?? []).map((agent) => [
        agent.id,
        agent.name,
        agent.voice_id,
        agent.llm_model,
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
          Agent configuration updated successfully.
        </div>
      ) : null}

      <Card className="mb-6">
        <CardContent className="pt-6">
          {agentsLoading ? (
            <DataTableSkeleton rows={4} />
          ) : (agents ?? []).length === 0 ? (
            <EmptyState
              title="No agents found yet"
              description="Create one to begin."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="hidden md:table-cell">Agent ID</TableHead>
                  <TableHead>Agent Name</TableHead>
                  <TableHead>Assigned Voice</TableHead>
                  <TableHead>Minutes Used</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(agents ?? []).map((agent) => (
                  <TableRow key={agent.id} onClick={() => openEditModal(agent)}>
                    <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">
                      {agent.id}
                    </TableCell>
                    <TableCell className="font-medium">
                      <RowOpenButton
                        onClick={() => openEditModal(agent)}
                        ariaLabel={`Edit settings and voice for ${agent.name}`}
                      >
                        {agent.name}
                      </RowOpenButton>
                    </TableCell>
                    <TableCell>
                      <Badge>{agent.voice_id}</Badge>
                    </TableCell>
                    <TableCell>{((agent.total_agent_sec ?? 0) / 60).toFixed(1)} min</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                Complete Uplift Urdu Voice Catalogue ({(voices ?? []).length} Primary Voices)
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Select an Urdu voice entry for your AI agent.
              </p>
            </div>
            <Badge variant="outline">Voice Picker</Badge>
          </div>

          <div className="mb-4 flex flex-wrap gap-3">
            <div className="relative min-w-[240px] flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                type="text"
                placeholder="Search voices..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={cn(inputClassName, 'pl-9')}
              />
            </div>

            <div className="flex gap-2">
              {['All', 'Male', 'Female'].map((gender) => (
                <Button
                  key={gender}
                  size="sm"
                  variant={genderFilter === gender ? 'default' : 'outline'}
                  onClick={() => setGenderFilter(gender)}
                >
                  {gender}
                </Button>
              ))}
            </div>
          </div>

          {voicesSWRError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <strong>Voice catalogue error:</strong>{' '}
              {voicesSWRError instanceof Error
                ? voicesSWRError.message
                : 'Failed to load voice catalogue'}
            </div>
          ) : voicesLoading ? (
            <div className="divide-y divide-border rounded-md border border-slate-300">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="flex items-center gap-3 px-3 py-3 sm:gap-4 sm:px-4">
                  <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
                  <div className="min-w-0 flex-1">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="mt-2 h-3 w-48" />
                  </div>
                  <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
                </div>
              ))}
            </div>
          ) : (
            <div className="max-h-[560px] divide-y divide-border overflow-y-auto rounded-md border border-slate-300">
              {filteredVoices.map((voice) => {
                const isPlaying = playingVoice === voice.id;
                const isCopied = copiedVoiceId === voice.id;
                const hasPreview = Boolean(voice.previewUrl);
                const failedToPlay = playErrorVoiceId === voice.id;

                return (
                  <div
                    key={voice.id}
                    className="flex items-start gap-3 px-3 py-3 sm:items-center sm:gap-4 sm:px-4"
                  >
                    <button
                      type="button"
                      onClick={(e) => handlePlayAudio(voice, e)}
                      disabled={!hasPreview}
                      aria-label={
                        !hasPreview
                          ? `No preview available for ${voice.displayName}`
                          : isPlaying
                            ? `Stop sample of ${voice.displayName}`
                            : `Play sample of ${voice.displayName}`
                      }
                      title={!hasPreview ? 'No preview available' : undefined}
                      className={cn(
                        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors',
                        !hasPreview && 'cursor-not-allowed opacity-40',
                        failedToPlay
                          ? 'bg-destructive/10 text-destructive'
                          : isPlaying
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-foreground hover:enabled:bg-muted/70',
                      )}
                    >
                      {failedToPlay ? (
                        <AlertCircle className="h-4 w-4" aria-hidden="true" />
                      ) : isPlaying ? (
                        <Square className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true" />
                      ) : (
                        <Play className="h-4 w-4" fill="currentColor" aria-hidden="true" />
                      )}
                    </button>

                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-foreground">
                        {voice.displayName}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant="secondary" className="shrink-0">
                          {capitalize(voice.gender)}
                        </Badge>
                        <span className="truncate font-mono text-xs text-muted-foreground">
                          ID: {voice.id}
                        </span>
                        {failedToPlay ? (
                          <span className="shrink-0 text-xs text-destructive">
                            Preview unavailable
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => handleCopyId(voice.id, e)}
                      aria-label={isCopied ? `Copied ${voice.displayName}'s ID` : `Copy ${voice.displayName}'s ID`}
                      title={isCopied ? 'Copied' : 'Copy ID'}
                      className="inline-flex shrink-0 items-center justify-center self-center rounded-md bg-muted px-2.5 py-1.5 text-foreground transition-colors hover:bg-muted/70"
                    >
                      {isCopied ? (
                        <Check className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <Copy className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Modal
        open={showModal}
        onOpenChange={setShowModal}
        title={editingAgentId ? 'Edit Agent Configuration' : 'Create Agent'}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleSave()} disabled={saving}>
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

      {copiedVoiceId && copyToastPosition && typeof document !== 'undefined'
        ? createPortal(
            <div
              role="status"
              aria-live="polite"
              style={{ top: copyToastPosition.top - 8, right: copyToastPosition.right }}
              className="fixed z-[200] -translate-y-full whitespace-nowrap rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background shadow-lg animate-in fade-in slide-in-from-bottom-1"
            >
              Voice ID copied
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
