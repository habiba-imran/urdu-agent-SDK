'use client';

import React, { useEffect, useState } from 'react';

import {
  type PortalAgent,
  createAgent,
  getAgents,
  updateAgent,
} from '@/lib/portalApi';

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

  return (
    <div>
      {error && (
        <div
          style={{
            background: 'rgba(248, 113, 113, 0.15)',
            border: '1px solid rgba(248, 113, 113, 0.35)',
            color: '#fca5a5',
            padding: '0.9rem 1.25rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1.5rem',
          }}
        >
          <strong>Backend connection error:</strong> {error}
        </div>
      )}

      {saveSuccessMessage && (
        <div
          style={{
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid var(--primary)',
            color: '#34d399',
            padding: '0.9rem 1.25rem',
            borderRadius: 'var(--radius-md)',
            marginBottom: '1.5rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>OK</span> Agent configuration updated successfully.
        </div>
      )}

      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1rem',
          }}
        >
          <div>
            <h2>Manage Agent Configurations</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Configure LLM system instructions, assigned Urdu voices, and
              connection settings.
            </p>
          </div>
          <button onClick={openCreateModal} className="btn-primary">
            + Configure Agent
          </button>
        </div>

        <table className="data-table">
          <thead>
            <tr>
              <th>Agent ID</th>
              <th>Agent Name</th>
              <th>Assigned Voice</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5}>Loading agents...</td>
              </tr>
            )}
            {!loading && agents.length === 0 && (
              <tr>
                <td colSpan={5}>No agents found yet. Create one to begin.</td>
              </tr>
            )}
            {agents.map((agent) => (
              <tr key={agent.id}>
                <td
                  style={{
                    fontFamily: 'monospace',
                    color: 'var(--accent-cyan)',
                  }}
                >
                  {agent.id}
                </td>
                <td style={{ fontWeight: 600 }}>{agent.name}</td>
                <td>
                  <span className="badge badge-green">{agent.voice_id}</span>
                </td>
                <td>
                  <span className="badge badge-green">Active</span>
                </td>
                <td>
                  <button
                    onClick={() => openEditModal(agent)}
                    className="btn-secondary"
                    style={{ padding: '0.35rem 0.85rem', fontSize: '0.8rem' }}
                  >
                    Edit Settings & Voice
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="glass-card">
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
            marginBottom: '1.5rem',
          }}
        >
          <div>
            <h2>
              Complete Uplift Urdu Voice Catalogue ({ALL_82_URDU_VOICES.length}{' '}
              Primary Voices)
            </h2>
            <p
              style={{
                color: 'var(--text-muted)',
                fontSize: '0.95rem',
                marginTop: '0.2rem',
              }}
            >
              Select an Urdu voice entry for your AI agent.
            </p>
          </div>
          <div className="badge badge-purple" style={{ padding: '0.4rem 0.8rem' }}>
            Voice Picker
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            gap: '1rem',
            marginBottom: '1.5rem',
            flexWrap: 'wrap',
          }}
        >
          <input
            type="text"
            placeholder="Search voices..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              minWidth: '240px',
              padding: '0.75rem 1rem',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border-card)',
              borderRadius: 'var(--radius-md)',
              color: '#fff',
              fontSize: '0.95rem',
            }}
          />

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {['All', 'Male', 'Female'].map((gender) => (
              <button
                key={gender}
                onClick={() => setGenderFilter(gender)}
                className={genderFilter === gender ? 'btn-primary' : 'btn-secondary'}
                style={{ padding: '0.6rem 1rem', fontSize: '0.85rem' }}
              >
                {gender} Voices
              </button>
            ))}
          </div>
        </div>

        <div
          className="voice-grid"
          style={{ maxHeight: '520px', overflowY: 'auto', paddingRight: '0.5rem' }}
        >
          {filteredVoices.map((voice) => {
            const isSelected = selectedVoice === voice.id;
            const isPlaying = playingVoice === voice.id;

            return (
              <div
                key={voice.id}
                className={`voice-card ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelectedVoice(voice.id)}
              >
                <div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: '0.4rem',
                    }}
                  >
                    <div className="voice-title">{voice.name}</div>
                    <span
                      className={`badge ${
                        voice.gender === 'Female' ? 'badge-purple' : 'badge-blue'
                      }`}
                    >
                      {voice.gender}
                    </span>
                  </div>
                  <div
                    className="voice-meta"
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: 'var(--accent-cyan)',
                    }}
                  >
                    ID: {voice.id}
                  </div>
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '1rem',
                  }}
                >
                  <button
                    onClick={(event) => handlePlayAudio(voice.id, event)}
                    className="btn-secondary"
                    style={{
                      padding: '0.3rem 0.65rem',
                      fontSize: '0.75rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                    }}
                  >
                    {isPlaying ? 'Playing...' : 'Play Sample'}
                  </button>

                  {isSelected && (
                    <span
                      style={{
                        color: 'var(--primary)',
                        fontWeight: 'bold',
                        fontSize: '0.85rem',
                      }}
                    >
                      Selected
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div className="glass-card" style={{ width: '550px', background: '#0b1120' }}>
            <h2 style={{ marginBottom: '1rem' }}>
              {editingAgentId ? 'Edit Agent Configuration' : 'Create Agent'}
            </h2>

            <div style={{ marginBottom: '1rem' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.4rem',
                }}
              >
                Agent Display Name
              </label>
              <input
                type="text"
                value={agentName}
                onChange={(e) => setAgentName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.7rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid var(--border-card)',
                  borderRadius: 'var(--radius-md)',
                  color: '#fff',
                }}
              />
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.4rem',
                }}
              >
                System Prompt
              </label>
              <textarea
                rows={4}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.7rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid var(--border-card)',
                  borderRadius: 'var(--radius-md)',
                  color: '#fff',
                }}
              />
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.4rem',
                }}
              >
                LLM Model
              </label>
              <input
                type="text"
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.7rem',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid var(--border-card)',
                  borderRadius: 'var(--radius-md)',
                  color: '#fff',
                }}
              />
            </div>

            <div style={{ marginBottom: '1.5rem' }}>
              <label
                style={{
                  display: 'block',
                  fontSize: '0.85rem',
                  color: 'var(--text-muted)',
                  marginBottom: '0.4rem',
                }}
              >
                Assigned Urdu Voice
              </label>
              <select
                value={selectedVoice}
                onChange={(e) => setSelectedVoice(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.7rem',
                  background: '#1e293b',
                  border: '1px solid var(--border-card)',
                  borderRadius: 'var(--radius-md)',
                  color: '#fff',
                }}
              >
                {ALL_82_URDU_VOICES.map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {voice.name} ({voice.gender})
                  </option>
                ))}
              </select>
            </div>

            <div
              style={{
                display: 'flex',
                gap: '0.75rem',
                justifyContent: 'flex-end',
              }}
            >
              <button onClick={() => setShowModal(false)} className="btn-secondary">
                Cancel
              </button>
              <button
                onClick={() => void handleSave()}
                className="btn-primary"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
