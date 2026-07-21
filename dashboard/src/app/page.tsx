'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';

import {
  type PortalAgent,
  type PortalCredentials,
  type PortalUsageSummary,
  getAgents,
  getCredentials,
  getUsageSummary,
} from '@/lib/portalApi';

export default function DashboardPage() {
  const [agents, setAgents] = useState<PortalAgent[]>([]);
  const [credentials, setCredentials] = useState<PortalCredentials | null>(null);
  const [usage, setUsage] = useState<PortalUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [agentsData, credentialsData, usageData] = await Promise.all([
          getAgents(),
          getCredentials(),
          getUsageSummary(),
        ]);
        setAgents(agentsData);
        setCredentials(credentialsData);
        setUsage(usageData);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  const concurrentNow = usage?.quota.concurrent_now ?? 0;
  const maxConcurrent = usage?.quota.max_concurrent ?? 0;
  const usedMinutes = usage?.quota.minutes_this_month ?? 0;
  const monthlyCap = usage?.quota.max_minutes_month ?? 0;

  return (
    <div>
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

      <div className="grid-3">
        <div className="glass-card">
          <div className="stat-header">
            <span>ACTIVE AGENTS</span>
            <span className="badge badge-green">Live</span>
          </div>
          <div className="stat-value">{loading ? '...' : agents.length}</div>
          <div className="stat-subtext">Configured Urdu Voice Assistants</div>
        </div>

        <div className="glass-card">
          <div className="stat-header">
            <span>CONCURRENT CALLS</span>
            <span className="badge badge-blue">
              Quota: {loading ? '...' : maxConcurrent}
            </span>
          </div>
          <div className="stat-value">
            {loading ? '...' : `${concurrentNow} / ${maxConcurrent}`}
          </div>
          <div className="stat-subtext">Active LiveKit WebRTC sessions</div>
        </div>

        <div className="glass-card">
          <div className="stat-header">
            <span>MONTHLY USAGE</span>
            <span className="badge badge-purple">
              {loading ? '...' : `${monthlyCap} min cap`}
            </span>
          </div>
          <div className="stat-value">
            {loading ? '...' : `${usedMinutes.toFixed(1)} min`}
          </div>
          <div className="stat-subtext">Agent minutes consumed this period</div>
        </div>
      </div>

      <div className="grid-3" style={{ gridTemplateColumns: '2fr 1fr' }}>
        <div className="glass-card">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1.25rem',
            }}
          >
            <h2>Configured Voice Agents</h2>
            <Link href="/agents" className="btn-primary">
              + New Agent
            </Link>
          </div>

          <table className="data-table">
            <thead>
              <tr>
                <th>Agent Name</th>
                <th>Selected Voice</th>
                <th>LLM Engine</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={4}>Loading agents...</td>
                </tr>
              )}
              {!loading && agents.length === 0 && (
                <tr>
                  <td colSpan={4}>No agents found for this tenant.</td>
                </tr>
              )}
              {!loading &&
                agents.map((agent) => (
                  <tr key={agent.id}>
                    <td style={{ fontWeight: 600 }}>{agent.name}</td>
                    <td>
                      <span className="badge badge-green">{agent.voice_id}</span>
                    </td>
                    <td>{agent.llm_model}</td>
                    <td>
                      <span className="badge badge-green">Active</span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <div className="glass-card">
          <h2 style={{ marginBottom: '1rem' }}>Integration Specs</h2>
          <p
            style={{
              color: 'var(--text-muted)',
              fontSize: '0.9rem',
              marginBottom: '1rem',
              lineHeight: '1.5',
            }}
          >
            Your host backend signs HMAC tokens using your assigned secret key
            before dispatching client WebRTC sessions.
          </p>

          <div
            style={{
              background: 'rgba(0,0,0,0.3)',
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
            }}
          >
            <div style={{ color: 'var(--text-dim)', marginBottom: '0.4rem' }}>
              PUBLISHABLE KEY
            </div>
            <div
              style={{
                fontFamily: 'monospace',
                color: 'var(--accent-cyan)',
                wordBreak: 'break-all',
              }}
            >
              {loading ? 'Loading...' : credentials?.publishable_key ?? 'Unavailable'}
            </div>
          </div>

          <Link
            href="/credentials"
            className="btn-secondary"
            style={{
              width: '100%',
              marginTop: '1rem',
              display: 'block',
              textAlign: 'center',
            }}
          >
            View Full Credentials
          </Link>
        </div>
      </div>
    </div>
  );
}
