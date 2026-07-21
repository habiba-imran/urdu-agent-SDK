import './globals.css';
import React from 'react';
import AppShell from '@/components/AppShell';

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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
