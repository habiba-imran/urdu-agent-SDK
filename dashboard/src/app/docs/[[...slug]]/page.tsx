import { notFound, redirect } from 'next/navigation';

import { DocsShell } from '@/components/docs/DocsShell';
import {
  getAllDocsSlugs,
  getDocsNeighbors,
  getDocsPage,
} from '@/content/docs';
import { applyDocPlaceholders, extractHeadings } from '@/lib/docs-markdown';

export function generateStaticParams() {
  return getAllDocsSlugs().map((slug) => ({ slug: [slug] }));
}

export default async function DocsPage({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const { slug: parts } = await params;
  if (!parts?.length) {
    redirect('/docs/overview');
  }
  const slug = parts[0];
  if (parts.length > 1) {
    notFound();
  }

  const page = getDocsPage(slug);
  if (!page) {
    notFound();
  }

  const markdown = applyDocPlaceholders(page.markdown);
  const headings = extractHeadings(markdown);
  const neighbors = getDocsNeighbors(slug);

  return (
    <DocsShell
      slug={page.slug}
      title={page.title}
      eyebrow={page.eyebrow}
      description={page.description}
      markdown={markdown}
      headings={headings}
      prev={neighbors.prev}
      next={neighbors.next}
    />
  );
}
