'use client';

import React, { useEffect, useState } from 'react';

import { type PortalSession, getSessions } from '@/lib/portalApi';

function formatDuration(durationSec: number | null) {
  if (durationSec === null || durationSec === undefined) {
    return 'Unknown';
  }

  const minutes = Math.floor(durationSec / 60);
  const seconds = durationSec % 60;
  return `${minutes} min ${seconds} sec`;
}

function formatTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return 'Unknown';
  }

  return new Date(timestamp).toLocaleString();
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<PortalSession[]>([]);
  const [activeSession, setActiveSession] = useState<PortalSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await getSessions();
        setSessions(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load sessions');
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

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

      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '0.5rem' }}>Recent Voice Sessions</h2>
        <p
          style={{
            color: 'var(--text-muted)',
            fontSize: '0.95rem',
            marginBottom: '1.5rem',
          }}
        >
          Historical record of completed WebRTC calls. Click a row to inspect
          the session details currently exposed by the tenant API.
        </p>

        <table className="data-table">
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Room Name</th>
              <th>Agent</th>
              <th>Duration</th>
              <th>End Reason</th>
              <th>Started At</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7}>Loading sessions...</td>
              </tr>
            )}
            {!loading && sessions.length === 0 && (
              <tr>
                <td colSpan={7}>No recent sessions found.</td>
              </tr>
            )}
            {sessions.map((session) => (
              <tr
                key={session.id}
                onClick={() => setActiveSession(session)}
                style={{ cursor: 'pointer' }}
              >
                <td style={{ fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                  {session.id}
                </td>
                <td style={{ fontFamily: 'monospace' }}>{session.room_name}</td>
                <td>{session.agent_name}</td>
                <td>{formatDuration(session.duration_sec)}</td>
                <td>
                  <span className="badge badge-green">
                    {session.end_reason ?? 'unknown'}
                  </span>
                </td>
                <td style={{ color: 'var(--text-muted)' }}>
                  {formatTimestamp(session.started_at)}
                </td>
                <td>
                  <button
                    className="btn-secondary"
                    style={{ padding: '0.3rem 0.65rem', fontSize: '0.75rem' }}
                  >
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {activeSession && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div className="glass-card" style={{ width: '600px', background: '#0b1120' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
              }}
            >
              <div>
                <h2>Session Details: {activeSession.id}</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {formatTimestamp(activeSession.started_at)}
                </div>
              </div>
              <button
                onClick={() => setActiveSession(null)}
                className="btn-secondary"
                style={{ padding: '0.3rem 0.65rem' }}
              >
                Close
              </button>
            </div>

            <div
              style={{
                background: 'rgba(0,0,0,0.4)',
                padding: '1rem',
                borderRadius: 'var(--radius-md)',
                maxHeight: '300px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.75rem',
              }}
            >
              <div><strong>Agent:</strong> {activeSession.agent_name}</div>
              <div><strong>Agent ID:</strong> {activeSession.agent_id}</div>
              <div><strong>Room:</strong> {activeSession.room_name}</div>
              <div><strong>Started:</strong> {formatTimestamp(activeSession.started_at)}</div>
              <div><strong>Ended:</strong> {formatTimestamp(activeSession.ended_at)}</div>
              <div><strong>Duration:</strong> {formatDuration(activeSession.duration_sec)}</div>
              <div><strong>End reason:</strong> {activeSession.end_reason ?? 'unknown'}</div>
              <div style={{ color: 'var(--text-muted)' }}>
                Transcript text is not exposed by the current tenant portal API yet.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
