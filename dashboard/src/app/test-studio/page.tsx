'use client';

import React, { useState, useEffect, useRef } from 'react';
import useSWR from 'swr';
import { Mic, MicOff, PhoneOff, Play, Volume2, RefreshCw, Bot, Sparkles, MessageSquare, AlertCircle } from 'lucide-react';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { getAgents, getCredentials } from '@/lib/portalApi';

type TranscriptTurn = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
};

export default function TestStudioPage() {
  const { data: agents, isLoading: loadingAgents } = useSWR(swrKeys.agents, swrFetchers.agents);
  const { data: credentials } = useSWR(swrKeys.credentials, swrFetchers.credentials);

  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [statusText, setStatusText] = useState<string>('Disconnected');
  const [transcripts, setTranscripts] = useState<TranscriptTurn[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Set default agent selection
  useEffect(() => {
    if (agents && agents.length > 0 && !selectedAgentId) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

  const handleStartSession = async () => {
    if (!selectedAgentId) {
      setErrorMsg('Please select a voice agent to test.');
      return;
    }
    setErrorMsg(null);
    setStatusText('Connecting to Voice Agent...');
    setIsConnected(true);

    // Mock/Simulated WebRTC turn loop for dashboard test studio
    const initialTurn: TranscriptTurn = {
      id: '1',
      role: 'system',
      text: 'Voice WebRTC session connected successfully.',
      timestamp: new Date().toLocaleTimeString(),
    };
    setTranscripts([initialTurn]);

    setTimeout(() => {
      setStatusText('Session Active (Listening...)');
      const agentObj = agents?.find(a => a.id === selectedAgentId);
      const greetingTurn: TranscriptTurn = {
        id: '2',
        role: 'assistant',
        text: `Assalam-o-Alaikum! Main ${agentObj?.name || 'Urdu Voice Agent'} hoon. Main aap ki kya madad kar sakta hoon?`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setTranscripts(prev => [...prev, greetingTurn]);
    }, 1500);
  };

  const handleEndSession = () => {
    setIsConnected(false);
    setStatusText('Disconnected');
    setTranscripts(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        role: 'system',
        text: 'Voice WebRTC session ended cleanly.',
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
  };

  const toggleMute = () => {
    setIsMuted(!isMuted);
  };

  const selectedAgent = agents?.find(a => a.id === selectedAgentId);

  return (
    <div>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <Mic className="h-6 w-6 text-primary" />
              WebRTC Voice Test Studio
            </h1>
            <p className="text-sm text-muted-foreground">
              Test your Urdu Voice Agents in real-time directly inside the dashboard with browser microphone input.
            </p>
          </div>
          {credentials && (
            <div className="text-xs text-muted-foreground bg-muted/50 border border-border px-3 py-1.5 rounded-md font-mono">
              Key: {credentials.publishable_key.slice(0, 8)}...
            </div>
          )}
        </div>

        {errorMsg && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {errorMsg}
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-3">
          {/* Controls Panel */}
          <div className="rounded-lg border border-border bg-card p-6 space-y-6 md:col-span-1">
            <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" />
              Agent Configuration
            </h2>

            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground">Select Agent</label>
              {loadingAgents ? (
                <p className="text-xs text-muted-foreground">Loading agents...</p>
              ) : (
                <select
                  value={selectedAgentId}
                  onChange={e => setSelectedAgentId(e.target.value)}
                  disabled={isConnected}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
                >
                  {agents?.map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.llm_model})</option>
                  ))}
                </select>
              )}
            </div>

            {selectedAgent && (
              <div className="rounded-md border border-border bg-muted/30 p-3 space-y-2 text-xs">
                <div className="flex justify-between text-muted-foreground">
                  <span>Voice ID:</span>
                  <span className="font-mono font-medium text-foreground">{selectedAgent.voice_id}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>LLM Model:</span>
                  <span className="font-mono font-medium text-foreground">{selectedAgent.llm_model}</span>
                </div>
              </div>
            )}

            <div className="pt-4 border-t border-border space-y-3">
              {!isConnected ? (
                <button
                  onClick={handleStartSession}
                  disabled={!selectedAgentId}
                  className="w-full flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  <Play className="h-4 w-4" /> Start WebRTC Call
                </button>
              ) : (
                <div className="space-y-2">
                  <button
                    onClick={toggleMute}
                    className={`w-full flex items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
                      isMuted ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-border bg-background text-foreground hover:bg-accent'
                    }`}
                  >
                    {isMuted ? <MicOff className="h-4 w-4 text-amber-600" /> : <Mic className="h-4 w-4" />}
                    {isMuted ? 'Microphone Muted' : 'Mute Microphone'}
                  </button>
                  <button
                    onClick={handleEndSession}
                    className="w-full flex items-center justify-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
                  >
                    <PhoneOff className="h-4 w-4" /> End Call
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Transcript & Status Panel */}
          <div className="rounded-lg border border-border bg-card p-6 flex flex-col h-[500px] md:col-span-2 space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5 text-primary" />
                <h2 className="text-base font-semibold text-foreground">Live Conversation Transcript</h2>
              </div>
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isConnected ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-muted text-muted-foreground'
              }`}>
                <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-muted-foreground'}`} />
                {statusText}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-2">
              {transcripts.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground space-y-2">
                  <Sparkles className="h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm">Click "Start WebRTC Call" to initiate conversation test.</p>
                </div>
              ) : (
                transcripts.map(turn => (
                  <div
                    key={turn.id}
                    className={`flex flex-col gap-1 p-3 rounded-lg text-sm ${
                      turn.role === 'user'
                        ? 'bg-primary/10 text-foreground ml-8 border border-primary/20'
                        : turn.role === 'assistant'
                        ? 'bg-muted text-foreground mr-8 border border-border'
                        : 'bg-accent/40 text-muted-foreground text-center text-xs'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                      <span className="capitalize">{turn.role}</span>
                      <span>{turn.timestamp}</span>
                    </div>
                    <p className="leading-relaxed">{turn.text}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
