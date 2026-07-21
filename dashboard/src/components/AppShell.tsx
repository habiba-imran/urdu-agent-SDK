'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import Sidebar from '@/components/Sidebar';
import { getStoredTenantToken } from '@/lib/portalAuth';

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [checkedAuth, setCheckedAuth] = useState(false);

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

  if (!checkedAuth && pathname !== '/login') {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#07111d',
          color: '#dbeafe',
        }}
      >
        Checking tenant session...
      </div>
    );
  }

  if (pathname === '/login') {
    return <>{children}</>;
  }

  return (
    <div className="app-container">
      <Sidebar />
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
  );
}
