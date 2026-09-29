'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import {
  PortalAuthError,
  claimExistingTenant,
  setStoredTenantToken,
} from '@/lib/portalAuth';
import { getSupabaseBrowserClient } from '@/lib/supabaseBrowser';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

/**
 * Legacy path: tenant was provisioned with id + HMAC only (no email).
 * Sign in with email/password Auth, then prove HMAC to attach that Auth user as owner.
 * Does not call the normal exchange (which would bootstrap an empty tenant).
 */
export default function ClaimTenantPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [tenantSecret, setTenantSecret] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (signInError) {
        throw new PortalAuthError(signInError.message);
      }
      const claimed = await claimExistingTenant({
        tenantId,
        tenantSecret,
      });
      setStoredTenantToken(claimed.token);
      router.replace('/credentials');
    } catch (err) {
      setError(
        err instanceof PortalAuthError || err instanceof Error
          ? err.message
          : 'Could not claim tenant',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-8">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Claim existing tenant</CardTitle>
          <CardDescription>
            Already have a tenant ID and HMAC secret from before email login? Sign in (or use the
            email/password you just created in Supabase), then paste those credentials to attach
            this account as owner — you keep your agents and keys.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium text-muted-foreground">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium text-muted-foreground">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="tenantId" className="text-sm font-medium text-muted-foreground">
                Tenant ID / publishable key
              </label>
              <input
                id="tenantId"
                value={tenantId}
                onChange={(e) => setTenantId(e.target.value)}
                required
                spellCheck={false}
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="secret" className="text-sm font-medium text-muted-foreground">
                HMAC secret
              </label>
              <input
                id="secret"
                type="password"
                autoComplete="off"
                value={tenantSecret}
                onChange={(e) => setTenantSecret(e.target.value)}
                required
                spellCheck={false}
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? 'Claiming…' : 'Claim tenant & continue'}
            </Button>
          </form>

          <p className="mt-4 text-sm text-muted-foreground">
            New workspace with no prior tenant?{' '}
            <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
              Sign in normally
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
