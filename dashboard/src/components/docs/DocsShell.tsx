'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';

import { DOCS_NAV, docsHref } from '@/content/docs/nav';
import { cn } from '@/lib/utils';
import type { DocsHeading } from '@/lib/docs-markdown';
import { DocsMarkdown } from '@/components/docs/DocsMarkdown';

export function DocsShell({
  slug,
  title,
  eyebrow,
  description,
  markdown,
  headings,
  prev,
  next,
}: {
  slug: string;
  title: string;
  eyebrow: string;
  description: string;
  markdown: string;
  headings: DocsHeading[];
  prev?: { href: string; title: string };
  next?: { href: string; title: string };
}) {
  const pathname = usePathname();
  const [activeId, setActiveId] = React.useState<string>('');

  React.useEffect(() => {
    const h2Ids = headings.filter((h) => h.level === 2).map((h) => h.id);
    if (!h2Ids.length) return;

    const handleScroll = () => {
      let current = h2Ids[0];
      for (const id of h2Ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < 200) {
          current = id;
        }
      }
      setActiveId(current);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    // Trigger once on mount
    handleScroll();

    return () => window.removeEventListener('scroll', handleScroll);
  }, [headings]);

  return (
    <div className="flex gap-10 xl:gap-12">
      {/* Left nav */}
      <aside className="hidden w-[240px] shrink-0 md:block">
        <nav aria-label="Docs" className="sticky top-[120px] max-h-[calc(100vh-140px)] overflow-y-auto pr-2">
          <div className="space-y-8">
            {DOCS_NAV.map((group) => (
              <div key={group.title}>
                <p className="mb-3 font-mono-label text-text-muted">{group.title}</p>
                <ul className="space-y-0.5">
                  {group.items.map((item) => {
                    const href = docsHref(item.slug);
                    const active =
                      slug === item.slug ||
                      pathname === href ||
                      pathname.startsWith(`${href}/`);
                    return (
                      <li key={item.slug}>
                        <Link
                          href={href}
                          aria-current={active ? 'page' : undefined}
                          className={cn(
                            'block rounded-input px-3 py-2 text-[13px] leading-snug text-text-muted transition-colors duration-console hover:bg-surface-muted hover:text-text',
                            active && 'bg-surface-muted font-medium text-text',
                          )}
                        >
                          {item.title}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>
      </aside>

      {/* Center */}
      <div className="min-w-0 flex-1">
        {/* Mobile page picker */}
        <div className="mb-8 md:hidden">
          <label className="mb-2 block font-mono-label text-text-muted">Docs</label>
          <select
            className="w-full rounded-input border border-border bg-surface px-3 py-2.5 text-[14px] text-text"
            value={slug}
            onChange={(e) => {
              window.location.href = docsHref(e.target.value);
            }}
          >
            {DOCS_NAV.map((group) => (
              <optgroup key={group.title} label={group.title}>
                {group.items.map((item) => (
                  <option key={item.slug} value={item.slug}>
                    {item.title}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        <header className="mb-10 max-w-[720px]">
          <p className="font-mono-label text-text-muted">{eyebrow}</p>
          <h1 className="mt-3 font-sans text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text">
            {title}
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-text-body">{description}</p>
        </header>

        <DocsMarkdown markdown={markdown} />

        <nav
          aria-label="Docs pagination"
          className="mt-16 flex max-w-[720px] items-stretch justify-between gap-4 border-t border-border pt-8"
        >
          {prev ? (
            <Link
              href={prev.href}
              className="group flex min-w-0 flex-1 flex-col gap-1 rounded-card border border-border bg-surface p-4 transition-colors duration-console hover:bg-surface-muted"
            >
              <span className="inline-flex items-center gap-1 font-mono-label text-text-muted">
                <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
                Previous
              </span>
              <span className="truncate text-[15px] font-medium text-text">{prev.title}</span>
            </Link>
          ) : (
            <span className="flex-1" />
          )}
          {next ? (
            <Link
              href={next.href}
              className="group flex min-w-0 flex-1 flex-col items-end gap-1 rounded-card border border-border bg-surface p-4 text-right transition-colors duration-console hover:bg-surface-muted"
            >
              <span className="inline-flex items-center gap-1 font-mono-label text-text-muted">
                Next
                <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              </span>
              <span className="truncate text-[15px] font-medium text-text">{next.title}</span>
            </Link>
          ) : (
            <span className="flex-1" />
          )}
        </nav>
      </div>

      {/* Right rail */}
      <aside className="hidden w-[200px] shrink-0 min-[1100px]:block">
        <div className="sticky top-[120px]">
          <p className="mb-3 font-mono-label text-text-muted">On this page</p>
          <ul className="space-y-2 border-l border-border pl-3">
            {headings
              .filter((h) => h.level === 2)
              .map((h) => (
                <li key={h.id}>
                  <a
                    href={`#${h.id}`}
                    className={cn(
                      'block text-[12px] leading-snug transition-colors duration-console hover:text-text',
                      activeId === h.id ? 'font-semibold text-text' : 'text-text-muted'
                    )}
                  >
                    {h.title}
                  </a>
                </li>
              ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
