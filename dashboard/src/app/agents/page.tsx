'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Search, Play, Copy, Check, Download } from 'lucide-react';

import {
  type PortalAgent,
  createAgent,
  getAgents,
  updateAgent,
} from '@/lib/portalApi';
import { toCsv, downloadCsv } from '@/lib/csv';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Modal } from '@/components/ui/modal';
import { Select } from '@/components/ui/select';
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

type VoiceOption = {
  id: string;
  name: string;
  gender: string;
};

const ALL_82_URDU_VOICES: VoiceOption[] = [
  { id: 'v_meklc281', name: 'Demo Voice (Default)', gender: 'Female' },
  { id: 'jinn', name: 'Jinn', gender: 'Male' },
  { id: 'sindhi-patriarch', name: 'Sindhi Patriarch', gender: 'Male' },
  { id: 'punjabi-masi', name: 'Punjabi Masi', gender: 'Female' },
  { id: 'cricket-commentator', name: 'Cricket Commentator', gender: 'Female' },
  { id: 'pashtun-pensioner', name: 'Pashtun Pensioner', gender: 'Male' },
  { id: 'crime-don', name: 'Crime Don', gender: 'Male' },
  { id: 'schoolgirl', name: 'Schoolgirl', gender: 'Female' },
  { id: 'bengali-grandfather', name: 'Bengali Grandfather', gender: 'Male' },
  { id: 'churail', name: 'Churail', gender: 'Female' },
  { id: 'balochi-seamstress', name: 'Balochi Seamstress', gender: 'Female' },
  { id: 'iqbalian-shayar', name: 'Iqbalian Shayar', gender: 'Male' },
  { id: 'late-night-rj', name: 'Late Night RJ', gender: 'Female' },
  { id: 'dha-matriarch', name: 'DHA Matriarch', gender: 'Female' },
  { id: 'bihari-organizer', name: 'Bihari Organizer', gender: 'Female' },
  { id: 'memon-organizer', name: 'Memon Organizer', gender: 'Female' },
  { id: 'crisp-storyteller', name: 'Crisp Storyteller', gender: 'Male' },
  { id: 'qissa-khawan', name: 'Qissa Khawan', gender: 'Male' },
  { id: 'female-narrator', name: 'Female Narrator', gender: 'Female' },
  { id: 'male-narrator', name: 'Male Narrator', gender: 'Male' },
  { id: 'podcast-host', name: 'Podcast Host', gender: 'Male' },
  { id: 'horror-narrator', name: 'Horror Narrator', gender: 'Male' },
  { id: 'prime-time-anchor', name: 'Prime Time Anchor', gender: 'Male' },
  { id: 'senior-anchor', name: 'Senior Anchor', gender: 'Male' },
  { id: 'news-anchor', name: 'News Anchor', gender: 'Female' },
  { id: 'news-reader', name: 'News Reader', gender: 'Female' },
  { id: 'field-correspondent', name: 'Field Correspondent', gender: 'Male' },
  { id: 'paediatrician', name: 'Paediatrician', gender: 'Female' },
  { id: 'diabetologist', name: 'Diabetologist', gender: 'Male' },
  { id: 'family-lawyer', name: 'Family Lawyer', gender: 'Female' },
  { id: 'defense-advocate', name: 'Defense Advocate', gender: 'Male' },
  { id: 'navy-officer', name: 'Navy Officer', gender: 'Male' },
  { id: 'stock-analyst', name: 'Stock Analyst', gender: 'Male' },
  { id: 'helpdesk-agent', name: 'Helpdesk Agent', gender: 'Female' },
  { id: 'broadband-support', name: 'Broadband Support', gender: 'Male' },
  { id: 'montessori-teacher', name: 'Montessori Teacher', gender: 'Female' },
  { id: 'urdu-professor', name: 'Urdu Professor', gender: 'Male' },
  { id: 'washroom-singer', name: 'Washroom Singer', gender: 'Male' },
  { id: 'khateeb', name: 'Khateeb', gender: 'Male' },
  { id: 'seerah-scholar', name: 'Seerah Scholar', gender: 'Male' },
  { id: 'hadith-narrator', name: 'Hadith Narrator', gender: 'Female' },
  { id: 'seerah-educator', name: 'Seerah Educator', gender: 'Male' },
  { id: 'dawah-youtuber', name: 'Dawah YouTuber', gender: 'Male' },
  { id: 'nosey-aunty', name: 'Nosey Aunty', gender: 'Female' },
  { id: 'orangi-khala', name: 'Orangi Khala', gender: 'Female' },
  { id: 'rohtaki-aunty', name: 'Rohtaki Aunty', gender: 'Female' },
  { id: 'dua-uncle', name: 'Dua Uncle', gender: 'Male' },
  { id: 'bus-conductor', name: 'Bus Conductor', gender: 'Male' },
  { id: 'lahori-barber', name: 'Lahori Barber', gender: 'Male' },
  { id: 'shopkeeper', name: 'Shopkeeper', gender: 'Male' },
  { id: 'street-vendor', name: 'Street Vendor', gender: 'Male' },
  { id: 'traffic-cop', name: 'Traffic Cop', gender: 'Male' },
  { id: 'khwajasara', name: 'Khwajasara', gender: 'Third-Gender' },
  { id: 'dha-teen-girl', name: 'DHA Teen Girl', gender: 'Female' },
  { id: 'dha-fitness-devotee', name: 'DHA Fitness Devotee', gender: 'Female' },
  { id: 'dha-hostess', name: 'DHA Hostess', gender: 'Female' },
  { id: 'nazimabad-boy', name: 'Nazimabad Boy', gender: 'Male' },
  { id: 'karachi-romeo', name: 'Karachi Romeo', gender: 'Male' },
  { id: 'wholesale-trader', name: 'Wholesale Trader', gender: 'Male' },
  { id: 'college-girl', name: 'College Girl', gender: 'Female' },
  { id: 'gaming-kid', name: 'Gaming Kid', gender: 'Male' },
  { id: 'udaas-aashiq', name: 'Udaas Aashiq', gender: 'Male' },
  { id: 'heartbroken', name: 'Heartbroken', gender: 'Male' },
  { id: 'udaas-philosopher', name: 'Udaas Philosopher', gender: 'Male' },
  { id: 'mohalla-storyteller', name: 'Mohalla Storyteller', gender: 'Male' },
  { id: 'mohalla-patriarch', name: 'Mohalla Patriarch', gender: 'Male' },
  { id: 'balochi-elder', name: 'Balochi Elder', gender: 'Male' },
  { id: 'bengali-businesswoman', name: 'Bengali Businesswoman', gender: 'Female' },
  { id: 'punjabi-manager', name: 'Punjabi Manager', gender: 'Male' },
  { id: 'lahori-story-uncle', name: 'Lahori Story Uncle', gender: 'Male' },
  { id: 'pashtun-teen', name: 'Pashtun Teen', gender: 'Male' },
  { id: 'pashtun-woman', name: 'Pashtun Woman', gender: 'Female' },
  { id: 'pashtun-navigator', name: 'Pashtun Navigator', gender: 'Male' },
  { id: 'sindhi-professional', name: 'Sindhi Professional', gender: 'Female' },
  { id: 'sindhi-networker', name: 'Sindhi Networker', gender: 'Male' },
  { id: 'sindhi-navigator', name: 'Sindhi Navigator', gender: 'Male' },
  { id: 'memon-trader', name: 'Memon Trader', gender: 'Male' },
  { id: 'headmaster', name: 'Headmaster', gender: 'Male' },
  { id: 'jalsa-mimic', name: 'Jalsa Mimic', gender: 'Male' },
  { id: 'street-vlogger', name: 'Street Vlogger', gender: 'Female' },
  { id: 'biryani-reviewer', name: 'Biryani Reviewer', gender: 'Male' },
  { id: 'female-debater', name: 'Female Debater', gender: 'Female' },
  { id: 'male-debater', name: 'Male Debater', gender: 'Male' },
];

export default function AgentsPage() {
  const [agents, setAgents] = useState<PortalAgent[]>([]);
  const [selectedVoice, setSelectedVoice] = useState('v_meklc281');
  const [searchQuery, setSearchQuery] = useState('');
  const [genderFilter, setGenderFilter] = useState('All');
  const [agentName, setAgentName] = useState('Customer Care Agent');
  const [systemPrompt, setSystemPrompt] = useState(
    'You are a polite Urdu customer support voice assistant.',
  );
  const [llmModel, setLlmModel] = useState('gemini-2.5-flash');
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const [copiedVoiceId, setCopiedVoiceId] = useState<string | null>(null);
  const [copyToastPosition, setCopyToastPosition] = useState<{ top: number; right: number } | null>(
    null,
  );
  const [showModal, setShowModal] = useState(false);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await getAgents();
        setAgents(data);
        if (data.length > 0) {
          const first = data[0];
          setEditingAgentId(first.id);
          setAgentName(first.name);
          setSystemPrompt(first.prompt);
          setSelectedVoice(first.voice_id);
          setLlmModel(first.llm_model);
        }
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load agents');
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  const filteredVoices = ALL_82_URDU_VOICES.filter((voice) => {
    const matchesSearch =
      voice.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      voice.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesGender =
      genderFilter === 'All' ||
      voice.gender.toLowerCase() === genderFilter.toLowerCase();
    return matchesSearch && matchesGender;
  });

  const handlePlayAudio = (voiceId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPlayingVoice(voiceId);
    setTimeout(() => {
      setPlayingVoice(null);
    }, 2000);
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
        setAgents((prev) =>
          prev.map((agent) =>
            agent.id === updated.id ? { ...agent, ...updated } : agent,
          ),
        );
      } else {
        const created = await createAgent({
          name: agentName,
          prompt: systemPrompt,
          voice_id: selectedVoice,
          llm_model: llmModel,
        });
        setAgents((prev) => [created, ...prev]);
        setEditingAgentId(created.id);
      }

      setShowModal(false);
      setSaveSuccessMessage(true);
      setError(null);
      setTimeout(() => setSaveSuccessMessage(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save agent');
    } finally {
      setSaving(false);
    }
  };

  const inputClassName =
    'w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring';

  const handleExportAgents = () => {
    const csv = toCsv(
      ['Agent ID', 'Agent Name', 'Voice', 'LLM Model', 'Minutes Used', 'Created At'],
      agents.map((agent) => [
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

      {error ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong> {error}
        </div>
      ) : null}

      {saveSuccessMessage ? (
        <div className="mb-6 rounded-md border border-border bg-muted px-4 py-3 text-sm font-medium text-foreground">
          Agent configuration updated successfully.
        </div>
      ) : null}

      <Card className="mb-6">
        <CardContent className="pt-6">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading agents...</p>
          ) : agents.length === 0 ? (
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
                {agents.map((agent) => (
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
                Complete Uplift Urdu Voice Catalogue ({ALL_82_URDU_VOICES.length} Primary Voices)
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

          <div className="max-h-[560px] divide-y divide-border overflow-y-auto rounded-md border border-slate-300">
            {filteredVoices.map((voice) => {
              const isPlaying = playingVoice === voice.id;
              const isCopied = copiedVoiceId === voice.id;

              return (
                <div
                  key={voice.id}
                  className="flex items-start gap-3 px-3 py-3 sm:items-center sm:gap-4 sm:px-4"
                >
                  <button
                    type="button"
                    onClick={(e) => handlePlayAudio(voice.id, e)}
                    aria-label={isPlaying ? `Playing sample of ${voice.name}` : `Play sample of ${voice.name}`}
                    className={cn(
                      'flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors',
                      isPlaying ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground hover:bg-muted/70',
                    )}
                  >
                    <Play className="h-4 w-4" fill="currentColor" aria-hidden="true" />
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold text-foreground">{voice.name}</div>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge variant="secondary" className="shrink-0">
                        {voice.gender}
                      </Badge>
                      <span className="truncate font-mono text-xs text-muted-foreground">
                        ID: {voice.id}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={(e) => handleCopyId(voice.id, e)}
                    aria-label={isCopied ? `Copied ${voice.name}'s ID` : `Copy ${voice.name}'s ID`}
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
              options={ALL_82_URDU_VOICES.map((voice) => ({
                value: voice.id,
                label: `${voice.name} (${voice.gender})`,
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
