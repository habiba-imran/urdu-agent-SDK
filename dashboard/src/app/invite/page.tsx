'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Session } from '@supabase/supabase-js';

import { getSupabaseBrowserClient } from '@/lib/supabaseBrowser';
import {
  PortalAuthError,
  exchangeSupabaseAccessToken,
  setStoredTenantToken,
} from '@/lib/portalAuth';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

/**
 * Invite accept page — Supabase email links land here with session tokens in the URL.
 * The invitee has no password yet; they set one, then we exchange for a portal JWT.
 *
 * Important: ``detectSessionInUrl`` finishes asynchronously after client init. Do not
 * treat a null getSession() on the first tick as an expired invite.
 */
export default function InviteAcceptPage() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [ready, setReady] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let settled = false;
    const supabase = getSupabaseBrowserClient();

    const settleOk = (session: Session) => {
      if (cancelled || settled) {
        return;
      }
      settled = true;
      setEmail(session.user.email ?? null);
      setReady(true);
      setError(null);
    };

    const settleFail = (message: string) => {
      if (cancelled || settled) {
        return;
      }
      settled = true;
      setError(message);
    };

    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (
        session &&
        (event === 'INITIAL_SESSION' ||
          event === 'SIGNED_IN' ||
          event === 'PASSWORD_RECOVERY' ||
          event === 'TOKEN_REFRESHED')
      ) {
        settleOk(session);
      }
    });

    (async () => {
      try {
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        if (code) {
          const { data: exchanged, error: exchangeError } =
            await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) {
            settleFail(exchangeError.message);
            return;
          }
          if (exchanged.session) {
            settleOk(exchanged.session);
            return;
          }
        }

        const first = await supabase.auth.getSession();
        if (first.error) {
          settleFail(first.error.message);
          return;
        }
        if (first.data.session) {
          settleOk(first.data.session);
          return;
        }

        // Hash/implicit invite links: wait for detectSessionInUrl to finish.
        await new Promise((r) => setTimeout(r, 900));
        if (cancelled || settled) {
          return;
        }
        const second = await supabase.auth.getSession();
        if (second.error) {
          settleFail(second.error.message);
          return;
        }
        if (second.data.session) {
          settleOk(second.data.session);
          return;
        }
        settleFail(
          'This invite link is missing or expired. Ask your admin to invite you again, then open the newest email.',
        );
      } catch (err) {
        settleFail(err instanceof Error ? err.message : 'Could not open invite link');
      }
    })();

    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) {
        throw updateError;
      }
      const { data, error: sessionError } = await supabase.auth.getSession();
      if (sessionError) {
        throw sessionError;
      }
      const accessToken = data.session?.access_token;
      if (!accessToken) {
        throw new PortalAuthError('Session missing after setting password');
      }
      const portal = await exchangeSupabaseAccessToken(accessToken);
      setStoredTenantToken(portal.token);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not finish invite');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Accept invitation</CardTitle>
          <CardDescription>
            Choose a password for {email ?? 'your account'}. After that you can sign in with this
            email and password anytime.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-4 rounded-input border border-danger/30 bg-[#FBEAEA] px-4 py-3 text-sm text-danger">
              {error}
            </div>
          ) : null}

          {!ready && !error ? (
            <p className="text-[15px] text-text-body">Opening invite…</p>
          ) : null}

          {ready ? (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="font-mono-label text-text-muted">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="confirm" className="font-mono-label text-text-muted">
                  Confirm password
                </label>
                <input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  className="h-11 w-full rounded-input border border-border bg-surface px-3 text-sm text-text outline-none transition-colors duration-console focus:border-accent focus:ring-2 focus:ring-accent-soft"
                />
              </div>
              <Button type="submit" disabled={submitting} className="w-full">
                {submitting ? 'Saving…' : 'Set password & continue'}
              </Button>
            </form>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
