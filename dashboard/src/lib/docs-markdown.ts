/** Heading extraction + light markdown helpers for docs. */

export type DocsHeading = { id: string; title: string; level: 2 | 3 };

export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .replace(/[`*_]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

export function extractHeadings(markdown: string): DocsHeading[] {
  const headings: DocsHeading[] = [];
  const seen = new Map<string, number>();
  for (const line of markdown.split('\n')) {
    const m = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (!m) continue;
    const level = m[1].length as 2 | 3;
    const title = m[2].replace(/[*_`]/g, '').trim();
    let id = slugifyHeading(title);
    const n = seen.get(id) ?? 0;
    seen.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;
    headings.push({ id, title, level });
  }
  return headings;
}

import {
  PLATFORM_CONTROL_PLANE_URL,
  PLATFORM_TENANT_PORTAL_URL,
} from '@/lib/platformUrls';

/** Apply non-secret platform URL prefills into markdown placeholders. */
export function applyDocPlaceholders(markdown: string): string {
  return markdown
    .replaceAll('https://your-control-plane.example', PLATFORM_CONTROL_PLANE_URL)
    .replaceAll('https://your-portal-api.example', PLATFORM_TENANT_PORTAL_URL);
}
