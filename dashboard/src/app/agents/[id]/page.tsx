'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { ChevronLeft, Copy, Mic, Settings2, Volume2 } from 'lucide-react';

import { updateAgent } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Select, type SelectOption } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { VoiceCatalogueGrid } from '@/components/VoiceCatalogueGrid';
import { cn } from '@/lib/utils';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function providerOptions(
  layer: Record<string, { models?: string[]; voices?: string[] }> | undefined,
): SelectOption[] {
  return Object.keys(layer ?? {}).map((provider) => ({ value: provider, label: capitalize(provider) }));
}

export default function AgentDetailPage({
  params,
}: {
  params?: { id?: string };
}) {
  const routeParams = useParams<{ id: string }>();
  const id = params?.id || routeParams?.id;
  const router = useRouter();

  const {
    data: agents,
    isLoading: agentsLoading,
    mutate: mutateAgents,
  } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: capabilities } = useSWR(
    swrKeys.providerCapabilities,
    swrFetchers.providerCapabilities,
  );

  const agent = agents?.find((a) => a.id === id);

  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [voiceId, setVoiceId] = useState('');
  // Real value always comes from the seeded agent record below (llm_model is a required field
  // on every agent) -- left empty rather than baking in a stale Uplift-only model name.
  const [llmModel, setLlmModel] = useState('');
  // agent_language is create-only (same rule test-app's AgentForm enforces) — seeded here but
  // never changed by this page, since changing it would invalidate stt/llm/tts provider+voice
  // choices that were made for the OTHER language.
  const [language, setLanguage] = useState('ur');
  const [sttProvider, setSttProvider] = useState('');
  const [sttModel, setSttModel] = useState('');
  const [llmProvider, setLlmProvider] = useState('');
  const [ttsProvider, setTtsProvider] = useState('');

  const [showVoiceSettings, setShowVoiceSettings] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [idCopied, setIdCopied] = useState(false);
  const seeded = useRef(false);
  const idCopyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (seeded.current || !agent) return;
    seeded.current = true;
    setName(agent.name);
    setPrompt(agent.prompt);
    setVoiceId(agent.tts_voice_id || agent.voice_id);
    setLlmModel(agent.llm_model);
    setLanguage(agent.agent_language || 'ur');
    setSttProvider(agent.stt_provider || '');
    setSttModel(agent.stt_model || '');
    setLlmProvider(agent.llm_provider || '');
    setTtsProvider(agent.tts_provider || '');
  }, [agent]);

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
    setVoiceId(langEntry?.tts?.[next]?.defaultVoice ?? '');
  };

  useEffect(() => {
    return () => {
      if (idCopyTimeoutRef.current) clearTimeout(idCopyTimeoutRef.current);
    };
  }, []);

  const handleCopyAgentId = () => {
    if (!agent) return;
    navigator.clipboard.writeText(agent.id);
    setIdCopied(true);
    if (idCopyTimeoutRef.current) clearTimeout(idCopyTimeoutRef.current);
    idCopyTimeoutRef.current = setTimeout(() => setIdCopied(false), 1500);
  };

  const handleSave = async () => {
    if (!agent) return;
    try {
      setSaving(true);
      const updated = await updateAgent(agent.id, {
        name,
        prompt,
        voice_id: voiceId,
        llm_model: llmModel,
        agent_language: language,
        stt_provider: sttProvider,
        stt_model: sttModel,
        llm_provider: llmProvider,
        tts_provider: ttsProvider,
        tts_voice_id: voiceId,
      });
      await mutateAgents(
        (current) => (current ?? []).map((a) => (a.id === updated.id ? { ...a, ...updated } : a)),
        { revalidate: false },
      );
      setSaveSuccess(true);
      setSaveError(null);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setSaving(false);
    }
  };

  const inputClassName =
    'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring';

  const backButton = (
    <button
      type="button"
      onClick={() => router.push('/agents')}
      aria-label="Back to Agents"
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border text-foreground transition-colors hover:bg-muted"
    >
      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
    </button>
  );

  if (agentsLoading) {
    return (
      <div className="flex h-full flex-col">
        <div className="mb-6 flex items-center gap-3">
          {backButton}
          <Skeleton className="h-6 w-40" />
        </div>
        <Card className="flex flex-1 flex-col">
          <CardContent className="flex flex-1 flex-col gap-4 pt-6">
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-11 w-full" />
            <Skeleton className="h-full w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!agent) {
    return (
      <div>
        <div className="mb-6 flex items-center gap-3">{backButton}</div>
        <EmptyState
          title="Agent not found"
          description="It may have been deleted, or the link is incorrect."
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {backButton}
          <h1 className="text-xl font-semibold tracking-tight text-foreground">{agent.name}</h1>
          <button
            type="button"
            onClick={handleCopyAgentId}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-transparent px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            {idCopied ? 'Copied' : 'Agent ID'}
          </button>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            onClick={() => router.push(`/test-studio?agentId=${agent.id}`)}
          >
            <Mic className="mr-1.5 h-4 w-4 text-primary" /> Test in Studio
          </Button>
        </div>
      </div>

      {saveError ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong> {saveError}
        </div>
      ) : null}

      {saveSuccess ? (
        <div className="mb-6 rounded-md border border-border bg-muted px-4 py-3 text-sm font-medium text-foreground">
          Agent configuration updated successfully.
        </div>
      ) : null}

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardContent className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pt-6">
          <div className="flex flex-wrap gap-4">
            <div className="flex min-w-0 flex-1 basis-0 flex-col gap-1.5">
              <label className="text-sm font-medium text-muted-foreground">Agent Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={cn(inputClassName, 'h-9')}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-muted-foreground">Settings</label>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => setShowVoiceSettings(true)}>
                  <Volume2 className="mr-1.5 h-4 w-4" aria-hidden="true" /> Voice Settings
                </Button>
                <Button variant="secondary" onClick={() => setShowAdvancedSettings(true)}>
                  <Settings2 className="mr-1.5 h-4 w-4" aria-hidden="true" /> Advanced Settings
                </Button>
              </div>
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">System Instructions & Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              dir="auto"
              className={cn(inputClassName, 'flex-1 resize-none font-mono text-sm leading-relaxed')}
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push('/agents')}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={saving}
              onClick={handleSave}
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Modal
        open={showVoiceSettings}
        onOpenChange={setShowVoiceSettings}
        title="Voice Settings"
        className="max-w-3xl"
        footer={
          <div className="flex justify-end">
            <Button onClick={() => setShowVoiceSettings(false)}>Done</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Text-to-speech provider</label>
            <Select
              aria-label="TTS provider"
              value={ttsProvider}
              onValueChange={handleTtsProviderChange}
              options={providerOptions(langEntry?.tts)}
              placeholder="TTS provider"
              className="w-full sm:w-64"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Voice</label>
            <VoiceCatalogueGrid
              mode="select"
              selectedVoiceId={voiceId}
              onSelect={(voice) => setVoiceId(voice.id)}
              allowedVoiceIds={allowedVoiceIds}
            />
          </div>
        </div>
      </Modal>

      <Modal
        open={showAdvancedSettings}
        onOpenChange={setShowAdvancedSettings}
        title="Advanced Settings"
        footer={
          <div className="flex justify-end">
            <Button onClick={() => setShowAdvancedSettings(false)}>Done</Button>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Language</label>
            <div className={cn(inputClassName, 'flex h-9 items-center bg-muted text-xs text-muted-foreground')}>
              <Badge variant="outline">{language.toUpperCase()}</Badge>
              <span className="ml-2">set at creation, not editable</span>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Speech-to-text provider</label>
              <Select
                aria-label="STT provider"
                value={sttProvider}
                onValueChange={handleSttProviderChange}
                options={providerOptions(langEntry?.stt)}
                placeholder="STT provider"
                className="w-full"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Speech-to-text model</label>
              <Select
                aria-label="STT model"
                value={sttModel}
                onValueChange={setSttModel}
                options={sttModelOptions}
                placeholder="STT model"
                disabled={sttModelOptions.length === 0}
                className="w-full"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Language model provider</label>
              <Select
                aria-label="LLM provider"
                value={llmProvider}
                onValueChange={handleLlmProviderChange}
                options={providerOptions(langEntry?.llm)}
                placeholder="LLM provider"
                className="w-full"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Language model</label>
              <Select
                aria-label="LLM model"
                value={llmModel}
                onValueChange={setLlmModel}
                options={llmModelOptions}
                placeholder="LLM model"
                disabled={llmModelOptions.length === 0}
                className="w-full"
              />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
