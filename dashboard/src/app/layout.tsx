import './globals.css';
import React from 'react';
import { Inter, JetBrains_Mono } from 'next/font/google';
import AppShell from '@/components/AppShell';
import { SwrProvider } from '@/components/SwrProvider';

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
  display: 'swap',
});

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
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className={inter.className}>
        <SwrProvider>
          <AppShell>{children}</AppShell>
        </SwrProvider>
      </body>
    </html>
  );
}
