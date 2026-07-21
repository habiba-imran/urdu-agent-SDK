'use client';

import React, { useState } from 'react';

export default function CredentialsPage() {
  const [copiedKey, setCopiedKey] = useState(false);

  const handleCopyKey = () => {
    navigator.clipboard.writeText('15e96da6-6b75-4a28-bd7b-ac018986368d');
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2500);
  };

  return (
    <div style={{ maxWidth: '950px' }}>
      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '0.5rem' }}>Tenant API Credentials & Trust Boundaries</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', marginBottom: '1.5rem' }}>
          Use these credentials in your host server (Node.js/Python) to sign HMAC session tokens for browser clients.
        </p>

        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.4rem', fontWeight: 600 }}>
            PUBLISHABLE KEY (Safe to embed in browser clients)
          </label>
          <div style={{
            background: 'rgba(0,0,0,0.4)', padding: '0.9rem', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-card)', fontFamily: 'monospace', color: 'var(--accent-cyan)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center'
          }}>
            <span>15e96da6-6b75-4a28-bd7b-ac018986368d</span>
            <button onClick={handleCopyKey} className="btn-secondary" style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
              {copiedKey ? '✓ Copied!' : '📋 Copy Key'}
            </button>
          </div>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.4rem', fontWeight: 600 }}>
            SECRET HMAC KEY (Masked - Host Server Only)
          </label>
          <div style={{
            background: 'rgba(0,0,0,0.4)', padding: '0.9rem', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-card)', fontFamily: 'monospace', color: 'var(--text-dim)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center'
          }}>
            <span>••••••••••••••••••••••••••••••••</span>
            <span className="badge badge-purple">Stored in DB</span>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.5rem' }}>
            Secrets are never returned via GET API queries. To issue a new secret, request secret rotation from your administrator.
          </p>
        </div>
      </div>

      <div className="glass-card">
        <h2 style={{ marginBottom: '1rem' }}>Host Backend Signing Snippet (Node.js Express)</h2>
        <div style={{ background: '#0b1120', padding: '1.25rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', fontFamily: 'monospace', color: '#e2e8f0', lineHeight: '1.6' }}>
          <div style={{ color: '#64748b' }}>// Node.js signing logic per HOST_BACKEND_CONTRACT.md</div>
          <div style={{ color: '#f472b6' }}>import crypto from &apos;crypto&apos;;</div>
          <br />
          <div>function signSession(tenantId, secret, timestamp, nonce, agentId) &#123;</div>
          <div style={{ color: '#34d399' }}>&nbsp;&nbsp;const payload = `$&#123;tenantId&#125;.$&#123;timestamp&#125;.$&#123;nonce&#125;.$&#123;agentId&#125;`;</div>
          <div>&nbsp;&nbsp;return crypto.createHmac(&apos;sha256&apos;, secret).update(payload).digest(&apos;hex&apos;);</div>
          <div>&#125;</div>
        </div>
      </div>
    </div>
  );
}
