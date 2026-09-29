'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

import {
  PortalAuthError,
  PORTAL_SESSION_TTL_HOURS,
  loginWithEmailPassword,
  setStoredTenantToken,
} from '@/lib/portalAuth';
import { preload } from 'swr';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const result = await loginWithEmailPassword(email, password);
      setStoredTenantToken(result.token);
      // Warm Overview cache before first paint.
      for (const key of [
        'agents',
        'credentials',
        'usage',
        'telephonyNumbers',
        'telephonyReadiness',
      ] as const) {
        void preload(swrKeys[key], swrFetchers[key]);
      }
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
    <div className="flex min-h-screen items-center justify-center bg-bg p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <p className="font-mono-label text-text-muted">Awaaz Labs</p>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Email and password for your invited account. Sessions last {PORTAL_SESSION_TTL_HOURS}{' '}
            hours; we renew quietly when Auth is still signed in.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-4 rounded-input border border-danger/30 bg-[#FBEAEA] px-4 py-3 text-sm text-danger">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="font-mono-label text-text-muted">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="font-mono-label text-text-muted">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
              />
            </div>

            <Button type="submit" disabled={submitting} className="mt-2 w-full">
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
