'use client';

import React from 'react';
import { cn } from '@/lib/utils';

/** Route page header: breadcrumb, mono eyebrow, title, optional description + actions. */
export function PageHeader({
  title,
  description,
  actions,
  className,
  breadcrumbLabel,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
  /** Final crumb label; defaults to uppercased title */
  breadcrumbLabel?: string;
  /** Defaults to title */
  eyebrow?: string;
}) {
  const pageCrumb = (breadcrumbLabel ?? title).toUpperCase();
  const eye = eyebrow ?? title;

  return (
    <div
      className={cn(
        'flex flex-col gap-6 pb-8 sm:flex-row sm:items-start sm:justify-between',
        className,
      )}
    >
      <div className="flex max-w-xl flex-col gap-6">
        <nav aria-label="Breadcrumb" className="font-mono-label">
          <ol className="flex flex-wrap items-center gap-2">
            <li className="text-text-muted">Home</li>
            <li className="text-text-muted" aria-hidden>
              /
            </li>
            <li className="text-text" aria-current="page">
              {pageCrumb}
            </li>
          </ol>
        </nav>
        <div className="flex flex-col gap-3">
          <p className="font-mono-label text-text-muted">{eye}</p>
          <h1 className="font-sans text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text">
            {title}
          </h1>
          {description ? (
            <p className="max-w-[560px] text-[15px] leading-relaxed text-text-body">{description}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
