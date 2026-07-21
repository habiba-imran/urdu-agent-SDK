'use client';

import React, { useState } from 'react';

type SessionRow = {
  id: string;
  roomName: string;
  agentId: string;
  duration: string;
  reason: string;
  startedAt: string;
  transcript: { speaker: string; text: string }[];
};

const SESSIONS_DATA: SessionRow[] = [
  {
    id: 'sess-9f8a2b1c3d4e',
    roomName: 'uva-15e96da6-1774135200',
    agentId: '3b5b7720-4cce',
    duration: '2 min 45 sec',
    reason: 'client_hangup',
    startedAt: '2026-07-21 22:15:00 UTC',
    transcript: [
      { speaker: 'Caller', text: 'السلام علیکم! مجھے برائے مہربانی پیکیج کی معلومات چاہیے۔' },
      { speaker: 'Urdu Agent', text: 'وعلیکم السلام! میں آپ کی بالکل مدد کر سکتا ہوں۔ ہمارے پاس تین پیکیجز دستیاب ہیں۔' },
      { speaker: 'Caller', text: 'بہت شکریہ، حافظ صاحب!' },
    ],
  },
  {
    id: 'sess-8e7d6c5b4a3f',
    roomName: 'uva-15e96da6-1774134800',
    agentId: '3b5b7720-4cce',
    duration: '4 min 12 sec',
    reason: 'client_hangup',
    startedAt: '2026-07-21 21:40:00 UTC',
    transcript: [
      { speaker: 'Caller', text: 'آرڈر کی تفصیلات چیک کر دیں۔' },
      { speaker: 'Urdu Agent', text: 'جی بالکل! اپنا آرڈر نمبر بتائیے۔' },
    ],
  },
  {
    id: 'sess-7d6c5b4a3f2e',
    roomName: 'uva-15e96da6-1774131200',
    agentId: '3b5b7720-4cce',
    duration: '1 min 05 sec',
    reason: 'inactivity_timeout',
    startedAt: '2026-07-21 20:10:00 UTC',
    transcript: [
      { speaker: 'Urdu Agent', text: 'کیا آپ مجھے سن سکتے ہیں؟' },
    ],
  },
];

export default function SessionsPage() {
  const [activeSession, setActiveSession] = useState<SessionRow | null>(null);

  return (
    <div>
      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <h2 style={{ marginBottom: '0.5rem' }}>Recent Voice Sessions & Transcript Logs</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', marginBottom: '1.5rem' }}>
          Historical record of completed WebRTC calls. Click any session row to inspect transcript dialogue.
        </p>

        <table className="data-table">
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Room Name</th>
              <th>Agent ID</th>
              <th>Duration</th>
              <th>End Reason</th>
              <th>Started At</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {SESSIONS_DATA.map((s) => (
              <tr key={s.id} onClick={() => setActiveSession(s)} style={{ cursor: 'pointer' }}>
                <td style={{ fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>{s.id}</td>
                <td style={{ fontFamily: 'monospace' }}>{s.roomName}</td>
                <td>{s.agentId}</td>
                <td>{s.duration}</td>
                <td><span className="badge badge-green">{s.reason}</span></td>
                <td style={{ color: 'var(--text-muted)' }}>{s.startedAt}</td>
                <td>
                  <button className="btn-secondary" style={{ padding: '0.3rem 0.65rem', fontSize: '0.75rem' }}>
                    View Transcript
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Transcript Drawer Modal */}
      {activeSession && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(8px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100
        }}>
          <div className="glass-card" style={{ width: '600px', background: '#0b1120' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h2>Session Transcript: {activeSession.id}</h2>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{activeSession.startedAt}</div>
              </div>
              <button onClick={() => setActiveSession(null)} className="btn-secondary" style={{ padding: '0.3rem 0.65rem' }}>
                ✕ Close
              </button>
            </div>

            <div style={{
              background: 'rgba(0,0,0,0.4)', padding: '1rem', borderRadius: 'var(--radius-md)',
              maxHeight: '300px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.75rem'
            }}>
              {activeSession.transcript.map((msg, idx) => (
                <div key={idx} style={{
                  padding: '0.75rem', borderRadius: '8px',
                  background: msg.speaker === 'Caller' ? 'rgba(6, 182, 212, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                  border: `1px solid ${msg.speaker === 'Caller' ? 'rgba(6, 182, 212, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
                  direction: 'rtl', textAlign: 'right'
                }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.2rem', direction: 'ltr', textAlign: 'left' }}>
                    {msg.speaker}
                  </div>
                  <div style={{ fontSize: '1rem', color: '#fff' }}>
                    {msg.text}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
