'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

import {
  PortalAuthError,
  loginTenantPortal,
  setStoredTenantToken,
} from '@/lib/portalAuth';

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
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background:
          'radial-gradient(circle at top, rgba(16,185,129,0.18), transparent 32%), #07111d',
        padding: '2rem',
      }}
    >
      <div
        className="glass-card"
        style={{ width: '100%', maxWidth: '480px', padding: '2rem' }}
      >
        <div style={{ marginBottom: '1.5rem' }}>
          <h1 style={{ marginBottom: '0.5rem' }}>Tenant Portal Login</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            Sign in with your tenant ID and tenant secret.
          </p>
        </div>

        {error && (
          <div
            style={{
              marginBottom: '1rem',
              border: '1px solid rgba(248, 113, 113, 0.35)',
              color: '#fca5a5',
              borderRadius: '12px',
              padding: '0.9rem 1rem',
              background: 'rgba(248, 113, 113, 0.08)',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label
              style={{
                display: 'block',
                marginBottom: '0.4rem',
                color: 'var(--text-muted)',
                fontSize: '0.9rem',
              }}
            >
              Tenant ID
            </label>
            <input
              type="text"
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.85rem 1rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-card)',
                borderRadius: '12px',
                color: '#fff',
              }}
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label
              style={{
                display: 'block',
                marginBottom: '0.4rem',
                color: 'var(--text-muted)',
                fontSize: '0.9rem',
              }}
            >
              Tenant Secret
            </label>
            <input
              type="password"
              value={tenantSecret}
              onChange={(event) => setTenantSecret(event.target.value)}
              required
              style={{
                width: '100%',
                padding: '0.85rem 1rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-card)',
                borderRadius: '12px',
                color: '#fff',
              }}
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={submitting}
            style={{ width: '100%' }}
          >
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
