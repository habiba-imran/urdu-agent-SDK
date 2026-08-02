'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import { Copy, Eye, EyeOff } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { getCredentialSecret } from '@/lib/portalApi';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Toast, useToast } from '@/components/ui/toast';

export default function CredentialsPage() {
  const { message: pubToastMessage, showToast: showPubToast } = useToast();
  const { message: hmacToastMessage, showToast: showHmacToast } = useToast();
  const { data: credentials, isLoading: loading, error } = useSWR(
    swrKeys.credentials,
    swrFetchers.credentials,
  );

  const [hmacSecret, setHmacSecret] = useState<string | null>(null);
  const [hmacNotProvisioned, setHmacNotProvisioned] = useState(false);
  const [hmacVisible, setHmacVisible] = useState(false);
  const [hmacLoading, setHmacLoading] = useState(false);
  const [hmacError, setHmacError] = useState<string | null>(null);

  const handleCopyPublishableKey = () => {
    if (!credentials?.publishable_key) {
      return;
    }
    navigator.clipboard.writeText(credentials.publishable_key);
    showPubToast('Copied to clipboard');
  };

  /** Fetches the raw secret on first use (view or copy), then reuses it — one call per page visit.
   *  Any 404 here (tenants.hmac_secret is NULL, e.g. pre-migration-0009 tenants; or the tenant
   *  row itself is missing) is a known, non-error state — surfaced via `notProvisioned`, not
   *  `hmacError`. The backend's exact detail text varies ("no secret provisioned",
   *  "tenant not found", or a generic "Not Found" if the route itself 404s), so this matches on
   *  "not found"/"not provisioned" rather than one exact string, which is what left real 404s
   *  slipping through to the generic error path with a raw "Not Found" message. */
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

  const handleCopyHmacSecret = async () => {
    const { secret } = await revealHmacSecret();
    if (!secret) {
      return;
    }
    navigator.clipboard.writeText(secret);
    showHmacToast('Copied to clipboard');
  };

  return (
    <div>
      <PageHeader
        title="Credentials"
        description="Tenant API credentials & trust boundaries."
      />

      {error ? (
        <div className="mb-6 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <strong>Backend connection error:</strong>{' '}
          {error instanceof Error ? error.message : 'Failed to load credentials'}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-6 pt-6">
          <p className="text-sm text-muted-foreground">
            Use these credentials in your host server (Node.js/Python) to sign HMAC session
            tokens for browser clients.
          </p>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              PUBLISHABLE KEY (Safe to embed in browser clients)
            </label>
            {loading ? (
              <Skeleton className="h-11 w-full" />
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted px-4 py-3 font-mono text-sm text-foreground">
                <span className="min-w-0 flex-1 truncate">
                  {credentials?.publishable_key ?? 'Unavailable'}
                </span>
                <div className="relative shrink-0">
                  <Toast message={pubToastMessage} />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleCopyPublishableKey}
                    aria-label="Copy publishable key"
                    title="Copy publishable key"
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              SECRET HMAC KEY (Host Server Only)
            </label>
            {loading ? (
              <Skeleton className="h-11 w-full" />
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted px-4 py-3 font-mono text-sm text-muted-foreground">
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {hmacLoading
                    ? 'Loading…'
                    : hmacVisible && hmacSecret
                      ? hmacSecret
                      : hmacVisible && hmacNotProvisioned
                        ? 'NULL'
                        : credentials?.secret_masked ?? 'Unavailable'}
                </span>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge variant="outline">{credentials?.status ?? 'Unknown'}</Badge>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleToggleHmacVisibility}
                    disabled={hmacLoading}
                    aria-label={hmacVisible ? 'Hide HMAC secret' : 'View HMAC secret'}
                    title={hmacVisible ? 'Hide HMAC secret' : 'View HMAC secret'}
                  >
                    {hmacVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                  <div className="relative">
                    <Toast message={hmacToastMessage} />
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleCopyHmacSecret}
                      disabled={hmacLoading}
                      aria-label="Copy HMAC secret"
                      title="Copy HMAC secret"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            )}
            <p className={hmacError ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
              {hmacError ??
                'Click the eye icon to reveal your HMAC secret. To issue a new one, request secret rotation from your administrator.'}
            </p>
          </div>

          {loading ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-4 w-56" />
              <Skeleton className="h-4 w-72" />
            </div>
          ) : (
            <div className="flex flex-col gap-1 text-sm text-muted-foreground">
              <div>Tenant ID: {credentials?.tenant_id ?? 'Unavailable'}</div>
              <div>Tenant Name: {credentials?.name ?? 'Unavailable'}</div>
              <div>
                Allowed Origins:{' '}
                {credentials?.allowed_origins?.length
                  ? credentials.allowed_origins.join(', ')
                  : 'None configured'}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <h2 className="mb-4 text-lg font-semibold text-foreground">
            Host Backend Signing Snippet (Node.js Express)
          </h2>
          <pre className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-sm leading-6 text-foreground">
            <span className="text-muted-foreground">
              {'// Node.js signing logic per HOST_BACKEND_CONTRACT.md\n'}
            </span>
            {"import crypto from 'crypto';\n\n"}
            {'function signSession(tenantId, secret, timestamp, nonce, agentId) {\n'}
            {'  const payload = `${tenantId}.${timestamp}.${nonce}.${agentId}`;\n'}
            {"  return crypto.createHmac('sha256', secret).update(payload).digest('hex');\n"}
            {'}'}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
