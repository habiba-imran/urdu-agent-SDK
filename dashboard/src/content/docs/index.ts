import { meta as overviewMeta, markdown as overviewMd } from './pages/overview';
import {
  meta as howMeta,
  markdown as howMd,
} from './pages/how-integration-works';
import { meta as quickMeta, markdown as quickMd } from './pages/quickstart';
import { meta as expectMeta, markdown as expectMd } from './pages/what-to-expect';
import { meta as backendMeta, markdown as backendMd } from './pages/backend-setup';
import {
  meta as frontendMeta,
  markdown as frontendMd,
} from './pages/frontend-setup';
import { meta as telMeta, markdown as telMd } from './pages/telephony';
import { meta as liveMeta, markdown as liveMd } from './pages/going-live';
import { meta as humanMeta, markdown as humanMd } from './pages/humanization-testing';
import { meta as sdkMeta, markdown as sdkMd } from './pages/sdk-reference';
import {
  meta as eventsMeta,
  markdown as eventsMd,
} from './pages/events-and-lifecycle';
import {
  meta as errorsMeta,
  markdown as errorsMd,
} from './pages/errors-and-troubleshooting';
import { meta as securityMeta, markdown as securityMd } from './pages/security';
import {
  meta as providersMeta,
  markdown as providersMd,
} from './pages/providers';
import {
  meta as legalMeta,
  markdown as legalMd,
} from './pages/legal-and-trust';
import { DOCS_PAGE_ORDER, docsHref } from './nav';

export type DocsPage = {
  slug: string;
  title: string;
  eyebrow: string;
  description: string;
  markdown: string;
};

const PAGES: DocsPage[] = [
  { ...overviewMeta, markdown: overviewMd },
  { ...howMeta, markdown: howMd },
  { ...quickMeta, markdown: quickMd },
  { ...expectMeta, markdown: expectMd },
  { ...backendMeta, markdown: backendMd },
  { ...frontendMeta, markdown: frontendMd },
  { ...telMeta, markdown: telMd },
  { ...liveMeta, markdown: liveMd },
  { ...humanMeta, markdown: humanMd },
  { ...providersMeta, markdown: providersMd },
  { ...sdkMeta, markdown: sdkMd },
  { ...eventsMeta, markdown: eventsMd },
  { ...errorsMeta, markdown: errorsMd },
  { ...securityMeta, markdown: securityMd },
  { ...legalMeta, markdown: legalMd },
];

const bySlug = new Map(PAGES.map((p) => [p.slug, p]));

export function getDocsPage(slug: string): DocsPage | undefined {
  return bySlug.get(slug);
}

export function getAllDocsSlugs(): string[] {
  return DOCS_PAGE_ORDER.filter((s) => bySlug.has(s));
}

export function getDocsNeighbors(slug: string): {
  prev?: { href: string; title: string };
  next?: { href: string; title: string };
} {
  const order = getAllDocsSlugs();
  const i = order.indexOf(slug);
  if (i < 0) return {};
  const prevSlug = order[i - 1];
  const nextSlug = order[i + 1];
  const prev = prevSlug ? bySlug.get(prevSlug) : undefined;
  const next = nextSlug ? bySlug.get(nextSlug) : undefined;
  return {
    prev: prev ? { href: docsHref(prev.slug), title: prev.title } : undefined,
    next: next ? { href: docsHref(next.slug), title: next.title } : undefined,
  };
}

export { PAGES };
