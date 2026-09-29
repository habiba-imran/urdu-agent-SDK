import './globals.css';
import React from 'react';
import AppShell from '@/components/AppShell';
import { SwrProvider } from '@/components/SwrProvider';

export const metadata = {
  title: 'Awaaz Labs Console',
  description: 'Developer console for agents, phone, sessions, and API keys',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <SwrProvider>
          <AppShell>{children}</AppShell>
        </SwrProvider>
      </body>
    </html>
  );
}
