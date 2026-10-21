# Members and invitation audit

The dashboard now supports one account in several workspaces, with an independent role and publishable-key permission in each workspace. The account menu provides workspace selection.

## Findings addressed

- Both the database's global `auth_user_id` uniqueness constraint and the invitation helper enforced one tenant per user. The new migration makes `(tenant_id, auth_user_id)` unique instead.
- Live authorization used the first membership it found. Every authorization lookup now selects the token's tenant explicitly. Selecting a tenant at login or from an invite link must pass the verified Auth user's membership check.
- Login activated every pending membership for a user. It now activates only the selected workspace. Inviting and claiming a workspace preserve previous memberships.
- HMAC reveal previously honored the member's API-key toggle. It now requires the workspace owner role, even when the publishable-key toggle is enabled. Credentials and overview responses continue to strip raw, encrypted, and hashed HMAC values.
- New member publishable-key access defaults to off. Owners alone can grant or revoke it, scoped to their own workspace. Live permission checks override stale token claims.
- Existing Auth users beyond the first 1,000 accounts could be missed. Lookup now continues through the project-wide Auth user list.
- Invite and recovery emails carry the inviting workspace into the accept page. Pending invitations can be resent; active duplicate memberships return a clear conflict.
- The table now reserves column and switch-label widths across saving/on/off states. Notifications appear at the bottom-right. Stable scrollbar space prevents page-width shifts.
- Workspace switches, sign-in, sign-out, and claim completion reload the document so previous account/workspace SWR data and revealed-secret state are discarded.

## Key visibility

| Capability | Owner | Member, toggle off | Member, toggle on |
| --- | --- | --- | --- |
| Publishable-key field | Visible | Hidden | Visible |
| HMAC reveal endpoint | Allowed if deployment enables it | 403 | 403 |
| HMAC UI / backend env export | Available | Hidden | Hidden |
| Invite / change permissions / origins | Allowed | 403 | 403 |

The publishable key currently equals the tenant UUID and is intentionally public identification. The visibility toggle does not make that identifier secret or revoke previously copied values. HMAC is the actual signing credential. Previously disclosed HMAC secrets require operator rotation to invalidate; this change does not rotate credentials.

## Verification

- All 16 focused HTTP authorization and multi-workspace tests pass, including real Postgres SQL against temporary tables, using `default_transaction_read_only=on` for permanent data. No real invitations were sent.
- Browser checks with mocked API responses cover stable table geometry while saving/on/off, bottom-right notifications, invite success and duplicate errors, workspace switching, member key restrictions, and 375px page overflow.
- Dashboard typecheck and production build pass.
- `graphify update .` was attempted; the installed launcher fails with `uv trampoline failed to canonicalize script path`. No graph existed at the start of this task.

## Deployment and remaining live checks

A read-only check of the configured database confirmed that `tenant_members_auth_user_unique` is still applied. The new migration has not been applied to permanent tables.

1. Apply `supabase/migrations/20261020220225_multi_tenant_memberships.sql` to the target database through the normal migration workflow before enabling the new API. The earlier member-key-access migration must already be applied.
2. Deploy the tenant portal API and dashboard together.
3. Ensure Supabase Auth Redirect URLs accepts the dashboard invite path with the `tenant_id` query. A scoped pattern such as `https://<dashboard-host>/invite*` supports the generated links. Verify custom email templates honor `redirectTo`; see [Supabase redirect documentation](https://supabase.com/docs/guides/auth/redirect-urls).
4. Exercise one real new-account invitation and one existing-account invitation, email delivery, acceptance, switching, and permission changes on the deployed target. These live email/deployment checks were not performed here.

Existing accounts continue to receive Supabase recovery emails, so completing that link changes their shared account password across workspaces. Membership creation and the external email send are separate effects: an email may be sent even if the database transaction later fails. Failed sends do not commit the membership; retries reuse the Auth identity. Guaranteed email/database atomicity would require a separate invitation outbox.
