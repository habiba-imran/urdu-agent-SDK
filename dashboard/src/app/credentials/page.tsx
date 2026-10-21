'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { Copy, Check } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { revealCredentialSecret, setAllowedOrigins } from '@/lib/portalApi';
import { isPortalAuthFailure, isPortalOwner } from '@/lib/portalAuth';
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
import { FixedToast, useFixedToast } from '@/components/ui/toast';
import { CodeBlock } from '@/components/ui/code-block';

function CopyField({
  label,
  value,
  hint,
  mono = true,
  onCopy,
  trailing,
}: {
  label: string;
  value: string;
  hint?: string;
  mono?: boolean;
  onCopy: () => void;
  trailing?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(() => {
    onCopy();
    if (timerRef.current) clearTimeout(timerRef.current);
    setCopied(true);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [onCopy]);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  return (
    <div className="flex flex-col gap-1.5">
      <label className="font-mono-label text-text-muted">{label}</label>
      <div className="flex items-center justify-between gap-3 rounded-input border border-border bg-surface-muted px-4 py-3 text-sm text-text">
        <span className={`min-w-0 flex-1 break-all ${mono ? 'font-mono text-[13px]' : ''}`}>
          {value}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          {trailing}
          <Button
            size="sm"
            variant="secondary"
            onClick={handleCopy}
            aria-label={copied ? `${label} copied` : `Copy ${label}`}
          >
            {copied
              ? <Check className="h-4 w-4 text-[var(--success)]" />
              : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      {hint ? <p className="text-[13px] text-text-muted">{hint}</p> : null}
    </div>
  );
}

/** Per-field copy button for the HMAC row (not using CopyField layout). */
function HmacCopyButton({
  hmacSecret,
  canViewKeys,
  onCopy,
}: {
  hmacSecret: string | null;
  canViewKeys: boolean;
  onCopy: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(() => {
    onCopy();
    if (timerRef.current) clearTimeout(timerRef.current);
    setCopied(true);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [onCopy]);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  return (
    <Button
      size="sm"
      variant="secondary"
      onClick={handleCopy}
      disabled={!hmacSecret}
      aria-label={copied ? 'HMAC secret copied' : 'Copy HMAC secret'}
      title={
        !canViewKeys
          ? 'Owner approval required'
          : hmacSecret
            ? copied ? 'Copied!' : 'Copy HMAC secret'
            : 'Secret not available'
      }
    >
      {copied
        ? <Check className="h-4 w-4 text-[var(--success)]" />
        : <Copy className="h-4 w-4" />}
    </Button>
  );
}

export default function CredentialsPage() {
  const { mutate } = useSWRConfig();
  const { fixedToast, showFixedToast, dismissFixedToast } = useFixedToast();
  const isOwner = isPortalOwner();
  const { data: credentials, isLoading: loading, error } = useSWR(
    swrKeys.credentials,
    swrFetchers.credentials,
    { refreshInterval: 15000 },
  );
  const canViewKeys = credentials?.can_view_api_keys === true;
  const canRevealSecret = isOwner && credentials?.secret_reveal_enabled === true;
  const { data: agents } = useSWR(swrKeys.agents, swrFetchers.agents);

  const [originsText, setOriginsText] = useState('');
  const [originsSaving, setOriginsSaving] = useState(false);
  const [originsError, setOriginsError] = useState<string | null>(null);
  const [originsNote, setOriginsNote] = useState<string | null>(null);
  // Explicit reveal stays in this page's tenant-scoped state, never the SWR metadata cache.
  const [revealedSecret, setRevealedSecret] = useState<{ tenantId: string; secret: string } | null>(null);
  const [revealingSecret, setRevealingSecret] = useState(false);
  const [secretError, setSecretError] = useState<string | null>(null);
  const hmacSecret = canRevealSecret && revealedSecret?.tenantId === credentials?.tenant_id
    ? revealedSecret?.secret ?? null : null;
  useEffect(() => {
    setRevealedSecret(null);
    setSecretError(null);
  }, [credentials?.tenant_id, canRevealSecret]);

  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [hostPublicUrl, setHostPublicUrl] = useState('http://localhost:3000');

  useEffect(() => {
    if (credentials?.allowed_origins) {
      setOriginsText(credentials.allowed_origins.join('\n'));
    }
  }, [credentials?.allowed_origins]);

  const originsEmpty = (credentials?.allowed_origins?.length ?? 0) === 0;

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
    return 'http://localhost:5174,http://localhost:3000';
  }, [credentials?.allowed_origins]);

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
  };

  const copyTextWithToast = async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    showFixedToast(`${label} copied`, 'success');
  };

  const handleCopyPublishableKey = () => {
    if (!credentials?.publishable_key) return;
    void copyToClipboard(credentials.publishable_key);
  };

  const handleCopyTenantId = () => {
    if (!credentials?.tenant_id) return;
    void copyToClipboard(credentials.tenant_id);
  };

  const handleSaveOrigins = async () => {
    if (!isOwner) {
      setOriginsError('Only the workspace owner can change allowed origins.');
      return;
    }
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
      showFixedToast('Allowed origins saved', 'success');
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
    const hmac =
      hmacSecret ||
      '<UVA_HMAC_SECRET — reveal above, or request secure operator delivery>';
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
    const agent = selectedAgentId || '<AGENT_UUID — create via @awaazlabs-uva/agents>';
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

  const hmacDisplay =
    !canViewKeys && !hmacSecret
      ? 'Owner approval required'
      : credentials?.secret_provisioned === false && !hmacSecret
        ? 'Not provisioned yet'
        : hmacSecret ||
          credentials?.secret_masked ||
          '••••••••••••••••••••••••••••••••';

  const keysReady = Boolean(credentials?.tenant_id && credentials?.publishable_key);

  const handleRevealSecret = async () => {
    const tenantId = credentials?.tenant_id;
    if (!canRevealSecret || !tenantId || revealingSecret) return;
    setRevealingSecret(true);
    setSecretError(null);
    try {
      const result = await revealCredentialSecret();
      setRevealedSecret({ tenantId, secret: result.hmac_secret });
    } catch (err) {
      setSecretError(err instanceof Error ? err.message : 'Could not reveal the secret. Ask an operator for secure delivery.');
    } finally {
      setRevealingSecret(false);
    }
  };

  const handleCopyHmacSecret = () => {
    if (!hmacSecret) return;
    void copyToClipboard(hmacSecret);
  };

  return (
    <div>
      <FixedToast toast={fixedToast} onDismiss={dismissFixedToast} />
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
        {' · '}
        <Link href="/docs/security" className="font-medium text-text underline-offset-4 hover:underline">
          Security
        </Link>
        .
      </p>

      {error && !isPortalAuthFailure(error) ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load credentials'}
        </div>
      ) : null}

      {originsEmpty && !loading ? (
        <div className="mb-6 rounded-md border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <strong>Allowed origins are empty.</strong> On hosted deployments the control plane
          rejects browser mint until you save at least one frontend origin below (and the
          dashboard origin if you use Test Studio).
        </div>
      ) : null}

      {!isOwner ? (
        <div className="mb-6 rounded-md border border-border bg-surface-muted px-4 py-3 text-sm text-text-body">
          You are signed in as a <strong>member</strong> (read-mostly). Only the workspace{' '}
          <strong>owner</strong> can change allowed origins or invite members.
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Platform URLs</CardTitle>
          <CardDescription>
            Render staging endpoints for session mint and portal APIs. Paste these into your host
            backend.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <CopyField
            label="Control plane (sessions)"
            value={PLATFORM_CONTROL_PLANE_URL}
            hint="UVA_CONTROL_PLANE_URL — your backend calls /v1/session here (HMAC-signed)."
            onCopy={() => void copyToClipboard(PLATFORM_CONTROL_PLANE_URL)}
          />
          <CopyField
            label="Tenant portal API (agents / telephony)"
            value={PLATFORM_TENANT_PORTAL_URL}
            hint="UVA_API_BASE_URL and UVA_TELEPHONY_API_URL — same base for both."
            onCopy={() => void copyToClipboard(PLATFORM_TENANT_PORTAL_URL)}
          />
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Tenant keys</CardTitle>
          <CardDescription>
            Members need owner approval to view the publishable key. Only owners can reveal HMAC for host setup.
            Copy the HMAC into your backend secret manager. Console rotation is disabled.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {loading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-11 w-full" />
              <Skeleton className="h-11 w-full" />
              <Skeleton className="h-11 w-full" />
            </div>
          ) : !canViewKeys ? (
            <p className="text-sm text-text-muted">
              Publishable key access is off. Ask your workspace owner to enable it for you in Members.
              HMAC secrets are restricted to owners.
            </p>
          ) : (
            <>
              <CopyField
                label="Tenant ID"
                value={keysReady ? credentials!.tenant_id : 'Unavailable'}
                hint="UVA_TENANT_ID — backend only. Same UUID as the publishable key."
                onCopy={handleCopyTenantId}
                trailing={
                  credentials?.name ? (
                    <Badge variant="outline">{credentials.name}</Badge>
                  ) : undefined
                }
              />

              <CopyField
                label="Publishable key"
                value={keysReady ? credentials!.publishable_key! : 'Unavailable'}
                hint="UVA_PUBLISHABLE_KEY / VITE_UVA_PUBLISHABLE_KEY — safe to embed in the client."
                onCopy={handleCopyPublishableKey}
                trailing={<Badge variant="outline">{credentials?.status ?? 'Unknown'}</Badge>}
              />

              {isOwner ? <div className="flex flex-col gap-1.5">
                <label className="font-mono-label text-text-muted">
                  HMAC secret (host server only)
                </label>
                <div className="flex items-center justify-between gap-3 rounded-input border border-border bg-surface-muted px-4 py-3 font-mono text-[13px] text-text">
                  <span className="min-w-0 flex-1 break-all">{hmacDisplay}</span>
                  {canViewKeys ? (
                    <Button size="sm" variant="secondary"
                      disabled={revealingSecret || !keysReady || !canRevealSecret || credentials?.secret_provisioned === false}
                      onClick={hmacSecret ? () => setRevealedSecret(null) : () => void handleRevealSecret()}>
                      {revealingSecret ? 'Revealing…' : hmacSecret ? 'Hide HMAC' : 'Reveal HMAC'}
                    </Button>
                  ) : null}
                  <HmacCopyButton
                    hmacSecret={hmacSecret}
                    canViewKeys={canViewKeys}
                    onCopy={handleCopyHmacSecret}
                  />
                </div>
                <p className="text-[13px] text-text-muted">
                  <code className="font-mono text-[12px]">UVA_HMAC_SECRET</code> — copy into your
                  host secret store after revealing it. Hiding it also removes it from the
                  generated env snippet. Never put it in frontend code. Console rotation is disabled.
                </p>
                {!credentials?.secret_reveal_enabled ? <p role="status" className="text-[13px] text-text-muted">
                  HMAC reveal is disabled by this deployment. Ask your operator for secure delivery
                  or to enable PORTAL_ALLOW_BROWSER_SECRET_REVEAL on the portal service.
                </p> : null}
                {secretError ? <p role="alert" className="text-[13px] text-destructive">{secretError}</p> : null}
              </div> : <p className="text-sm text-text-muted">HMAC secrets are restricted to workspace owners.</p>}
            </>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Browser allowed origins</CardTitle>
          <CardDescription>
            Origins allowed to mint voice sessions for this tenant (control-plane check). One per
            line. Hosted mint rejects an empty list — set production frontend (and dashboard, if you
            use Test Studio) origins before go-live. Also prefilled into{' '}
            <code className="font-mono text-[12px]">HOST_ALLOWED_ORIGINS</code> in the backend env
            block below.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <textarea
            value={originsText}
            onChange={(e) => setOriginsText(e.target.value)}
            rows={4}
            spellCheck={false}
            disabled={!isOwner}
            className="w-full rounded-input border border-border bg-surface px-3 py-2 font-mono text-[13px] text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft disabled:opacity-60"
            placeholder={'http://localhost:5173\nhttps://your-app.example.com'}
          />
          {originsError ? <p className="text-[13px] text-destructive">{originsError}</p> : null}
          {originsNote ? <p className="text-[13px] text-text-muted">{originsNote}</p> : null}
          {!isOwner ? (
            <p className="text-[13px] text-text-muted">Only the workspace owner can change allowed origins.</p>
          ) : null}
          <div>
            <Button onClick={handleSaveOrigins} disabled={!isOwner || originsSaving || loading}>
              {originsSaving ? 'Saving…' : 'Save origins'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {canViewKeys ? <Card className="mb-6">
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

          <Tabs defaultValue={isOwner ? 'backend' : 'frontend'}>
            <TabsList>
              {isOwner ? <TabsTrigger value="backend">Backend .env</TabsTrigger> : null}
              <TabsTrigger value="frontend">Frontend .env</TabsTrigger>
            </TabsList>

            {isOwner ? <TabsContent value="backend" className="mt-4 flex flex-col gap-3">
              <p className="text-[15px] text-text-body">
                Paste into your host backend <code className="font-mono text-[13px]">.env</code>.
                Reveal HMAC above to fill <code className="font-mono text-[13px]">UVA_HMAC_SECRET</code>.
                Leave{' '}
                <code className="font-mono text-[13px]">TELNYX_API_KEY</code> empty until you connect
                Telnyx with{' '}
                <code className="font-mono text-[13px]">@awaazlabs-uva/telephony</code>. Assigned
                numbers appear on{' '}
                <Link href="/agents" className="font-medium text-text underline-offset-4 hover:underline">
                  Agents
                </Link>
                .
              </p>
              <CodeBlock label="Backend .env" code={backendEnv} />
              <div>
                <Button
                  onClick={() => void copyTextWithToast(backendEnv, 'Backend .env')}
                  disabled={loading || (!hmacSecret && Boolean(credentials))}
                >
                  Copy backend env
                </Button>
              </div>
            </TabsContent> : null}

            <TabsContent value="frontend" className="mt-4 flex flex-col gap-3">
              <div className="flex flex-col gap-1.5 sm:max-w-md">
                <label className="font-mono-label text-text-muted">Agent ID</label>
                <select
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                  className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
                >
                  {!agents?.length ? (
                    <option value="">No agents yet — create via agents SDK</option>
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
                <Button onClick={() => void copyTextWithToast(frontendEnv, 'Frontend .env')} disabled={loading}>
                  Copy frontend env
                </Button>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card> : null}

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
