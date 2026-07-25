'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

import {
  PortalAuthError,
  loginTenantPortal,
  setStoredTenantToken,
} from '@/lib/portalAuth';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function LoginPage() {
  const router = useRouter();
  const [tenantId, setTenantId] = useState('');
  const [tenantSecret, setTenantSecret] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const result = await loginTenantPortal({
        tenant_id: tenantId.trim(),
        tenant_secret: tenantSecret.trim(),
      });
      setStoredTenantToken(result.token);
      router.replace('/');
    } catch (err) {
      setError(
        err instanceof PortalAuthError || err instanceof Error
          ? err.message
          : 'Login failed',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>AwaazLabs Tenant Portal</CardTitle>
          <CardDescription>Sign in with your tenant ID and tenant secret.</CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="tenant-id" className="text-sm font-medium text-muted-foreground">
                Tenant ID
              </label>
              <input
                id="tenant-id"
                type="text"
                value={tenantId}
                onChange={(event) => setTenantId(event.target.value)}
                required
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="tenant-secret" className="text-sm font-medium text-muted-foreground">
                Tenant Secret
              </label>
              <input
                id="tenant-secret"
                type="password"
                value={tenantSecret}
                onChange={(event) => setTenantSecret(event.target.value)}
                required
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <Button type="submit" disabled={submitting} className="mt-2 w-full">
              {submitting ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
