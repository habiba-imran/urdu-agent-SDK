'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { Copy, Eye, EyeOff, RefreshCw } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { getCredentialSecret, rotateCredentialSecret, setAllowedOrigins } from '@/lib/portalApi';
import { isPortalAuthFailure } from '@/lib/portalAuth';
import {
  PLATFORM_CONTROL_PLANE_URL,
  PLATFORM_TENANT_PORTAL_URL,
} from '@/lib/platformUrls';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Toast, useToast } from '@/components/ui/toast';
import { CodeBlock } from '@/components/ui/code-block';

function CopyField({
  label,
  value,
  hint,
  mono = true,
  onCopy,
  toastMessage,
  trailing,
}: {
  label: string;
  value: string;
  hint?: string;
  mono?: boolean;
  onCopy: () => void;
  toastMessage: string | null;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="font-mono-label text-text-muted">{label}</label>
      <div className="flex items-center justify-between gap-3 rounded-input border border-border bg-surface-muted px-4 py-3 text-sm text-text">
        <span className={`min-w-0 flex-1 break-all ${mono ? 'font-mono text-[13px]' : ''}`}>
          {value}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          {trailing}
          <div className="relative">
            <Toast message={toastMessage} />
            <Button size="sm" variant="secondary" onClick={onCopy} aria-label={`Copy ${label}`}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
      {hint ? <p className="text-[13px] text-text-muted">{hint}</p> : null}
    </div>
  );
}

export default function CredentialsPage() {
  const { mutate } = useSWRConfig();
  const { message: toastMessage, showToast } = useToast();
  const { data: credentials, isLoading: loading, error } = useSWR(
    swrKeys.credentials,
    swrFetchers.credentials,
  );
  const { data: agents } = useSWR(swrKeys.agents, swrFetchers.agents);

  const [hmacSecret, setHmacSecret] = useState<string | null>(null);
  const [hmacNotProvisioned, setHmacNotProvisioned] = useState(false);
  const [hmacVisible, setHmacVisible] = useState(false);
  const [hmacLoading, setHmacLoading] = useState(false);
  const [hmacError, setHmacError] = useState<string | null>(null);
  const [rotating, setRotating] = useState(false);

  const [originsText, setOriginsText] = useState('');
  const [originsSaving, setOriginsSaving] = useState(false);
  const [originsError, setOriginsError] = useState<string | null>(null);
  const [originsNote, setOriginsNote] = useState<string | null>(null);

  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [hostPublicUrl, setHostPublicUrl] = useState('http://localhost:3000');

  useEffect(() => {
    if (credentials?.allowed_origins) {
      setOriginsText(credentials.allowed_origins.join('\n'));
    }
  }, [credentials?.allowed_origins]);

  useEffect(() => {
    if (!selectedAgentId && agents?.length) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

  const hostOriginsCsv = useMemo(() => {
    const fromTenant = (credentials?.allowed_origins ?? [])
      .map((o) => o.trim())
      .filter(Boolean);
    if (fromTenant.length) return fromTenant.join(',');
    return 'http://localhost:5173,http://localhost:3000';
  }, [credentials?.allowed_origins]);

  const revealHmacSecret = async (): Promise<{
    secret: string | null;
    notProvisioned: boolean;
  }> => {
    if (hmacSecret) {
      return { secret: hmacSecret, notProvisioned: false };
    }
    if (hmacNotProvisioned) {
      return { secret: null, notProvisioned: true };
    }
    setHmacLoading(true);
    setHmacError(null);
    try {
      const { hmac_secret } = await getCredentialSecret();
      setHmacSecret(hmac_secret);
      return { secret: hmac_secret, notProvisioned: false };
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load secret';
      if (/not found|not provisioned/i.test(msg)) {
        setHmacNotProvisioned(true);
        return { secret: null, notProvisioned: true };
      }
      if (/log in again|older than|age-checked/i.test(msg)) {
        setHmacError(
          'For security, revealing the signing secret needs a fresh sign-in. Log out and back in, then try again.',
        );
        return { secret: null, notProvisioned: false };
      }
      setHmacError(msg);
      return { secret: null, notProvisioned: false };
    } finally {
      setHmacLoading(false);
    }
  };

  const handleToggleHmacVisibility = async () => {
    if (hmacVisible) {
      setHmacVisible(false);
      return;
    }
    const { secret, notProvisioned } = await revealHmacSecret();
    if (secret || notProvisioned) {
      setHmacVisible(true);
    }
  };

  const copyText = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    showToast(`${label} copied`);
  };

  const handleCopyPublishableKey = () => {
    if (!credentials?.publishable_key) return;
    void copyText(credentials.publishable_key, 'Publishable key');
  };

  const handleCopyTenantId = () => {
    if (!credentials?.tenant_id) return;
    void copyText(credentials.tenant_id, 'Tenant ID');
  };

  const handleCopyHmacSecret = async () => {
    const { secret } = await revealHmacSecret();
    if (!secret) return;
    void copyText(secret, 'HMAC secret');
  };

  const handleRotate = async () => {
    if (
      !window.confirm(
        'Rotate the HMAC secret? Every host backend using the old secret will stop working immediately. The new value is shown once.',
      )
    ) {
      return;
    }
    setRotating(true);
    setHmacError(null);
    try {
      const result = await rotateCredentialSecret();
      setHmacSecret(result.hmac_secret);
      setHmacVisible(true);
      setHmacNotProvisioned(false);
      showToast('Secret rotated — copy it now');
      void mutate(swrKeys.credentials);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Rotate failed';
      if (/log in again|older than|age-checked/i.test(msg)) {
        setHmacError(
          'For security, rotating the signing secret needs a fresh sign-in. Log out and back in, then try again.',
        );
      } else {
        setHmacError(msg);
      }
    } finally {
      setRotating(false);
    }
  };

  const handleSaveOrigins = async () => {
    setOriginsSaving(true);
    setOriginsError(null);
    setOriginsNote(null);
    try {
      const origins = originsText
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await setAllowedOrigins(origins);
      setOriginsText(result.allowed_origins.join('\n'));
      setOriginsNote(result.note);
      showToast('Allowed origins saved');
      void mutate(swrKeys.credentials);
    } catch (e) {
      setOriginsError(e instanceof Error ? e.message : 'Failed to save origins');
    } finally {
      setOriginsSaving(false);
    }
  };

  const backendEnv = useMemo(() => {
    const tenantId = credentials?.tenant_id ?? '<TENANT_UUID>';
    const pub = credentials?.publishable_key ?? '<PUBLISHABLE_KEY>';
    const hmac = hmacSecret ?? '<UVA_HMAC_SECRET — click Reveal secret above>';
    const hostBase = hostPublicUrl.replace(/\/$/, '') || 'http://localhost:3000';
    return [
      '# --- AwaazLabs tenant (from this page) ---',
      `UVA_TENANT_ID=${tenantId}`,
      `UVA_HMAC_SECRET=${hmac}`,
      `UVA_PUBLISHABLE_KEY=${pub}`,
      '',
      '# --- AwaazLabs platform (Render staging) ---',
      `UVA_CONTROL_PLANE_URL=${PLATFORM_CONTROL_PLANE_URL}`,
      `UVA_API_BASE_URL=${PLATFORM_TENANT_PORTAL_URL}`,
      `UVA_TELEPHONY_API_URL=${PLATFORM_TENANT_PORTAL_URL}`,
      '',
      '# --- Your host backend ---',
      `HOST_PUBLIC_BASE_URL=${hostBase}`,
      `HOST_ALLOWED_ORIGINS=${hostOriginsCsv}`,
      'PORT=3000',
      '',
      '# --- Telephony (optional — your Telnyx key; leave blank until connected via SDK) ---',
      'TELNYX_API_KEY=',
      'TELNYX_OUTBOUND_ALLOWED_DESTINATIONS=US',
    ].join('\n');
  }, [credentials, hmacSecret, hostPublicUrl, hostOriginsCsv]);

  const frontendEnv = useMemo(() => {
    const pub = credentials?.publishable_key ?? '<PUBLISHABLE_KEY>';
    const agent = selectedAgentId || '<AGENT_UUID — create one under Agents>';
    const base = hostPublicUrl.replace(/\/$/, '') || 'http://localhost:3000';
    return [
      '# Browser only — never put UVA_HMAC_SECRET or Telnyx keys here',
      '# Session URLs must point at YOUR host backend, not the control plane',
      `VITE_UVA_PUBLISHABLE_KEY=${pub}`,
      `VITE_UVA_SESSION_ENDPOINT=${base}/api/voice/session`,
      `VITE_UVA_REFRESH_ENDPOINT=${base}/api/voice/session/refresh`,
      `VITE_UVA_AGENT_ID=${agent}`,
      '',
      '# Next.js / other bundlers (same values, different prefix)',
      `NEXT_PUBLIC_UVA_PUBLISHABLE_KEY=${pub}`,
      `NEXT_PUBLIC_UVA_SESSION_ENDPOINT=${base}/api/voice/session`,
      `NEXT_PUBLIC_UVA_REFRESH_ENDPOINT=${base}/api/voice/session/refresh`,
      `NEXT_PUBLIC_UVA_AGENT_ID=${agent}`,
    ].join('\n');
  }, [credentials, selectedAgentId, hostPublicUrl]);

  const handleCopyBackendEnv = async () => {
    const { secret } = await revealHmacSecret();
    const text = backendEnv.replace(
      /UVA_HMAC_SECRET=.*/,
      `UVA_HMAC_SECRET=${secret ?? '<reveal failed — sign in again>'}`,
    );
    await copyText(text, 'Backend .env');
  };

  const hmacDisplay = hmacLoading
    ? 'Loading…'
    : hmacVisible && hmacSecret
      ? hmacSecret
      : hmacVisible && hmacNotProvisioned
        ? 'Not provisioned'
        : credentials?.secret_provisioned === false
          ? 'Not provisioned'
          : (credentials?.secret_masked && credentials.secret_masked !== 'masked'
              ? credentials.secret_masked
              : '••••••••••••••••••••••••••••••••');

  const keysReady = Boolean(credentials?.tenant_id && credentials?.publishable_key);

  return (
    <div>
      <PageHeader
        title="API Keys"
        breadcrumbLabel="API Keys"
        description="Everything you need to wire a host backend and frontend — platform URLs, tenant keys, and ready-to-paste env files."
      />

      <p className="mb-6 text-[15px] text-text-body">
        Walkthrough:{' '}
        <Link href="/docs/quickstart" className="font-medium text-text underline-offset-4 hover:underline">
          Quickstart
        </Link>
        {' · '}
        <Link href="/docs/backend-setup" className="font-medium text-text underline-offset-4 hover:underline">
          Backend setup
        </Link>
        .
      </p>

      {error && !isPortalAuthFailure(error) ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load credentials'}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Platform URLs</CardTitle>
          <CardDescription>
            Render staging endpoints for session mint and portal APIs. Paste these into your host
            backend. The voice worker runs locally for now — no worker URL needed here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <CopyField
            label="Control plane (sessions)"
            value={PLATFORM_CONTROL_PLANE_URL}
            hint="UVA_CONTROL_PLANE_URL — your backend calls /v1/session here (HMAC-signed)."
            onCopy={() => void copyText(PLATFORM_CONTROL_PLANE_URL, 'Control plane URL')}
            toastMessage={toastMessage}
          />
          <CopyField
            label="Tenant portal API (agents / telephony)"
            value={PLATFORM_TENANT_PORTAL_URL}
            hint="UVA_API_BASE_URL and UVA_TELEPHONY_API_URL — same base for both."
            onCopy={() => void copyText(PLATFORM_TENANT_PORTAL_URL, 'Tenant portal URL')}
            toastMessage={toastMessage}
          />
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Tenant keys</CardTitle>
          <CardDescription>
            Publishable key is safe in the browser. HMAC secret and tenant id stay on your host
            server only.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {loading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-11 w-full" />
              <Skeleton className="h-11 w-full" />
              <Skeleton className="h-11 w-full" />
            </div>
          ) : (
            <>
              <CopyField
                label="Tenant ID"
                value={keysReady ? credentials!.tenant_id : 'Unavailable'}
                hint="UVA_TENANT_ID — backend only. Same UUID as the publishable key."
                onCopy={handleCopyTenantId}
                toastMessage={toastMessage}
                trailing={
                  credentials?.name ? (
                    <Badge variant="outline">{credentials.name}</Badge>
                  ) : undefined
                }
              />

              <CopyField
                label="Publishable key"
                value={keysReady ? credentials!.publishable_key : 'Unavailable'}
                hint="UVA_PUBLISHABLE_KEY / VITE_UVA_PUBLISHABLE_KEY — safe to embed in the client."
                onCopy={handleCopyPublishableKey}
                toastMessage={toastMessage}
                trailing={<Badge variant="outline">{credentials?.status ?? 'Unknown'}</Badge>}
              />

              <div className="flex flex-col gap-1.5">
                <label className="font-mono-label text-text-muted">
                  HMAC secret (host server only)
                </label>
                <div className="flex items-center justify-between gap-3 rounded-input border border-border bg-surface-muted px-4 py-3 font-mono text-[13px] text-text">
                  <span className="min-w-0 flex-1 break-all">{hmacDisplay}</span>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleToggleHmacVisibility}
                      disabled={hmacLoading}
                      aria-label={hmacVisible ? 'Hide HMAC secret' : 'Reveal HMAC secret'}
                    >
                      {hmacVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleCopyHmacSecret}
                      disabled={hmacLoading}
                      aria-label="Copy HMAC secret"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleRotate}
                      disabled={hmacLoading || rotating}
                      aria-label="Rotate HMAC secret"
                      title="Rotate secret"
                    >
                      <RefreshCw className={`h-4 w-4 ${rotating ? 'animate-spin' : ''}`} />
                    </Button>
                  </div>
                </div>
                <p className={hmacError ? 'text-[13px] text-destructive' : 'text-[13px] text-text-muted'}>
                  {hmacError ??
                    'UVA_HMAC_SECRET — reveal needs a fresh sign-in (≤5 min). Rotate invalidates the previous secret immediately.'}
                </p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Browser allowed origins</CardTitle>
          <CardDescription>
            Origins allowed to mint voice sessions for this tenant (control-plane check). One per
            line. Also prefilled into <code className="font-mono text-[12px]">HOST_ALLOWED_ORIGINS</code>{' '}
            in the backend env block below.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <textarea
            value={originsText}
            onChange={(e) => setOriginsText(e.target.value)}
            rows={4}
            spellCheck={false}
            className="w-full rounded-input border border-border bg-surface px-3 py-2 font-mono text-[13px] text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
            placeholder={'http://localhost:5173\nhttps://your-app.example.com'}
          />
          {originsError ? <p className="text-[13px] text-destructive">{originsError}</p> : null}
          {originsNote ? <p className="text-[13px] text-text-muted">{originsNote}</p> : null}
          <div>
            <Button onClick={handleSaveOrigins} disabled={originsSaving || loading}>
              {originsSaving ? 'Saving…' : 'Save origins'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Env files</CardTitle>
          <CardDescription>
            Combined values for this tenant + Render platform URLs. Session endpoints must point at{' '}
            <em>your</em> host API, never the control plane.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5 sm:max-w-md">
            <label className="font-mono-label text-text-muted">
              Your host public URL
            </label>
            <input
              value={hostPublicUrl}
              onChange={(e) => setHostPublicUrl(e.target.value)}
              className="w-full rounded-input border border-border bg-surface px-3 py-2 font-mono text-[13px] text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
              placeholder="http://localhost:3000"
            />
            <p className="text-[13px] text-text-muted">
              Used for HOST_PUBLIC_BASE_URL and frontend session/refresh endpoints.
            </p>
          </div>

          <Tabs defaultValue="backend">
            <TabsList>
              <TabsTrigger value="backend">Backend .env</TabsTrigger>
              <TabsTrigger value="frontend">Frontend .env</TabsTrigger>
            </TabsList>

            <TabsContent value="backend" className="mt-4 flex flex-col gap-3">
              <p className="text-[15px] text-text-body">
                Paste into <code className="font-mono text-[13px]">host-backend-starter/.env</code> (or
                your own API). Use “Copy with secret” after a fresh sign-in so HMAC is filled. Leave{' '}
                <code className="font-mono text-[13px]">TELNYX_API_KEY</code> empty until you connect
                Telnyx from your backend with{' '}
                <code className="font-mono text-[13px]">@awaazlabs-uva/telephony</code>. Assigned
                numbers appear on{' '}
                <Link href="/agents" className="font-medium text-text underline-offset-4 hover:underline">
                  Agents
                </Link>
                .
              </p>
              <CodeBlock label="Backend .env" code={backendEnv} />
              <div>
                <Button onClick={handleCopyBackendEnv} disabled={loading || hmacLoading}>
                  Copy with secret
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="frontend" className="mt-4 flex flex-col gap-3">
              <div className="flex flex-col gap-1.5 sm:max-w-md">
                <label className="font-mono-label text-text-muted">Agent ID</label>
                <select
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                  className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
                >
                  {!agents?.length ? (
                    <option value="">No agents yet — create one under Agents</option>
                  ) : (
                    agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} ({a.id.slice(0, 8)}…)
                      </option>
                    ))
                  )}
                </select>
              </div>
              <p className="text-[15px] text-text-body">
                Browser only. Includes both Vite and Next.js prefixes — use the ones that match your
                app. Never put the HMAC secret or Telnyx keys in frontend env.
              </p>
              <CodeBlock label="Frontend .env" code={frontendEnv} />
              <div>
                <Button onClick={() => void copyText(frontendEnv, 'Frontend .env')} disabled={loading}>
                  Copy frontend env
                </Button>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <p className="text-[13px] text-text-muted">
        Next:{' '}
        <Link href="/docs/overview" className="font-medium text-text underline-offset-4 hover:underline">
          Docs
        </Link>{' '}
        · mint a call · verify in{' '}
        <Link href="/sessions" className="font-medium text-text underline-offset-4 hover:underline">
          Sessions
        </Link>
        .
      </p>
    </div>
  );
}
