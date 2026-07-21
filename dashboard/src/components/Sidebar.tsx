'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { clearStoredTenantToken } from '@/lib/portalAuth';

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const navItems = [
    {
      href: '/',
      label: 'Overview',
      icon: (
        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    {
      href: '/agents',
      label: 'Agents & Voices',
      icon: (
        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 100-6 3 3 0 000 6z" />
        </svg>
      ),
    },
    {
      href: '/credentials',
      label: 'Credentials',
      icon: (
        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
        </svg>
      ),
    },
    {
      href: '/sessions',
      label: 'Call Sessions',
      icon: (
        <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
  ];

  const handleLogout = () => {
    clearStoredTenantToken();
    router.replace('/login');
  };

  return (
    <aside className="sidebar">
      <div className="logo-box">
        <div className="logo-badge">U</div>
        <div>
          <div className="logo-text">Urdu VaaS</div>
          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>Tenant Portal</div>
        </div>
      </div>

      <nav>
        <ul className="nav-list">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <li key={item.href}>
                <Link href={item.href} className={`nav-link ${isActive ? 'active' : ''}`}>
                  {item.icon}
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <button
        onClick={handleLogout}
        className="btn-secondary"
        style={{ marginTop: 'auto', width: '100%' }}
      >
        Log Out
      </button>
    </aside>
  );
}
