/**
 * Docs sidebar + page registry.
 * Content lives in `./pages/*.ts` as markdown strings.
 */

export type DocsNavGroup = {
  title: string;
  items: { slug: string; title: string }[];
};

export type DocsPageMeta = {
  slug: string;
  title: string;
  eyebrow: string;
  description: string;
  /** Heading ids for the right rail (derived from ## headings). */
  sections?: { id: string; title: string }[];
};

export const DOCS_NAV: DocsNavGroup[] = [
  {
    title: 'Get started',
    items: [
      { slug: 'overview', title: 'Overview' },
      { slug: 'how-integration-works', title: 'How integration works' },
      { slug: 'quickstart', title: 'Quickstart' },
      { slug: 'what-to-expect', title: 'What to expect' },
    ],
  },
  {
    title: 'Integrate',
    items: [
      { slug: 'backend-setup', title: 'Backend setup' },
      { slug: 'frontend-setup', title: 'Frontend setup' },
      { slug: 'telephony', title: 'Telephony' },
      { slug: 'going-live', title: 'Going live' },
    ],
  },
  {
    title: 'Reference',
    items: [
      { slug: 'providers', title: 'Providers' },
      { slug: 'sdk-reference', title: 'SDK reference' },
      { slug: 'events-and-lifecycle', title: 'Events and lifecycle' },
      { slug: 'errors-and-troubleshooting', title: 'Errors and troubleshooting' },
      { slug: 'security', title: 'Security' },
      { slug: 'legal-and-trust', title: 'Legal and trust' },
    ],
  },
];

/** Flat order for Previous / Next. */
export const DOCS_PAGE_ORDER: string[] = DOCS_NAV.flatMap((g) => g.items.map((i) => i.slug));

export function docsHref(slug: string): string {
  return `/docs/${slug}`;
}
