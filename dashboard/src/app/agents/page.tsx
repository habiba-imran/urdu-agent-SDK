'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { Check, Copy, Download, Plus } from 'lucide-react';

import { createAgent, type LanguageCapabilities } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Modal } from '@/components/ui/modal';
import { Select, type SelectOption } from '@/components/ui/select';
import { DataTableSkeleton, Skeleton } from '@/components/ui/skeleton';
import { VoiceCatalogueGrid } from '@/components/VoiceCatalogueGrid';
import { cn } from '@/lib/utils';
import { RowOpenButton } from '@/components/ui/table';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

/** Options for a provider `Select` from one capability layer (e.g. `langEntry.stt`) — the
 *  provider keys themselves are the only source of truth for what's actually enabled. */
function providerOptions(
  layer: Record<string, { models?: string[]; voices?: string[] }> | undefined,
): SelectOption[] {
  return Object.keys(layer ?? {}).map((provider) => ({ value: provider, label: capitalize(provider) }));
}

// The starting prompt text for a new agent, keyed by agent_language -- "polite Urdu customer
// support voice assistant" doesn't make sense as the default for an English agent (ADR-036
// added English/multi-provider support after this text was written).
const DEFAULT_PROMPTS: Record<string, string> = {
  ur: 'You are a polite Urdu customer support voice assistant.',
  en: 'You are a polite, helpful customer support voice assistant.',
};

function defaultPromptFor(lang: string): string {
  return DEFAULT_PROMPTS[lang] ?? 'You are a polite, helpful voice assistant.';
}

export default function AgentsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    data: agents,
    isLoading: agentsLoading,
    error: agentsSWRError,
    mutate: mutateAgents,
  } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: capabilities } = useSWR(
    swrKeys.providerCapabilities,
    swrFetchers.providerCapabilities,
  );

  const [agentName, setAgentName] = useState('New Portal Agent');
  // Real values for all of these come from applyLanguageDefaults(), always called before the
  // modal is shown (openCreateModal / handleLanguageChange) -- these initializers are never
  // actually seen by the user, so they're left empty rather than baking in stale Uplift-only
  // constants (a legacy voice id, a fixed model name) that predate multi-provider support.
  const [systemPrompt, setSystemPrompt] = useState('');
  const [language, setLanguage] = useState('ur');
  const [sttProvider, setSttProvider] = useState('');
  const [sttModel, setSttModel] = useState('');
  const [llmProvider, setLlmProvider] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('');
  const [llmModel, setLlmModel] = useState('');
  const [ttsProvider, setTtsProvider] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copiedAgentId, setCopiedAgentId] = useState<string | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const languageOptions: SelectOption[] = Object.entries(capabilities?.languages ?? {}).map(
    ([code, entry]) => ({ value: code, label: entry.label }),
  );
  const langEntry = capabilities?.languages[language];
  const sttModelOptions: SelectOption[] = (langEntry?.stt?.[sttProvider]?.models ?? []).map((m) => ({
    value: m,
    label: m,
  }));
  const llmModelOptions: SelectOption[] = (langEntry?.llm?.[llmProvider]?.models ?? []).map((m) => ({
    value: m,
    label: m,
  }));
  const allowedVoiceIds = langEntry?.tts?.[ttsProvider]?.voices ?? [];
  const canCreate = Boolean(
    agentName.trim() &&
      systemPrompt.trim() &&
      selectedVoice &&
      sttProvider &&
      llmProvider &&
      ttsProvider &&
      !saving,
  );

  const handleCopyAgentId = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(agentId);
    setCopiedAgentId(agentId);
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => {
      setCopiedAgentId((current) => (current === agentId ? null : current));
    }, 1500);
  };

  // Switching language invalidates every provider/model/voice choice below it — recompute all
  // of them to that language's first enabled option, same "no silent fallback" rule test-app's
  // AgentForm applies to its own picker. The starting prompt text is language-specific too
  // (see DEFAULT_PROMPTS), so it resets here alongside everything else.
  const applyLanguageDefaults = (lang: string, entry: LanguageCapabilities | undefined) => {
    setLanguage(lang);
    setSystemPrompt(defaultPromptFor(lang));
    const firstStt = Object.keys(entry?.stt ?? {})[0] ?? '';
    const firstLlm = Object.keys(entry?.llm ?? {})[0] ?? '';
    const firstTts = Object.keys(entry?.tts ?? {})[0] ?? '';
    setSttProvider(firstStt);
    setSttModel(entry?.stt?.[firstStt]?.defaultModel ?? '');
    setLlmProvider(firstLlm);
    setLlmModel(entry?.llm?.[firstLlm]?.defaultModel ?? '');
    setTtsProvider(firstTts);
    setSelectedVoice(entry?.tts?.[firstTts]?.defaultVoice ?? '');
  };

  const handleLanguageChange = (lang: string) => {
    applyLanguageDefaults(lang, capabilities?.languages[lang]);
  };

  const handleSttProviderChange = (next: string) => {
    setSttProvider(next);
    setSttModel(langEntry?.stt?.[next]?.defaultModel ?? '');
  };

  const handleLlmProviderChange = (next: string) => {
    setLlmProvider(next);
    setLlmModel(langEntry?.llm?.[next]?.defaultModel ?? '');
  };

  const handleTtsProviderChange = (next: string) => {
    setTtsProvider(next);
    setSelectedVoice(langEntry?.tts?.[next]?.defaultVoice ?? '');
  };

  const openCreateModal = () => {
    setAgentName('New Portal Agent');
    const langCode = capabilities ? Object.keys(capabilities.languages)[0] ?? 'ur' : 'ur';
    applyLanguageDefaults(langCode, capabilities?.languages[langCode]);
    setShowModal(true);
  };

  // Lets other pages (e.g. Overview's empty state) link straight into the create flow via
  // /agents?new=1, instead of landing on the list and requiring a second click. Waits for
  // capabilities so the modal opens with real language/provider defaults already populated,
  // not the pre-load empty state. Consumed once, then stripped from the URL so navigating
  // back here later (or refreshing) doesn't reopen it.
  const autoOpenedCreateModal = useRef(false);
  useEffect(() => {
    if (autoOpenedCreateModal.current || !capabilities) return;
    if (searchParams.get('new') === '1') {
      autoOpenedCreateModal.current = true;
      openCreateModal();
      router.replace('/agents');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capabilities, searchParams]);

  const handleCreate = async () => {
    try {
      setSaving(true);
      const created = await createAgent({
        name: agentName,
        prompt: systemPrompt,
        voice_id: selectedVoice,
        llm_model: llmModel,
        agent_language: language,
        stt_provider: sttProvider,
        stt_model: sttModel,
        llm_provider: llmProvider,
        tts_provider: ttsProvider,
        tts_voice_id: selectedVoice,
      });
      await mutateAgents((current) => [created, ...(current ?? [])], { revalidate: false });

      setShowModal(false);
      setSaveError(null);
      router.push(`/agents/${created.id}`);
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
    <div className="flex h-full flex-col">
      <PageHeader
        title="Manage Agent Configurations"
        description="Configure system instructions, language, providers, and assigned voices."
        actions={
          <>
            <Button variant="secondary" onClick={handleExportAgents}>
              <Download className="mr-1.5 h-4 w-4" aria-hidden="true" />
              Export CSV
            </Button>
            <Button onClick={openCreateModal}>
              <Plus className="mr-1.5 h-4 w-4" aria-hidden="true" />
              New Agent
            </Button>
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

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <CardContent className="flex min-h-0 flex-1 flex-col pt-6">
          {agentsLoading ? (
            <DataTableSkeleton rows={4} />
          ) : (agents ?? []).length === 0 ? (
            <EmptyState
              title="No agents found yet"
              description="Create one to begin."
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col text-sm">
              <div className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_minmax(0,1fr)_3.25rem] border-b border-border">
                <div className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">
                  Agent Name
                </div>
                <div className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">
                  Language
                </div>
                <div className="h-10 px-3 text-left align-middle font-medium text-muted-foreground">
                  Assigned Voice
                </div>
                <div className="h-10 px-3 text-center align-middle font-medium text-muted-foreground">
                  Minutes Used
                </div>
                <div className="h-10 px-3 align-middle">
                  <span className="sr-only">Actions</span>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-border">
                {(agents ?? []).map((agent) => {
                  const isCopied = copiedAgentId === agent.id;
                  return (
                    <div
                      key={agent.id}
                      onClick={() => router.push(`/agents/${agent.id}`)}
                      className="group grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_minmax(0,1fr)_3.25rem] items-center transition-colors hover:bg-muted/30"
                    >
                      <div className="truncate p-3 text-left align-middle font-medium">
                        <RowOpenButton
                          onClick={() => router.push(`/agents/${agent.id}`)}
                          ariaLabel={`Edit settings and voice for ${agent.name}`}
                        >
                          {agent.name}
                        </RowOpenButton>
                      </div>
                      <div className="truncate p-3 text-left align-middle">
                        <Badge variant="outline">
                          {(agent.agent_language ?? 'ur').toUpperCase()}
                        </Badge>
                      </div>
                      <div className="truncate p-3 text-left align-middle">
                        <Badge>{agent.voice_id}</Badge>
                      </div>
                      <div className="truncate p-3 text-center align-middle">
                        {((agent.total_agent_sec ?? 0) / 60).toFixed(1)} min
                      </div>
                      <div className="flex items-center justify-center p-3 align-middle">
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
        className="max-w-5xl"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreate()} disabled={!canCreate}>
              {saving ? 'Saving...' : 'Create Agent'}
            </Button>
          </div>
        }
      >
        {!capabilities ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                <label className="text-sm font-medium text-muted-foreground">Language</label>
                <Select
                  aria-label="Agent language"
                  value={language}
                  onValueChange={handleLanguageChange}
                  options={languageOptions}
                  className="w-full"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <fieldset className="flex flex-col gap-1.5">
                <legend className="mb-1 text-sm font-medium text-muted-foreground">Speech-to-text</legend>
                <Select
                  aria-label="STT provider"
                  value={sttProvider}
                  onValueChange={handleSttProviderChange}
                  options={providerOptions(langEntry?.stt)}
                  placeholder="STT provider"
                  className="w-full"
                />
                <Select
                  aria-label="STT model"
                  value={sttModel}
                  onValueChange={setSttModel}
                  options={sttModelOptions}
                  placeholder="STT model"
                  disabled={sttModelOptions.length === 0}
                  className="mt-1 w-full"
                />
              </fieldset>

              <fieldset className="flex flex-col gap-1.5">
                <legend className="mb-1 text-sm font-medium text-muted-foreground">Language model</legend>
                <Select
                  aria-label="LLM provider"
                  value={llmProvider}
                  onValueChange={handleLlmProviderChange}
                  options={providerOptions(langEntry?.llm)}
                  placeholder="LLM provider"
                  className="w-full"
                />
                <Select
                  aria-label="LLM model"
                  value={llmModel}
                  onValueChange={setLlmModel}
                  options={llmModelOptions}
                  placeholder="LLM model"
                  disabled={llmModelOptions.length === 0}
                  className="mt-1 w-full"
                />
              </fieldset>
            </div>

            <fieldset className="flex flex-col gap-1.5">
              <legend className="text-sm font-medium text-muted-foreground">Text-to-speech</legend>
              <Select
                aria-label="TTS provider"
                value={ttsProvider}
                onValueChange={handleTtsProviderChange}
                options={providerOptions(langEntry?.tts)}
                placeholder="TTS provider"
                className="w-full sm:w-64"
              />
            </fieldset>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-muted-foreground">Assigned Voice</label>
              <VoiceCatalogueGrid
                mode="select"
                selectedVoiceId={selectedVoice}
                onSelect={(voice) => setSelectedVoice(voice.id)}
                allowedVoiceIds={allowedVoiceIds}
              />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
