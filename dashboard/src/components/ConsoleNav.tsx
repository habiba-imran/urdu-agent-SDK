'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { preload } from 'swr';
import { Menu, X } from 'lucide-react';

import { cn } from '@/lib/utils';
import { logoutPortalSession } from '@/lib/portalAuth';
import { swrKeys, swrFetchers } from '@/lib/swr-keys';
import { getSupabaseBrowserClient } from '@/lib/supabaseBrowser';

const navItems = [
  {
    href: '/',
    label: 'Overview',
    prefetch: ['overview'] as const,
  },
  {
    href: '/agents',
    label: 'Agents',
    prefetch: ['agents', 'telephonyNumbers'] as const,
  },
  { href: '/sessions', label: 'Sessions', prefetch: ['sessions'] as const },
  { href: '/usage', label: 'Usage', prefetch: ['usage'] as const },
  { href: '/credentials', label: 'API Keys', prefetch: ['credentials', 'agents'] as const },
  { href: '/members', label: 'Members', prefetch: ['members'] as const },
  { href: '/docs', label: 'Docs', prefetch: [] as const },
] as const;

function prefetchRouteData(keys: readonly (keyof typeof swrKeys)[] | undefined) {
  if (!keys?.length) return;
  for (const key of keys) {
    if (key in swrKeys && key in swrFetchers) {
      void preload(swrKeys[key], swrFetchers[key]);
    }
  }
}

function isActivePath(pathname: string, href: string) {
  return href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);
}

export default function ConsoleNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, top: 0, width: 0, height: 0, opacity: 0 });
  const navContainerRef = useRef<HTMLDivElement>(null);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  const updateIndicator = useCallback(() => {
    if (!navContainerRef.current) return;
    const activeLink = navContainerRef.current.querySelector('a[aria-current="page"]') as HTMLElement;
    if (activeLink) {
      setIndicatorStyle({
        left: activeLink.offsetLeft,
        top: activeLink.offsetTop,
        width: activeLink.offsetWidth,
        height: activeLink.offsetHeight,
        opacity: 1,
      });
    } else {
      setIndicatorStyle((prev) => ({ ...prev, opacity: 0 }));
    }
  }, []);

  useEffect(() => {
    setMenuOpen(false);
    setUserDropdownOpen(false);
  }, [pathname]);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const supabase = getSupabaseBrowserClient();
        const { data } = await supabase.auth.getUser();
        if (data?.user?.email) {
          setUserEmail(data.user.email);
        }
      } catch (err) {
        // ignore
      }
    };
    void fetchUser();
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target as Node)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    updateIndicator();
    
    let observer: ResizeObserver | null = null;
    if (typeof window !== 'undefined' && window.ResizeObserver && navContainerRef.current) {
      observer = new ResizeObserver(() => {
        window.requestAnimationFrame(() => {
          updateIndicator();
        });
      });
      observer.observe(navContainerRef.current);
    }
    
    return () => {
      if (observer) {
        observer.disconnect();
      }
    };
  }, [pathname, updateIndicator]);

  const handleLogout = () => {
    void logoutPortalSession().finally(() => {
      router.replace('/login');
    });
  };

  const getInitials = (email: string | null) => {
    if (!email) return 'U';
    const parts = email.split('@')[0].split(/[.\-_]/);
    if (parts.length > 1) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return email.substring(0, 2).toUpperCase();
  };

  return (
    <header 
      className="pointer-events-none fixed left-0 top-4 z-[100] flex justify-center px-4"
      style={{ right: 'var(--removed-body-scroll-bar-size, 0px)' }}
    >
      <nav
        aria-label="Main"
        className="pointer-events-auto flex h-14 w-full lg:w-auto items-center gap-2 rounded-pill border border-border bg-surface py-2 pl-6 pr-2 shadow-float"
      >
        <Link
          href="/"
          className="shrink-0 font-sans text-base font-semibold tracking-tight text-text transition-colors duration-console hover:text-text"
        >
          Awaaz Labs
        </Link>

        <div ref={navContainerRef} className="mx-4 hidden items-center justify-center gap-0.5 lg:flex relative">
          <div
            className="absolute rounded-pill bg-surface-muted transition-all duration-300 ease-out"
            style={{ 
              left: `${indicatorStyle.left}px`, 
              top: `${indicatorStyle.top}px`, 
              width: `${indicatorStyle.width}px`, 
              height: `${indicatorStyle.height}px`,
              opacity: indicatorStyle.opacity 
            }}
          />
          {navItems.map((item) => {
            const active = isActivePath(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                onMouseEnter={() => prefetchRouteData([...item.prefetch])}
                onFocus={() => prefetchRouteData([...item.prefetch])}
                className={cn(
                  'font-mono-label relative z-10 rounded-pill px-3.5 py-2.5 text-text-muted transition-colors duration-console hover:text-text',
                  active && 'text-text',
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="relative hidden md:block" ref={userDropdownRef}>
            <button
              type="button"
              onClick={() => setUserDropdownOpen((o) => !o)}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-surface font-mono text-sm font-medium uppercase text-text transition-colors duration-console hover:bg-surface-muted"
            >
              {getInitials(userEmail)}
            </button>

            {userDropdownOpen && (
              <div className="absolute right-0 top-[calc(100%+0.5rem)] z-[101] w-48 rounded-card border border-border bg-surface p-2 shadow-float">
                {userEmail && (
                  <div className="mb-2 truncate border-b border-border px-3 pb-2 pt-1 text-sm font-medium text-text">
                    {userEmail}
                  </div>
                )}
                <button
                  type="button"
                  onClick={handleLogout}
                  className="w-full rounded-input px-3 py-2 text-left font-mono-label text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-pill border border-border text-text transition-colors duration-console hover:bg-surface-muted lg:hidden"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <X className="h-4 w-4" aria-hidden /> : <Menu className="h-4 w-4" aria-hidden />}
          </button>
        </div>
      </nav>

      {menuOpen ? (
        <div className="pointer-events-auto absolute left-4 right-4 top-[4.5rem] z-[101] rounded-card border border-border bg-surface p-2 shadow-float lg:hidden">
          {navItems.map((item) => {
            const active = isActivePath(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'block rounded-input px-4 py-3 font-mono-label text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text',
                  active && 'bg-surface-muted text-text',
                )}
              >
                {item.label}
              </Link>
            );
          })}
          {userEmail && (
            <div className="mt-2 truncate px-4 py-2 text-sm font-medium text-text md:hidden">
              {userEmail}
            </div>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="mt-1 w-full rounded-input px-4 py-3 text-left font-mono-label text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text md:hidden"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </header>
  );
}
