'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import { UserPlus } from 'lucide-react';

import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { inviteMember } from '@/lib/portalApi';
import { getPortalRole, isPortalAuthFailure } from '@/lib/portalAuth';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';

export default function MembersPage() {
  const { data: members, isLoading, error, mutate } = useSWR(
    swrKeys.members,
    swrFetchers.members,
  );
  const isOwner = getPortalRole() === 'owner';

  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const handleInvite = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFormSuccess(null);
    try {
      const invited = await inviteMember(email.trim());
      setEmail('');
      if (invited.resent) {
        setFormSuccess(
          `Invite re-sent to ${invited.email}. They must open the newest email link, set a password on /invite, then sign in.`,
        );
      } else if (invited.existing_auth_user) {
        setFormSuccess(
          `Linked existing Auth user ${invited.email} as member. A reset/invite email was sent so they can set or confirm their password, then sign in.`,
        );
      } else {
        setFormSuccess(
          `Invite sent to ${invited.email}. They must open the email link, set a password on /invite, then they can sign in with that email + password.`,
        );
      }
      await mutate();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Invite failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Members"
        description="Invite teammates to this tenant. They share the same keys and data; only owners can invite."
      />

      {isOwner ? (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <form onSubmit={handleInvite} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <label htmlFor="invite-email" className="text-sm font-medium text-muted-foreground">
                  Email
                </label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <Button type="submit" disabled={submitting || !email.trim()}>
                <UserPlus className="mr-1.5 h-4 w-4" aria-hidden="true" />
                {submitting ? 'Inviting…' : 'Invite member'}
              </Button>
            </form>
            {formError ? <p className="text-sm text-destructive">{formError}</p> : null}
            {formSuccess ? <p className="text-sm text-muted-foreground">{formSuccess}</p> : null}
            <p className="text-xs text-muted-foreground">
              Invites are scoped to your tenant automatically. The browser never chooses a tenant id.
            </p>
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">
          Only the workspace owner can invite new members.
        </p>
      )}

      <Card>
        <CardContent className="pt-6">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : error && !isPortalAuthFailure(error) ? (
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : 'Failed to load members'}
            </p>
          ) : error && isPortalAuthFailure(error) ? (
            <p className="text-sm text-muted-foreground">Redirecting to sign in…</p>
          ) : !members || members.length === 0 ? (
            <EmptyState
              title="No members yet"
              description="You should appear here as owner after signing in."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Email</th>
                    <th className="pb-2 pr-4 font-medium">Role</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.auth_user_id} className="border-b border-border/60">
                      <td className="py-3 pr-4 text-foreground">{m.email || '—'}</td>
                      <td className="py-3 pr-4">
                        <Badge variant="outline">{m.role}</Badge>
                      </td>
                      <td className="py-3">
                        <Badge variant="secondary">{m.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
