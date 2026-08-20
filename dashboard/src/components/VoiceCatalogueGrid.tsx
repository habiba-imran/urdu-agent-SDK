'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useSWR from 'swr';
import { AlertCircle, Check, Play, Search, Square } from 'lucide-react';

import { type ApiVoice } from '@/lib/voicesApi';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { VoiceAvatar } from '@/components/VoiceAvatar';
import { cn } from '@/lib/utils';

function capitalize(value: string): string {
  return value.length > 0 ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

/**
 * The voice catalogue grid design (search + gender filter + avatar cards + play preview),
 * shared between the standalone catalogue browsing view and the per-agent voice picker.
 *
 * `mode: 'copy'` — tapping a card copies its id (shows a toast + temporary checkmark).
 * `mode: 'select'` — tapping a card calls `onSelect(voice)` and highlights `selectedVoiceId`;
 * no clipboard/toast involved, since selecting a voice for an agent is the point, not copying.
 *
 * `allowedVoiceIds`, when passed, scopes the grid to exactly those ids — the authoritative
 * "which voices work with this agent's tts_provider+agent_language" list, from
 * `getProviderCapabilities()`. Without it, every enabled voice in the catalogue is shown
 * regardless of provider — fine for browsing, wrong for picking a voice for a specific agent
 * (nothing would otherwise stop assigning e.g. a Cartesia voice id to an `uplift` agent).
 */
export function VoiceCatalogueGrid({
  mode,
  selectedVoiceId,
  onSelect,
  allowedVoiceIds,
}: {
  mode: 'copy' | 'select';
  selectedVoiceId?: string;
  onSelect?: (voice: ApiVoice) => void;
  allowedVoiceIds?: string[];
}) {
  const { data: voices, isLoading: voicesLoading, error: voicesError } = useSWR(
    swrKeys.voices,
    swrFetchers.voices,
  );

  const [search, setSearch] = useState('');
  const [gender, setGender] = useState('all');

  const [playingId, setPlayingId] = useState<string | null>(null);
  const [playErrorVoiceId, setPlayErrorVoiceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [toastPosition, setToastPosition] = useState<{ top: number; left: number } | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    };
  }, []);

  const genderOptions = useMemo(() => {
    const unique = Array.from(new Set((voices ?? []).map((v) => v.gender))).sort();
    return [{ value: 'all', label: 'Gender' }, ...unique.map((g) => ({ value: g, label: capitalize(g) }))];
  }, [voices]);

  const filteredVoices = useMemo(() => {
    const query = search.trim().toLowerCase();
    const scoped = allowedVoiceIds
      ? (voices ?? []).filter((voice) => allowedVoiceIds.includes(voice.id))
      : (voices ?? []);
    return scoped.filter((voice) => {
      if (gender !== 'all' && voice.gender !== gender) return false;
      if (
        query &&
        !voice.displayName.toLowerCase().includes(query) &&
        !voice.id.toLowerCase().includes(query)
      ) {
        return false;
      }
      return true;
    });
  }, [voices, search, gender, allowedVoiceIds]);

  const handlePlayAudio = (voice: ApiVoice, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!voice.previewUrl) return;

    setCopiedId((current) => (current === voice.id ? null : current));
    audioRef.current?.pause();
    setPlayErrorVoiceId(null);

    if (playingId === voice.id) {
      setPlayingId(null);
      return;
    }

    const audio = new Audio(voice.previewUrl);
    audioRef.current = audio;
    setPlayingId(voice.id);

    const handleFailure = () => {
      setPlayingId((current) => (current === voice.id ? null : current));
      setPlayErrorVoiceId(voice.id);
      setTimeout(() => {
        setPlayErrorVoiceId((current) => (current === voice.id ? null : current));
      }, 3000);
    };

    audio.addEventListener('ended', () => {
      setPlayingId((current) => (current === voice.id ? null : current));
    });
    audio.addEventListener('error', handleFailure);
    audio.play().catch(handleFailure);
  };

  const handleCopyId = (voice: ApiVoice, e: React.SyntheticEvent<HTMLElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setToastPosition({ top: rect.top, left: rect.left + rect.width / 2 });
    navigator.clipboard.writeText(voice.id);
    setCopiedId(voice.id);

    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => {
      setCopiedId((current) => (current === voice.id ? null : current));
      setToastPosition(null);
    }, 2000);
  };

  const handleCardActivate = (voice: ApiVoice, e: React.SyntheticEvent<HTMLElement>) => {
    if (mode === 'select') {
      onSelect?.(voice);
    } else {
      handleCopyId(voice, e);
    }
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select
          aria-label="Filter by gender"
          value={gender}
          onValueChange={setGender}
          options={genderOptions}
          placeholder="Gender"
        />
        <div className="relative min-w-[220px] flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search voices..."
            className="w-full rounded-md border border-input bg-transparent py-1.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
        </div>
      </div>

      {voicesError ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Voice catalogue error:</strong>{' '}
          {voicesError instanceof Error ? voicesError.message : 'Failed to load voice catalogue'}
        </div>
      ) : voicesLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 9 }, (_, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <Skeleton className="h-12 w-12 shrink-0 rounded-full" />
              <div className="min-w-0 flex-1">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="mt-2 h-3 w-32" />
              </div>
              <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
            </div>
          ))}
        </div>
      ) : allowedVoiceIds && allowedVoiceIds.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
          <p className="text-sm font-medium text-foreground">No voices available for this provider yet</p>
        </div>
      ) : filteredVoices.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
          <p className="text-sm font-medium text-foreground">No voices match your filters</p>
          <p className="text-sm text-muted-foreground">Try clearing the search or filters.</p>
        </div>
      ) : (
        <div className="thin-scrollbar max-h-[520px] overflow-y-auto p-1">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredVoices.map((voice) => {
              const isPlaying = playingId === voice.id;
              const isCopied = copiedId === voice.id;
              const isSelected = mode === 'select' && voice.id === selectedVoiceId;
              const hasPreview = Boolean(voice.previewUrl);
              const failedToPlay = playErrorVoiceId === voice.id;

              return (
                <div
                  key={voice.id}
                  role="button"
                  tabIndex={0}
                  onClick={(e) => handleCardActivate(voice, e)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') handleCardActivate(voice, e);
                  }}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors',
                    isSelected ? 'border-foreground/60 bg-muted/40' : 'border-border hover:border-foreground/30',
                  )}
                >
                  <VoiceAvatar name={voice.displayName} gender={voice.gender} seed={voice.id} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{voice.displayName}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="secondary" className="shrink-0">
                        {capitalize(voice.gender)}
                      </Badge>
                      <span className="truncate font-mono text-xs text-muted-foreground">
                        ID: {voice.id}
                      </span>
                    </div>
                    {failedToPlay ? (
                      <p className="mt-1 text-xs text-destructive">Preview unavailable</p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={(e) => handlePlayAudio(voice, e)}
                    disabled={!hasPreview}
                    aria-label={
                      isCopied
                        ? `Copied ID for ${voice.displayName}`
                        : !hasPreview
                          ? `No preview available for ${voice.displayName}`
                          : isPlaying
                            ? `Stop sample of ${voice.displayName}`
                            : `Play sample of ${voice.displayName}`
                    }
                    title={!hasPreview ? 'No preview available' : undefined}
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors',
                      !hasPreview && !isCopied && 'cursor-not-allowed opacity-40',
                      isCopied
                        ? 'bg-emerald-500 text-white'
                        : failedToPlay
                          ? 'bg-destructive/10 text-destructive'
                          : isPlaying
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-foreground text-background hover:enabled:bg-foreground/90',
                    )}
                  >
                    {isCopied ? (
                      <Check className="h-4 w-4" aria-hidden="true" />
                    ) : failedToPlay ? (
                      <AlertCircle className="h-4 w-4" aria-hidden="true" />
                    ) : isPlaying ? (
                      <Square className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true" />
                    ) : (
                      <Play className="h-3.5 w-3.5 translate-x-[1px]" fill="currentColor" aria-hidden="true" />
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {mode === 'copy' && copiedId && toastPosition && typeof document !== 'undefined'
        ? createPortal(
            <div
              role="status"
              aria-live="polite"
              style={{
                top: toastPosition.top,
                left: toastPosition.left,
                transform: 'translate(-50%, calc(-100% - 8px))',
              }}
              className="fixed z-[200] whitespace-nowrap rounded-md bg-foreground px-3 py-1.5 text-xs font-medium text-background shadow-lg animate-in fade-in slide-in-from-bottom-1"
            >
              ID Copied
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
