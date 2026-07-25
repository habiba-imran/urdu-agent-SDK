'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { Menu } from 'lucide-react';

import Sidebar, { SidebarNav } from '@/components/Sidebar';
import { getStoredTenantToken } from '@/lib/portalAuth';
import { useScrollLock } from '@/hooks/use-scroll-lock';

/** Slide-in nav overlay for narrow viewports — `Sidebar` itself is `hidden` below `md`. */
function MobileNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  useScrollLock(open);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <Dialog.Portal>
        <div aria-hidden="true" className="fixed inset-0 z-[100] bg-foreground/60 md:hidden" />
        <Dialog.Content
          className="fixed left-0 top-0 z-[100] flex h-dvh w-64 max-w-[80vw] flex-col border-r border-border bg-card shadow-lg md:hidden data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left"
        >
          <Dialog.Title className="sr-only">Main navigation</Dialog.Title>
          <SidebarNav onNavigate={() => onOpenChange(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    const token = getStoredTenantToken();
    const isLoginRoute = pathname === '/login';

    if (!token && !isLoginRoute) {
      router.replace('/login');
      return;
    }

    if (token && isLoginRoute) {
      router.replace('/');
      return;
    }

    setCheckedAuth(true);
  }, [pathname, router]);

  // A route change means a nav link was just followed — the overlay must not linger.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  if (!checkedAuth && pathname !== '/login') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
        Checking tenant session...
      </div>
    );
  }

  if (pathname === '/login') {
    return <>{children}</>;
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <Sidebar />
      <MobileNav open={mobileNavOpen} onOpenChange={setMobileNavOpen} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4 md:hidden">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open main navigation"
            className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:bg-accent"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <span className="text-sm font-semibold text-foreground">AwaazLabs</span>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-6 md:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
