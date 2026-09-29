'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import ConsoleNav from '@/components/ConsoleNav';
import { ensurePortalSession, getStoredValidTenantToken } from '@/lib/portalAuth';

const PUBLIC_AUTH_ROUTES = new Set(['/login', '/invite', '/claim']);

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [checkedAuth, setCheckedAuth] = useState(false);
  const isPublicAuthRoute = PUBLIC_AUTH_ROUTES.has(pathname);

  useEffect(() => {
    if (typeof window !== 'undefined' && pathname !== '/invite') {
      const hash = window.location.hash || '';
      const search = window.location.search || '';
      const inviteLanding =
        hash.includes('type=invite') ||
        hash.includes('type=recovery') ||
        hash.includes('access_token=') ||
        search.includes('code=') ||
        search.includes('type=invite') ||
        search.includes('type=recovery');
      if (inviteLanding) {
        window.location.replace(`/invite${search}${hash}`);
        return;
      }
    }

    let cancelled = false;

    (async () => {
      if (isPublicAuthRoute) {
        if (pathname === '/login' && getStoredValidTenantToken()) {
          router.replace('/');
          return;
        }
        if (!cancelled) {
          setCheckedAuth(true);
        }
        return;
      }

      const token = await ensurePortalSession();
      if (cancelled) {
        return;
      }
      if (!token) {
        router.replace('/login');
        return;
      }
      setCheckedAuth(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router, isPublicAuthRoute]);

  if (!checkedAuth && !isPublicAuthRoute) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg font-sans text-text-body">
        Checking session…
      </div>
    );
  }

  if (isPublicAuthRoute) {
    return <>{children}</>;
  }

  const isDocs = pathname === '/docs' || pathname.startsWith('/docs/');

  return (
    <div className="min-h-screen bg-bg text-text">
      <ConsoleNav />
      <main
        className={
          isDocs
            ? 'mx-auto w-full max-w-[1280px] px-6 pb-16 pt-[120px]'
            : 'mx-auto w-full max-w-console px-6 pb-16 pt-[120px]'
        }
      >
        {children}
      </main>
    </div>
  );
}
