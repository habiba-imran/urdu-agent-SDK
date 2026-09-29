-- 0033_tenant_secret_encryption.sql
-- F-C6 (audit §9): tenants.hmac_secret held the raw HMAC signing credential in plaintext,
-- while 0001_schema.sql:27, control_plane/secrets.py:3-5 and docs/21-PHASE-1-SUPABASE.md:12
-- all still asserted "hash ONLY, never the secret". A database dump was every tenant's
-- permanent signing credential.
--
-- This cannot become a hash: the value has to be handed back to the host that signs with it,
-- so it is encryption (control_plane/secret_crypto.py, AES-256-GCM + HKDF), not digesting.
--
-- Rollout is deliberately two-phase so minting never stops:
--   1. This migration adds the column. Nothing reads it yet that cannot fall back.
--   2. scripts/encrypt_tenant_secrets.py fills it, and with --finalize clears the plaintext
--      column once every row has a ciphertext.
-- Readers (control_plane/secrets_db.py) prefer hmac_secret_enc and fall back to hmac_secret,
-- so a half-migrated database, or a service that has not been given the key yet, keeps
-- working.

alter table tenants
  add column if not exists hmac_secret_enc text;

comment on column tenants.hmac_secret_enc is
  'F-C6: tenant HMAC signing secret, encrypted with TENANT_SECRET_ENCRYPTION_KEY (control_plane/secret_crypto.py). Replaces the plaintext hmac_secret column.';

comment on column tenants.hmac_secret is
  'DEPRECATED (F-C6): plaintext signing secret. Kept only for rollout; scripts/encrypt_tenant_secrets.py --finalize clears it once hmac_secret_enc is populated.';

-- hmac_secret_hash predates all of this and is vestigial: the mint compares against the raw
-- secret, never this column (F-L9 removed the dead SELECT of it). Left in place rather than
-- dropped, because dropping a column is not reversible and nothing is harmed by it existing.
comment on column tenants.hmac_secret_hash is
  'Vestigial: no code verifies against this (see F-L9). Retained only so this migration stays non-destructive.';
