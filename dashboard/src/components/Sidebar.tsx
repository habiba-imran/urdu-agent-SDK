'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { LayoutDashboard, Bot, KeyRound, PhoneCall, BarChart3, LogOut } from 'lucide-react';

import { cn } from '@/lib/utils';
import { clearStoredTenantToken } from '@/lib/portalAuth';

const navItems = [
  { href: '/', label: 'Overview', icon: LayoutDashboard },
  { href: '/agents', label: 'Agents & Voices', icon: Bot },
  { href: '/usage', label: 'Usage', icon: BarChart3 },
  { href: '/credentials', label: 'Credentials', icon: KeyRound },
  { href: '/sessions', label: 'Call Sessions', icon: PhoneCall },
];

/**
 * Nav content only — no wrapping `<aside>` — so it can be rendered inside the persistent
 * desktop sidebar AND inside the mobile slide-over overlay without duplicating markup.
 * `onNavigate` is used by the mobile overlay to close itself when a link is followed.
 */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    clearStoredTenantToken();
    router.replace('/login');
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center border-b border-border px-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">AwaazLabs</p>
          <p className="truncate text-xs text-muted-foreground">Tenant Portal</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4" aria-label="Main navigation">
        <div className="flex flex-col gap-0.5">
          {navItems.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                onClick={onNavigate}
                className={cn(
                  'flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-accent',
                  active && 'bg-accent font-medium text-accent-foreground',
                )}
              >
                <Icon
                  className={cn('h-4 w-4 shrink-0', active ? 'text-foreground' : 'text-muted-foreground')}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={handleLogout}
          className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Log Out
        </button>
      </div>
    </div>
  );
}

/** Persistent desktop sidebar — hidden below `md`, where `AppShell`'s mobile overlay takes over. */
export default function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r border-border bg-card md:flex">
      <SidebarNav />
    </aside>
  );
}
