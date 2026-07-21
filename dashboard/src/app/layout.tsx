import './globals.css';
import React from 'react';
import Sidebar from '@/components/Sidebar';

export const metadata = {
  title: 'Urdu VaaS — Tenant Dashboard',
  description: 'Self-service management portal for Urdu Voice-Agent-as-a-Service',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="app-container">
          {/* Dynamic Active Link Sidebar */}
          <Sidebar />

          {/* Main Content Area */}
          <main className="main-content">
            <header className="header-bar">
              <div className="header-title">
                <h1>Tenant Operations Center</h1>
                <p>Manage your Urdu voice agents, credentials, and real-time usage quotas.</p>
              </div>

              <div className="status-chip">
                <span className="pulse-dot"></span>
                <span>Active Tenant</span>
              </div>
            </header>

            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
