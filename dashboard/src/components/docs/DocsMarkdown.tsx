'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { CodeBlock } from '@/components/ui/code-block';
import { cn } from '@/lib/utils';
import { slugifyHeading } from '@/lib/docs-markdown';

type InlineNode = string | React.ReactNode;

function renderInline(text: string, keyPrefix: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  // links, bold, inline code
  const re = /(\[([^\]]+)\]\(([^)]+)\))|(\*\*([^*]+)\*\*)|(`([^`]+)`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      const href = m[3];
      const label = m[2];
      const external = href.startsWith('http');
      nodes.push(
        external ? (
          <a
            key={`${keyPrefix}-a-${i++}`}
            href={href}
            className="font-medium text-text underline-offset-4 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            {label}
          </a>
        ) : (
          <Link
            key={`${keyPrefix}-a-${i++}`}
            href={href}
            className="font-medium text-text underline-offset-4 hover:underline"
          >
            {label}
          </Link>
        ),
      );
    } else if (m[4]) {
      nodes.push(
        <strong key={`${keyPrefix}-b-${i++}`} className="font-semibold text-text">
          {m[5]}
        </strong>,
      );
    } else if (m[6]) {
      nodes.push(
        <code
          key={`${keyPrefix}-c-${i++}`}
          className="rounded-sm bg-surface-muted px-1.5 py-0.5 font-mono text-[12px] text-text"
        >
          {m[7]}
        </code>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Fence = { lang: string; label: string; code: string };
type TabGroup = { tabs: { name: string; fence: Fence }[] };

type Block =
  | { type: 'h2' | 'h3'; id: string; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul' | 'ol'; items: string[] }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'fence'; fence: Fence }
  | { type: 'tabs'; group: TabGroup }
  | { type: 'hr' };

function parseFenceHeader(info: string): { lang: string; label: string } {
  const parts = info.trim().split(/\s+/);
  const lang = parts[0] || 'text';
  let label = lang.toUpperCase();
  const titlePart = parts.find((p) => p.startsWith('title='));
  if (titlePart) label = titlePart.slice('title='.length);
  return { lang, label };
}

function parseMarkdownBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  const seenIds = new Map<string, number>();

  const allocId = (title: string) => {
    let id = slugifyHeading(title);
    const n = seenIds.get(id) ?? 0;
    seenIds.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;
    return id;
  };

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (line.trim() === ':::tabs') {
      i += 1;
      const tabs: TabGroup['tabs'] = [];
      let currentName = '';
      while (i < lines.length && lines[i].trim() !== ':::') {
        const t = lines[i];
        if (t.startsWith('===')) {
          currentName = t.replace(/^===\s*/, '').trim();
          i += 1;
          continue;
        }
        if (t.startsWith('```')) {
          const { lang, label } = parseFenceHeader(t.slice(3));
          i += 1;
          const codeLines: string[] = [];
          while (i < lines.length && !lines[i].startsWith('```')) {
            codeLines.push(lines[i]);
            i += 1;
          }
          i += 1; // closing ```
          tabs.push({
            name: currentName || label,
            fence: { lang, label, code: codeLines.join('\n') },
          });
          continue;
        }
        i += 1;
      }
      i += 1; // closing :::
      if (tabs.length) blocks.push({ type: 'tabs', group: { tabs } });
      continue;
    }

    if (line.startsWith('```')) {
      const { lang, label } = parseFenceHeader(line.slice(3));
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ type: 'fence', fence: { lang, label, code: codeLines.join('\n') } });
      continue;
    }

    const h = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (h) {
      const text = h[2].trim();
      blocks.push({
        type: h[1].length === 2 ? 'h2' : 'h3',
        id: allocId(text.replace(/[*_`]/g, '')),
        text,
      });
      i += 1;
      continue;
    }

    if (line.trim() === '---') {
      blocks.push({ type: 'hr' });
      i += 1;
      continue;
    }

    if (line.trim().startsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        tableLines.push(lines[i].trim());
        i += 1;
      }
      const parseRow = (row: string) =>
        row
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((c) => c.trim());
      if (tableLines.length >= 2) {
        const headers = parseRow(tableLines[0]);
        const rows = tableLines.slice(2).map(parseRow);
        blocks.push({ type: 'table', headers, rows });
      }
      continue;
    }

    if (/^[-*]\s+/.test(line.trim()) || /^\d+\.\s+/.test(line.trim())) {
      const ordered = /^\d+\.\s+/.test(line.trim());
      const items: string[] = [];
      while (i < lines.length) {
        const t = lines[i].trim();
        if (ordered ? !/^\d+\.\s+/.test(t) : !/^[-*]\s+/.test(t)) break;
        items.push(t.replace(/^([-*]|\d+\.)\s+/, ''));
        i += 1;
      }
      blocks.push({ type: ordered ? 'ol' : 'ul', items });
      continue;
    }

    const para: string[] = [];
    while (i < lines.length && lines[i].trim()) {
      const t = lines[i];
      if (
        t.startsWith('#') ||
        t.startsWith('```') ||
        t.trim().startsWith('|') ||
        t.trim() === ':::tabs' ||
        t.trim() === '---' ||
        /^[-*]\s+/.test(t.trim()) ||
        /^\d+\.\s+/.test(t.trim())
      ) {
        break;
      }
      para.push(t.trim());
      i += 1;
    }
    if (para.length) blocks.push({ type: 'p', text: para.join(' ') });
  }

  return blocks;
}

function CodeTabs({ group }: { group: TabGroup }) {
  const [active, setActive] = useState(0);
  const tab = group.tabs[active] ?? group.tabs[0];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">
        {group.tabs.map((t, idx) => (
          <button
            key={t.name}
            type="button"
            onClick={() => setActive(idx)}
            className={cn(
              'rounded-pill px-3.5 py-2 font-mono-label text-text-muted transition-colors duration-console hover:text-text',
              idx === active && 'bg-surface-muted text-text',
            )}
          >
            {t.name}
          </button>
        ))}
      </div>
      <CodeBlock label={tab.fence.label} code={tab.fence.code} />
    </div>
  );
}

function ChecklistItem({ text, index }: { text: string; index: number }) {
  const checked = text.startsWith('[x] ') || text.startsWith('[X] ');
  const unchecked = text.startsWith('[ ] ');
  if (checked || unchecked) {
    const label = text.slice(4);
    return (
      <li className="flex gap-3">
        <span
          className={cn(
            'mt-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-border',
            checked && 'bg-text text-white',
          )}
          aria-hidden
        >
          {checked ? '✓' : null}
        </span>
        <span>{renderInline(label, `check-${index}`)}</span>
      </li>
    );
  }
  return <li className="ml-1 list-disc pl-4">{renderInline(text, `li-${index}`)}</li>;
}

export function DocsMarkdown({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => parseMarkdownBlocks(markdown.trim()), [markdown]);

  return (
    <div className="docs-prose space-y-6 text-[15px] leading-[1.75] text-text-body">
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'h2':
            return (
              <h2
                key={idx}
                id={block.id}
                className="scroll-mt-32 pt-4 font-sans text-[28px] font-bold leading-tight tracking-[-0.02em] text-text"
              >
                {renderInline(block.text, `h2-${idx}`)}
              </h2>
            );
          case 'h3':
            return (
              <h3
                key={idx}
                id={block.id}
                className="scroll-mt-32 pt-2 font-sans text-[20px] font-semibold tracking-[-0.01em] text-text"
              >
                {renderInline(block.text, `h3-${idx}`)}
              </h3>
            );
          case 'p':
            return (
              <p key={idx} className="max-w-[720px]">
                {renderInline(block.text, `p-${idx}`)}
              </p>
            );
          case 'ul':
            return (
              <ul key={idx} className="max-w-[720px] space-y-2">
                {block.items.map((item, j) => (
                  <ChecklistItem key={j} text={item} index={j} />
                ))}
              </ul>
            );
          case 'ol':
            return (
              <ol key={idx} className="max-w-[720px] list-decimal space-y-2 pl-5">
                {block.items.map((item, j) => (
                  <li key={j}>{renderInline(item, `ol-${idx}-${j}`)}</li>
                ))}
              </ol>
            );
          case 'table':
            return (
              <div key={idx} className="max-w-full overflow-x-auto rounded-card border border-border">
                <table className="w-full min-w-[480px] border-collapse text-left text-[13px]">
                  <thead className="bg-surface-muted">
                    <tr>
                      {block.headers.map((h) => (
                        <th
                          key={h}
                          className="border-b border-border px-4 py-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted"
                        >
                          {renderInline(h, `th-${h}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r} className="border-b border-border last:border-0">
                        {row.map((cell, c) => (
                          <td key={c} className="px-4 py-3 align-top text-text-body">
                            {renderInline(cell, `td-${r}-${c}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case 'fence':
            return <CodeBlock key={idx} label={block.fence.label} code={block.fence.code} />;
          case 'tabs':
            return <CodeTabs key={idx} group={block.group} />;
          case 'hr':
            return <hr key={idx} className="border-border" />;
          default:
            return null;
        }
      })}
    </div>
  );
}
