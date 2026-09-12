'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import {
  Phone,
  Radio,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Search,
  Plus,
  ShieldCheck,
  Zap,
  Globe,
  Settings,
  PhoneOutgoing,
  KeyRound,
  Trash2,
} from 'lucide-react';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import {
  connectTelnyx,
  rotateTelnyxKey,
  reverifyTelnyx,
  disconnectTelnyx,
  syncManagedNumbers,
  assignAgentToNumber,
  searchAvailableNumbers,
  reserveNumber,
  purchaseNumber,
  upsertSipConnection,
  testSipConnection,
  createOutboundCall,
  AvailablePhoneNumber,
  ManagedPhoneNumber,
} from '@/lib/telephonyApi';

export default function TelephonyPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'numbers' | 'search' | 'sip' | 'test'>('overview');

  // SWR hooks
  const { data: connection, mutate: mutateConnection, isLoading: loadingConn } = useSWR(
    swrKeys.telephonyConnection,
    swrFetchers.telephonyConnection
  );

  const { data: numbers, mutate: mutateNumbers, isLoading: loadingNumbers } = useSWR(
    swrKeys.telephonyNumbers,
    swrFetchers.telephonyNumbers
  );

  const { data: readiness, mutate: mutateReadiness } = useSWR(
    swrKeys.telephonyReadiness,
    swrFetchers.telephonyReadiness
  );

  const { data: drift, mutate: mutateDrift } = useSWR(
    swrKeys.telephonyDrift,
    swrFetchers.telephonyDrift
  );

  const { data: agents } = useSWR(swrKeys.agents, swrFetchers.agents);

  const isTelnyxConnected = Boolean(
    connection?.connected ||
    connection?.platform_status === 'active' ||
    connection?.provider_status === 'active' ||
    connection?.status === 'active'
  );

  // Form & Action States
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [labelInput, setLabelInput] = useState('');
  const [isRotateMode, setIsRotateMode] = useState(false);
  const [showRotateOffer, setShowRotateOffer] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Search state
  const [searchCountry, setSearchCountry] = useState('US');
  const [searchAreaCode, setSearchAreaCode] = useState('');
  const [searchType, setSearchType] = useState('local');
  const [searchResults, setSearchResults] = useState<AvailablePhoneNumber[]>([]);
  const [searching, setSearching] = useState(false);

  // SIP state
  const [sipFqdn, setSipFqdn] = useState('');
  const [sipUser, setSipUser] = useState('');
  const [sipSecret, setSipSecret] = useState('');
  const [sipTesting, setSipTesting] = useState(false);

  // Outbound call state
  const [outboundAgentId, setOutboundAgentId] = useState('');
  const [outboundToNumber, setOutboundToNumber] = useState('');

  // Actions
  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;
    setIsSubmitting(true);
    setFeedback(null);
    setShowRotateOffer(false);
    try {
      if (isRotateMode) {
        await rotateTelnyxKey(apiKeyInput.trim());
        setFeedback({ type: 'success', message: 'Telnyx API key rotated successfully!' });
      } else {
        await connectTelnyx(apiKeyInput.trim(), labelInput.trim() || undefined);
        setFeedback({ type: 'success', message: 'Telnyx account successfully connected!' });
      }
      setApiKeyInput('');
      setLabelInput('');
      setIsRotateMode(false);
      await mutateConnection();
      await mutateReadiness();
    } catch (err: any) {
      const msg = err.message || 'Failed to connect Telnyx account';
      if (msg.includes('already has an active Telnyx connection')) {
        setShowRotateOffer(true);
      }
      setFeedback({ type: 'error', message: msg });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRotateExisting = async () => {
    if (!apiKeyInput.trim()) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      await rotateTelnyxKey(apiKeyInput.trim());
      setFeedback({ type: 'success', message: 'Telnyx API key rotated successfully!' });
      setApiKeyInput('');
      setLabelInput('');
      setShowRotateOffer(false);
      setIsRotateMode(false);
      await mutateConnection();
      await mutateReadiness();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to rotate key' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReverify = async () => {
    setIsSubmitting(true);
    setFeedback(null);
    try {
      await reverifyTelnyx();
      setFeedback({ type: 'success', message: 'Telnyx connection reverified successfully.' });
      await mutateConnection();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Reverification failed' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect your active Telnyx connection?')) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      await disconnectTelnyx();
      setFeedback({ type: 'success', message: 'Telnyx connection disconnected.' });
      setIsRotateMode(false);
      await mutateConnection();
      await mutateReadiness();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Disconnect failed' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSyncNumbers = async () => {
    setIsSubmitting(true);
    setFeedback(null);
    try {
      const res = await syncManagedNumbers();
      const count = res.synced_count ?? res.items?.length ?? 0;
      setFeedback({ type: 'success', message: `Synced ${count} phone number${count !== 1 ? 's' : ''} from live Telnyx provider.` });
      await mutateConnection();
      await mutateNumbers();
      await mutateDrift();
      await mutateReadiness();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to sync numbers' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAssignAgent = async (numberId: string, agentId: string) => {
    try {
      await assignAgentToNumber(numberId, agentId || null);
      await mutateNumbers();
      setFeedback({ type: 'success', message: 'Agent assigned to phone number.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to assign agent' });
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    setSearching(true);
    setFeedback(null);
    try {
      const res = await searchAvailableNumbers({
        country: searchCountry,
        area_code: searchAreaCode || undefined,
        number_type: searchType,
      });
      setSearchResults(res || []);
      if (!res?.length) {
        setFeedback({ type: 'error', message: 'No available numbers found matching search criteria.' });
      }
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Search failed' });
    } finally {
      setSearching(false);
    }
  };

  const handlePurchase = async (number: AvailablePhoneNumber) => {
    if (!confirm(`Purchase number ${number.e164_number}?`)) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      await purchaseNumber({ e164_number: number.e164_number });
      setFeedback({ type: 'success', message: `Successfully purchased ${number.e164_number}!` });
      await mutateNumbers();
      setSearchResults(prev => prev.filter(n => n.e164_number !== number.e164_number));
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Purchase failed' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveSip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sipFqdn.trim()) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      await upsertSipConnection({
        sip_fqdn: sipFqdn.trim(),
        sip_username: sipUser.trim() || undefined,
        sip_secret: sipSecret.trim() || undefined,
      });
      setFeedback({ type: 'success', message: 'SIP connection configured successfully.' });
      await mutateReadiness();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to configure SIP connection' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTestSip = async () => {
    setSipTesting(true);
    setFeedback(null);
    try {
      const res = await testSipConnection();
      if (res.verified) {
        setFeedback({ type: 'success', message: 'SIP Connection Verified! ' + res.message });
      } else {
        setFeedback({ type: 'error', message: 'SIP Verification Warning: ' + res.message });
      }
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'SIP test failed' });
    } finally {
      setSipTesting(false);
    }
  };

  const handleTriggerCall = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!outboundAgentId || !outboundToNumber) return;
    setIsSubmitting(true);
    setFeedback(null);
    try {
      const res = await createOutboundCall({
        agent_id: outboundAgentId,
        to_e164: outboundToNumber.trim(),
      });
      setFeedback({ type: 'success', message: `Outbound call initiated! Room: ${res.room_name} (ID: ${res.call_id})` });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to initiate outbound call' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Telephony Management</h1>
            <p className="text-sm text-muted-foreground">
              Configure Telnyx provider integration, manage phone numbers, set up SIP trunking, and initiate outbound call testing.
            </p>
          </div>
          {readiness && (() => {
            const isReady = readiness.is_ready ?? readiness.ready ?? false;
            const reasonsList = readiness.reasons ?? readiness.missing_steps ?? [];
            return (
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                  isReady ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-sky-50 text-sky-700 border border-sky-200'
                }`}>
                  {isReady ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Phone className="h-3.5 w-3.5" />}
                  {isReady ? 'Telephony Active' : `Setup Pending (${reasonsList.length} step${reasonsList.length !== 1 ? 's' : ''})`}
                </span>
              </div>
            );
          })()}
        </div>

        {/* Global Feedback Banner */}
        {feedback && (
          <div className={`rounded-lg border p-4 text-sm ${
            feedback.type === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-destructive/30 bg-destructive/10 text-destructive'
          }`}>
            <div className="flex items-center justify-between">
              <span>{feedback.message}</span>
              {showRotateOffer && (
                <button
                  onClick={handleRotateExisting}
                  disabled={isSubmitting}
                  className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  Rotate Key with Provided API Key
                </button>
              )}
            </div>
          </div>
        )}

        {/* Sub Navigation Tabs */}
        <div className="flex border-b border-border gap-2 overflow-x-auto">
          {[
            { id: 'overview', label: 'Provider Connection', icon: ShieldCheck },
            { id: 'numbers', label: 'Managed Numbers', icon: Phone },
            { id: 'search', label: 'Search & Purchase', icon: Search },
            { id: 'sip', label: 'SIP & Trunking', icon: Radio },
            { id: 'test', label: 'Outbound Tester', icon: PhoneOutgoing },
          ].map(tab => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id as any); setFeedback(null); setShowRotateOffer(false); }}
                className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap ${
                  active ? 'border-primary text-foreground font-semibold' : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* TAB 1: OVERVIEW & PROVIDER CONNECTION */}
        {activeTab === 'overview' && (
          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-lg border border-border bg-card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-primary" />
                  Telnyx Account Connection
                </h2>
                {isTelnyxConnected && (
                  <button
                    onClick={() => setIsRotateMode(!isRotateMode)}
                    className="text-xs font-medium text-primary hover:underline flex items-center gap-1"
                  >
                    <KeyRound className="h-3.5 w-3.5" />
                    {isRotateMode ? 'Cancel Key Rotation' : 'Rotate API Key'}
                  </button>
                )}
              </div>

              {loadingConn ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <RefreshCw className="h-4 w-4 animate-spin" /> Loading connection status...
                </div>
              ) : isTelnyxConnected && !isRotateMode ? (
                <div className="space-y-4">
                  <div className="rounded-md border border-emerald-200 bg-emerald-50/50 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-emerald-800 uppercase tracking-wider">Status</span>
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Connected
                      </span>
                    </div>
                    <p className="text-sm font-medium text-foreground">Label: {connection?.label || 'Default Telnyx Connection'}</p>
                    <p className="text-xs text-muted-foreground font-mono">Key Mask: {connection?.key_mask || connection?.key_fingerprint || '••••••••'}</p>
                    {(connection?.verified_at || connection?.last_verified_at) && (
                      <p className="text-xs text-muted-foreground">Verified: {new Date(connection.verified_at || connection.last_verified_at!).toLocaleString()}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      onClick={handleReverify}
                      disabled={isSubmitting}
                      className="rounded-md border border-border bg-background px-3.5 py-2 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      Re-verify Connection
                    </button>
                    <button
                      onClick={() => setIsRotateMode(true)}
                      className="rounded-md border border-border bg-background px-3.5 py-2 text-xs font-medium text-foreground hover:bg-accent transition-colors flex items-center gap-1.5"
                    >
                      <KeyRound className="h-3.5 w-3.5 text-primary" />
                      Rotate API Key
                    </button>
                    <button
                      onClick={handleDisconnect}
                      disabled={isSubmitting}
                      className="rounded-md border border-destructive/30 bg-destructive/10 px-3.5 py-2 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Disconnect
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleConnect} className="space-y-4">
                  <p className="text-xs text-muted-foreground">
                    {isRotateMode
                      ? 'Enter a new Telnyx V2 API Key to rotate your existing account credentials without breaking phone numbers.'
                      : 'Connect your Telnyx API key to enable phone number provisioning, SIP trunking, and PSTN calls for your agents.'}
                  </p>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-foreground">
                      {isRotateMode ? 'New Telnyx V2 API Key' : 'Telnyx V2 API Key'}
                    </label>
                    <input
                      type="password"
                      placeholder="KEY019FC..."
                      value={apiKeyInput}
                      onChange={e => setApiKeyInput(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
                      required
                    />
                  </div>
                  {!isRotateMode && (
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-foreground">Connection Label (Optional)</label>
                      <input
                        type="text"
                        placeholder="Production Telnyx Account"
                        value={labelInput}
                        onChange={e => setLabelInput(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      />
                    </div>
                  )}
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  >
                    {isSubmitting
                      ? 'Processing...'
                      : isRotateMode
                      ? 'Rotate Telnyx API Key'
                      : 'Connect Telnyx Account'}
                  </button>
                </form>
              )}
            </div>

            <div className="rounded-lg border border-border bg-card p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                Telephony System Readiness
              </h2>
              {readiness ? (
                <div className="space-y-3">
                  {[
                    { label: 'Telnyx Account Connected', status: readiness.connection_status === 'active' || Boolean(readiness.has_connection) },
                    { label: 'SIP Connection Configured', status: readiness.sip_status === 'active' || Boolean(readiness.has_sip_connection) },
                    { label: 'Outbound Profile Active', status: readiness.outbound_profile_status === 'active' || Boolean(readiness.has_outbound_profile) },
                    { label: 'Routed Agent Numbers Ready', status: (readiness.active_numbers_count ?? 0) > 0 || Boolean(readiness.has_managed_numbers) },
                  ].map((step, idx) => (
                    <div key={idx} className="flex items-center justify-between border-b border-border/60 pb-2 text-sm">
                      <span className="text-muted-foreground">{step.label}</span>
                      {step.status ? (
                        <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Ready
                        </span>
                      ) : (
                        <span className="text-xs font-semibold text-amber-600 flex items-center gap-1">
                          <AlertCircle className="h-3.5 w-3.5" /> Pending
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Checking system readiness...</p>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: MANAGED NUMBERS */}
        {activeTab === 'numbers' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Managed Phone Numbers</h2>
                <p className="text-xs text-muted-foreground">Assign phone numbers to agents for automated inbound call routing.</p>
              </div>
              <button
                onClick={handleSyncNumbers}
                disabled={isSubmitting}
                className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isSubmitting ? 'animate-spin' : ''}`} />
                Sync Provider Numbers
              </button>
            </div>

            {drift?.drift_detected && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800 space-y-1">
                <p className="font-semibold flex items-center gap-1">
                  <AlertCircle className="h-4 w-4 text-amber-600" /> Configuration Drift Detected
                </p>
                <p>Provider count ({drift.provider_count}) differs from local inventory ({drift.managed_count}). Click "Sync Provider Numbers" to align.</p>
              </div>
            )}

            {loadingNumbers ? (
              <p className="text-sm text-muted-foreground">Loading phone numbers...</p>
            ) : numbers && numbers.length > 0 ? (
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                    <tr>
                      <th className="px-4 py-3">Phone Number</th>
                      <th className="px-4 py-3">Country</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Assigned Agent</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {numbers.map((num: ManagedPhoneNumber) => {
                      const isMissingAtProvider = drift?.missing_in_provider?.includes(num.e164_number);

                      return (
                        <tr key={num.id} className="hover:bg-accent/40 transition-colors">
                          <td className="px-4 py-3 font-mono font-medium text-foreground">{num.e164_number}</td>
                          <td className="px-4 py-3 text-muted-foreground">{num.country || 'US'}</td>
                          <td className="px-4 py-3">
                            {!isTelnyxConnected ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-800 border border-amber-200">
                                <AlertCircle className="h-3 w-3 text-amber-600" /> Disconnected (No API)
                              </span>
                            ) : isMissingAtProvider ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-0.5 text-xs font-medium text-rose-800 border border-rose-200">
                                <AlertCircle className="h-3 w-3 text-rose-600" /> Disconnected (Not on Active Telnyx Acc)
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 border border-emerald-200">
                                <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Live & Active
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <select
                              value={num.assigned_agent_id || ''}
                              onChange={e => handleAssignAgent(num.id, e.target.value)}
                              className="rounded-md border border-input bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                            >
                              <option value="">-- Unassigned --</option>
                              {agents?.map((agent: any) => (
                                <option key={agent.id} value={agent.id}>{agent.name}</option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground space-y-3">
                <Phone className="mx-auto h-8 w-8 text-muted-foreground/60" />
                <p className="text-sm font-medium">No managed phone numbers found</p>
                <p className="text-xs">Use the "Search & Purchase" tab to find and acquire numbers.</p>
              </div>
            )}

            {numbers && numbers.length > 0 && (
              <div className="rounded-lg border border-border bg-card p-6 space-y-3">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Globe className="h-4 w-4 text-primary" />
                  Inbound Call Routing & PSTN Testing Guide
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  When a customer dials an assigned E.164 phone number above from any cell phone or landline:
                </p>
                <ol className="list-decimal list-inside text-xs text-muted-foreground space-y-1.5 font-mono">
                  <li>Telnyx receives the incoming PSTN call and forwards it to the LiveKit SIP trunk.</li>
                  <li>Telnyx triggers an inbound webhook to <code className="bg-muted px-1.5 py-0.5 rounded text-foreground font-semibold">/telephony/webhooks/telnyx</code>.</li>
                  <li>The platform resolves the assigned Agent ID and dispatches the LiveKit Voice Worker.</li>
                  <li>The Voice Worker (<code className="bg-muted px-1.5 py-0.5 rounded text-foreground">python -m worker.main dev</code>) answers the call in Urdu.</li>
                </ol>
                <div className="pt-2">
                  <span className="inline-flex items-center gap-1.5 text-xs text-sky-700 bg-sky-50 border border-sky-200 px-3 py-1.5 rounded-md font-medium">
                    <Phone className="h-3.5 w-3.5" />
                    To test inbound calls: Dial any assigned phone number above from your mobile phone!
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: SEARCH & PURCHASE */}
        {activeTab === 'search' && (
          <div className="space-y-6">
            <form onSubmit={handleSearch} className="rounded-lg border border-border bg-card p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Search className="h-5 w-5 text-primary" />
                Search Available Phone Numbers
              </h2>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Country</label>
                  <select
                    value={searchCountry}
                    onChange={e => setSearchCountry(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="US">United States (+1)</option>
                    <option value="PK">Pakistan (+92)</option>
                    <option value="CA">Canada (+1)</option>
                    <option value="GB">United Kingdom (+44)</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Area Code (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. 415"
                    value={searchAreaCode}
                    onChange={e => setSearchAreaCode(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-foreground">Number Type</label>
                  <select
                    value={searchType}
                    onChange={e => setSearchType(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    <option value="local">Local</option>
                    <option value="toll_free">Toll Free</option>
                    <option value="mobile">Mobile</option>
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={searching}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {searching ? 'Searching...' : 'Search Inventory'}
              </button>
            </form>

            {searchResults.length > 0 && (
              <div className="rounded-lg border border-border bg-card overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                    <tr>
                      <th className="px-4 py-3">E.164 Number</th>
                      <th className="px-4 py-3">Region</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Cost</th>
                      <th className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {searchResults.map((num, idx) => (
                      <tr key={idx} className="hover:bg-accent/40 transition-colors">
                        <td className="px-4 py-3 font-mono font-medium text-foreground">{num.e164_number}</td>
                        <td className="px-4 py-3 text-muted-foreground">{num.locality || num.region || num.country}</td>
                        <td className="px-4 py-3 text-xs capitalize">{num.number_type || 'Local'}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">${num.monthly_cost || '1.00'}/mo</td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handlePurchase(num)}
                            disabled={isSubmitting}
                            className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
                          >
                            Purchase
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: SIP & TRUNKING */}
        {activeTab === 'sip' && (
          <div className="grid gap-6 md:grid-cols-2">
            <form onSubmit={handleSaveSip} className="rounded-lg border border-border bg-card p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Radio className="h-5 w-5 text-primary" />
                SIP Connection Settings
              </h2>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">SIP FQDN / Endpoint</label>
                <input
                  type="text"
                  placeholder="sip.uva.awaazlabs.com"
                  value={sipFqdn}
                  onChange={e => setSipFqdn(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">SIP Username (Optional)</label>
                <input
                  type="text"
                  placeholder="sip_user_123"
                  value={sipUser}
                  onChange={e => setSipUser(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">SIP Password / Secret (Optional)</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={sipSecret}
                  onChange={e => setSipSecret(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {isSubmitting ? 'Saving...' : 'Save SIP Configuration'}
                </button>
                <button
                  type="button"
                  onClick={handleTestSip}
                  disabled={sipTesting}
                  className="rounded-md border border-border bg-background px-3.5 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                >
                  {sipTesting ? 'Testing...' : 'Test Connection'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* TAB 5: OUTBOUND CALL TESTER */}
        {activeTab === 'test' && (
          <div className="max-w-xl rounded-lg border border-border bg-card p-6 space-y-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <PhoneOutgoing className="h-5 w-5 text-primary" />
              Outbound Call Tester
            </h2>
            <p className="text-xs text-muted-foreground">
              Trigger an automated outbound call from an assigned agent to any destination phone number.
            </p>
            <form onSubmit={handleTriggerCall} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Select Voice Agent</label>
                <select
                  value={outboundAgentId}
                  onChange={e => setOutboundAgentId(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  required
                >
                  <option value="">-- Choose Agent --</option>
                  {agents?.map((agent: any) => (
                    <option key={agent.id} value={agent.id}>{agent.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-foreground">Destination Phone Number (E.164)</label>
                <input
                  type="text"
                  placeholder="+14155552671"
                  value={outboundToNumber}
                  onChange={e => setOutboundToNumber(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
              >
                {isSubmitting ? 'Initiating Call...' : 'Trigger Outbound Call'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
