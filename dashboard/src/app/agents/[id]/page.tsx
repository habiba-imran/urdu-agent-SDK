'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { ChevronDown, ChevronLeft, Copy, Mic, Settings2, Sliders } from 'lucide-react';

import { updateAgent } from '@/lib/portalApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { VoiceAvatar } from '@/components/VoiceAvatar';
import { VoiceCatalogueGrid } from '@/components/VoiceCatalogueGrid';
import { cn } from '@/lib/utils';

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
  const { data: voices } = useSWR(swrKeys.voices, swrFetchers.voices);

  const agent = agents?.find((a) => a.id === id);

  const [mode, setMode] = useState<'basic' | 'advanced'>('basic');
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [llmModel, setLlmModel] = useState('gemini-2.5-flash');
  const [temperature, setTemperature] = useState(0.7);
  const [systemFraming, setSystemFraming] = useState('strict');

  const [showVoicePicker, setShowVoicePicker] = useState(false);
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
    setVoiceId(agent.voice_id);
    setLlmModel(agent.llm_model || 'gemini-2.5-flash');
    setTemperature(agent.temperature ?? 0.7);
    setSystemFraming(agent.system_framing_mode || 'strict');
  }, [agent]);

  useEffect(() => {
    return () => {
      if (idCopyTimeoutRef.current) clearTimeout(idCopyTimeoutRef.current);
    };
  }, []);

  const pickedVoice = voices?.find((v) => v.id === voiceId);

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
        temperature,
        system_framing_mode: systemFraming,
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

        {/* Mode Toggle & Test Action */}
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5">
            <button
              onClick={() => setMode('basic')}
              className={cn(
                'rounded px-3 py-1 text-xs font-medium transition-colors',
                mode === 'basic' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              Basic View
            </button>
            <button
              onClick={() => setMode('advanced')}
              className={cn(
                'rounded px-3 py-1 text-xs font-medium transition-colors flex items-center gap-1',
                mode === 'advanced' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Sliders className="h-3 w-3" /> Advanced View
            </button>
          </div>

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

            <div className="flex min-w-0 flex-1 basis-0 flex-col gap-1.5">
              <label className="text-sm font-medium text-muted-foreground">Assigned Voice</label>
              <button
                type="button"
                onClick={() => setShowVoicePicker(true)}
                className={cn(inputClassName, 'flex h-9 items-center justify-between gap-2 text-left hover:bg-muted/40')}
              >
                <span className="flex min-w-0 items-center gap-2">
                  {pickedVoice ? (
                    <VoiceAvatar name={pickedVoice.displayName} gender={pickedVoice.gender} seed={pickedVoice.id} size={20} />
                  ) : null}
                  <span className="truncate">{pickedVoice ? pickedVoice.displayName : voiceId}</span>
                </span>
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* Advanced Mode Controls */}
          {mode === 'advanced' && (
            <div className="grid gap-4 sm:grid-cols-3 rounded-lg border border-border bg-muted/20 p-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">LLM Model Engine</label>
                <select
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  className={cn(inputClassName, 'h-9 text-xs')}
                >
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash (Fast Low-Latency)</option>
                  <option value="gemini-1.5-pro">Gemini 1.5 Pro (Deep Reasoning)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Temperature: {temperature}</label>
                <input
                  type="range"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full h-9 cursor-pointer accent-primary"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">System Framing Mode</label>
                <select
                  value={systemFraming}
                  onChange={(e) => setSystemFraming(e.target.value)}
                  className={cn(inputClassName, 'h-9 text-xs')}
                >
                  <option value="strict">Strict (Strict Safety Bounds)</option>
                  <option value="relaxed">Relaxed (Natural Flow)</option>
                </select>
              </div>
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col gap-1.5">
            <label className="text-sm font-medium text-muted-foreground">Urdu System Instructions & Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
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

      <Modal open={showVoicePicker} onOpenChange={setShowVoicePicker} title="Select Urdu Voice">
        <VoiceCatalogueGrid
          mode="select"
          selectedVoiceId={voiceId}
          onSelect={(voice) => {
            setVoiceId(voice.id);
            setShowVoicePicker(false);
          }}
        />
      </Modal>
    </div>
  );
}
