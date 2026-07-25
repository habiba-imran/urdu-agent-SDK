'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { preload } from 'swr';
import { LayoutDashboard, Bot, KeyRound, PhoneCall, BarChart3, LogOut } from 'lucide-react';

import { cn } from '@/lib/utils';
import { clearStoredTenantToken } from '@/lib/portalAuth';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';

const navItems = [
  {
    href: '/',
    label: 'Overview',
    icon: LayoutDashboard,
    prefetch: ['agents', 'credentials', 'usage', 'sessions'] as const,
  },
  { href: '/agents', label: 'Agents & Voices', icon: Bot, prefetch: ['agents', 'voices'] as const },
  { href: '/usage', label: 'Usage', icon: BarChart3, prefetch: ['usage'] as const },
  { href: '/credentials', label: 'Credentials', icon: KeyRound, prefetch: ['credentials'] as const },
  { href: '/sessions', label: 'Call Sessions', icon: PhoneCall, prefetch: ['sessions'] as const },
];

/** Warms SWR's global cache for a route's data before the user actually navigates there,
 *  so the page renders from cache instantly instead of showing a skeleton. Safe to call
 *  repeatedly — SWR dedupes concurrent/duplicate requests for the same key on its own. */
function prefetchRouteData(keys: readonly (keyof typeof swrKeys)[]) {
  for (const key of keys) {
    void preload(swrKeys[key], swrFetchers[key]);
  }
}

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
                onMouseEnter={() => prefetchRouteData(item.prefetch)}
                onFocus={() => prefetchRouteData(item.prefetch)}
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
