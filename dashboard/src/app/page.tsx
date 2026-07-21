import React from 'react';
import Link from 'next/link';

export default function DashboardPage() {
  return (
    <div>
      {/* Overview Metric Cards */}
      <div className="grid-3">
        <div className="glass-card">
          <div className="stat-header">
            <span>ACTIVE AGENTS</span>
            <span className="badge badge-green">Live</span>
          </div>
          <div className="stat-value">3</div>
          <div className="stat-subtext">Configured Urdu Voice Assistants</div>
        </div>

        <div className="glass-card">
          <div className="stat-header">
            <span>CONCURRENT CALLS</span>
            <span className="badge badge-blue">Quota: 5</span>
          </div>
          <div className="stat-value">0 / 5</div>
          <div className="stat-subtext">Active LiveKit WebRTC sessions</div>
        </div>

        <div className="glass-card">
          <div className="stat-header">
            <span>MONTHLY USAGE</span>
            <span className="badge badge-purple">1,000 min cap</span>
          </div>
          <div className="stat-value">48.5 min</div>
          <div className="stat-subtext">Agent minutes consumed this period</div>
        </div>
      </div>

      {/* Quick Actions & Recent Sessions */}
      <div className="grid-3" style={{ gridTemplateColumns: '2fr 1fr' }}>
        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
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
              <tr>
                <td style={{ fontWeight: 600 }}>Customer Care Urdu Agent</td>
                <td><span className="badge badge-green">helpdesk-agent</span></td>
                <td>Gemini 1.5 Flash</td>
                <td><span className="badge badge-green">Active</span></td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>Sales Concierge</td>
                <td><span className="badge badge-blue">street-vendor</span></td>
                <td>Gemini 1.5 Flash</td>
                <td><span className="badge badge-green">Active</span></td>
              </tr>
              <tr>
                <td style={{ fontWeight: 600 }}>News Reader Agent</td>
                <td><span className="badge badge-purple">prime-time-anchor</span></td>
                <td>Gemini 1.5 Pro</td>
                <td><span className="badge badge-green">Active</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="glass-card">
          <h2 style={{ marginBottom: '1rem' }}>Integration Specs</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem', lineHeight: '1.5' }}>
            Your host backend signs HMAC tokens using your assigned secret key before dispatching client WebRTC sessions.
          </p>

          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '1rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem' }}>
            <div style={{ color: 'var(--text-dim)', marginBottom: '0.4rem' }}>PUBLISHABLE KEY</div>
            <div style={{ fontFamily: 'monospace', color: 'var(--accent-cyan)', wordBreak: 'break-all' }}>
              15e96da6-6b75-4a28-bd7b-ac018986368d
            </div>
          </div>

          <Link href="/credentials" className="btn-secondary" style={{ width: '100%', marginTop: '1rem', display: 'block', textAlign: 'center' }}>
            View Full Credentials
          </Link>

        </div>
      </div>
    </div>
  );
}
