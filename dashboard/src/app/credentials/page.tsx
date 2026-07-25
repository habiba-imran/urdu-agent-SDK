'use client';

import React, { useState } from 'react';
import useSWR from 'swr';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

export default function CredentialsPage() {
  const [copiedKey, setCopiedKey] = useState(false);
  const { data: credentials, isLoading: loading, error } = useSWR(
    swrKeys.credentials,
    swrFetchers.credentials,
  );

  const handleCopyKey = () => {
    if (!credentials?.publishable_key) {
      return;
    }
    navigator.clipboard.writeText(credentials.publishable_key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2500);
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
                <Button size="sm" variant="secondary" onClick={handleCopyKey} className="shrink-0">
                  {copiedKey ? 'Copied!' : 'Copy Key'}
                </Button>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-muted-foreground">
              SECRET HMAC KEY (Masked - Host Server Only)
            </label>
            {loading ? (
              <Skeleton className="h-11 w-full" />
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted px-4 py-3 font-mono text-sm text-muted-foreground">
                <span>{credentials?.secret_masked ?? 'Unavailable'}</span>
                <Badge variant="outline">{credentials?.status ?? 'Unknown'}</Badge>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Secrets are never returned via GET API queries. To issue a new secret, request
              secret rotation from your administrator.
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
