'use client';

import React, { useEffect, useState } from 'react';

import { type PortalCredentials, getCredentials } from '@/lib/portalApi';

export default function CredentialsPage() {
  const [copiedKey, setCopiedKey] = useState(false);
  const [credentials, setCredentials] = useState<PortalCredentials | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await getCredentials();
        setCredentials(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load credentials');
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  const handleCopyKey = () => {
    if (!credentials?.publishable_key) {
      return;
    }
    navigator.clipboard.writeText(credentials.publishable_key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2500);
  };

  return (
    <div style={{ maxWidth: '950px' }}>
      {error && (
        <div
          className="glass-card"
          style={{
            marginBottom: '1.5rem',
            border: '1px solid rgba(248, 113, 113, 0.35)',
            color: '#fca5a5',
          }}
        >
          <strong>Backend connection error:</strong> {error}
        </div>
      )}

      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '0.5rem' }}>
          Tenant API Credentials & Trust Boundaries
        </h2>
        <p
          style={{
            color: 'var(--text-muted)',
            fontSize: '0.95rem',
            marginBottom: '1.5rem',
          }}
        >
          Use these credentials in your host server (Node.js/Python) to sign
          HMAC session tokens for browser clients.
        </p>

        <div style={{ marginBottom: '1.5rem' }}>
          <label
            style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--text-muted)',
              marginBottom: '0.4rem',
              fontWeight: 600,
            }}
          >
            PUBLISHABLE KEY (Safe to embed in browser clients)
          </label>
          <div
            style={{
              background: 'rgba(0,0,0,0.4)',
              padding: '0.9rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-card)',
              fontFamily: 'monospace',
              color: 'var(--accent-cyan)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{loading ? 'Loading...' : credentials?.publishable_key ?? 'Unavailable'}</span>
            <button
              onClick={handleCopyKey}
              className="btn-secondary"
              style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}
            >
              {copiedKey ? 'Copied!' : 'Copy Key'}
            </button>
          </div>
        </div>

        <div>
          <label
            style={{
              display: 'block',
              fontSize: '0.85rem',
              color: 'var(--text-muted)',
              marginBottom: '0.4rem',
              fontWeight: 600,
            }}
          >
            SECRET HMAC KEY (Masked - Host Server Only)
          </label>
          <div
            style={{
              background: 'rgba(0,0,0,0.4)',
              padding: '0.9rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-card)',
              fontFamily: 'monospace',
              color: 'var(--text-dim)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{loading ? 'Loading...' : credentials?.secret_masked ?? 'Unavailable'}</span>
            <span className="badge badge-purple">
              {loading ? '...' : credentials?.status ?? 'Unknown'}
            </span>
          </div>
          <p
            style={{
              fontSize: '0.8rem',
              color: 'var(--text-dim)',
              marginTop: '0.5rem',
            }}
          >
            Secrets are never returned via GET API queries. To issue a new
            secret, request secret rotation from your administrator.
          </p>
        </div>

        <div style={{ marginTop: '1.25rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <div>Tenant ID: {loading ? 'Loading...' : credentials?.tenant_id ?? 'Unavailable'}</div>
          <div>Tenant Name: {loading ? 'Loading...' : credentials?.name ?? 'Unavailable'}</div>
          <div>
            Allowed Origins:{' '}
            {loading
              ? 'Loading...'
              : credentials?.allowed_origins?.length
                ? credentials.allowed_origins.join(', ')
                : 'None configured'}
          </div>
        </div>
      </div>

      <div className="glass-card">
        <h2 style={{ marginBottom: '1rem' }}>
          Host Backend Signing Snippet (Node.js Express)
        </h2>
        <div
          style={{
            background: '#0b1120',
            padding: '1.25rem',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.85rem',
            fontFamily: 'monospace',
            color: '#e2e8f0',
            lineHeight: '1.6',
          }}
        >
          <div style={{ color: '#64748b' }}>
            // Node.js signing logic per HOST_BACKEND_CONTRACT.md
          </div>
          <div style={{ color: '#f472b6' }}>import crypto from 'crypto';</div>
          <br />
          <div>function signSession(tenantId, secret, timestamp, nonce, agentId) {'{'}</div>
          <div style={{ color: '#34d399' }}>
            &nbsp;&nbsp;const payload = `{'${tenantId}.${timestamp}.${nonce}.${agentId}'}`;
          </div>
          <div>
            &nbsp;&nbsp;return crypto.createHmac('sha256', secret).update(payload).digest('hex');
          </div>
          <div>{'}'}</div>
        </div>
      </div>
    </div>
  );
}
