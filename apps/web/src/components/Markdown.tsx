/**
 * A small markdown renderer for assistant answers.
 *
 * The model writes headings, bold figures, bullet lists and links, and all of
 * it was being dumped as one grey block of preformatted text, which buried the
 * numbers the answer exists to deliver.
 *
 * Hand-rolled rather than pulled from a library for one reason that matters:
 * it builds React elements instead of setting innerHTML, so text arriving from
 * a model or quoted out of a customer review cannot inject markup. It covers
 * what the assistant actually emits and deliberately no more.
 */
import type { ReactNode } from 'react';

/** Split a line into bold, italic, code and link spans. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // links first, because their label may itself contain emphasis markers
  const pattern = /(\[[^\]]+\]\([^)]+\))|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${index++}`;

    if (token.startsWith('[')) {
      const split = token.indexOf('](');
      const label = token.slice(1, split);
      const href = token.slice(split + 2, -1);
      const safe = /^https?:\/\//i.test(href);
      nodes.push(
        safe ? (
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[var(--color-ink-blue)] underline decoration-[var(--color-ink-blue)]/30 underline-offset-2 hover:decoration-[var(--color-ink-blue)]"
          >
            {label}
          </a>
        ) : (
          <span key={key}>{label}</span>
        ),
      );
    } else if (token.startsWith('**')) {
      nodes.push(
        <strong key={key} className="font-semibold text-[var(--color-ink)]">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith('`')) {
      nodes.push(
        <code key={key} className="tnum rounded-[4px] bg-black/[0.06] px-1 py-px text-[11px]">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

interface Block {
  kind: 'heading' | 'paragraph' | 'bullets' | 'numbers' | 'quote';
  lines: string[];
}

/** Group lines into blocks, which is all the structure this needs. */
function parse(source: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;

  const flush = () => {
    if (current && current.lines.length) blocks.push(current);
    current = null;
  };

  for (const raw of source.split('\n')) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    if (/^#{1,6}\s/.test(line)) {
      flush();
      blocks.push({ kind: 'heading', lines: [line.replace(/^#{1,6}\s/, '')] });
      continue;
    }
    if (/^>\s?/.test(line)) {
      if (current?.kind !== 'quote') {
        flush();
        current = { kind: 'quote', lines: [] };
      }
      current.lines.push(line.replace(/^>\s?/, ''));
      continue;
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      if (current?.kind !== 'bullets') {
        flush();
        current = { kind: 'bullets', lines: [] };
      }
      current.lines.push(line.replace(/^\s*[-*•]\s+/, ''));
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      if (current?.kind !== 'numbers') {
        flush();
        current = { kind: 'numbers', lines: [] };
      }
      current.lines.push(line.replace(/^\s*\d+[.)]\s+/, ''));
      continue;
    }
    if (current?.kind !== 'paragraph') {
      flush();
      current = { kind: 'paragraph', lines: [] };
    }
    current.lines.push(line);
  }
  flush();
  return blocks;
}

export function Markdown({ text }: { text: string }) {
  if (!text.trim()) return null;
  const blocks = parse(text);

  return (
    <div className="space-y-2 text-[12.5px] leading-relaxed">
      {blocks.map((block, i) => {
        const key = `b${i}`;
        switch (block.kind) {
          case 'heading':
            return (
              <div key={key} className="pt-0.5 text-[12.5px] font-semibold">
                {inline(block.lines[0], key)}
              </div>
            );
          case 'bullets':
            return (
              <ul key={key} className="space-y-1">
                {block.lines.map((line, j) => (
                  <li key={`${key}-${j}`} className="flex gap-1.5">
                    <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-[var(--color-ink-blue)]" />
                    <span className="min-w-0 flex-1">{inline(line, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ul>
            );
          case 'numbers':
            return (
              <ol key={key} className="space-y-1">
                {block.lines.map((line, j) => (
                  <li key={`${key}-${j}`} className="flex gap-1.5">
                    <span className="tnum mt-px shrink-0 text-[11px] font-semibold text-[var(--color-ink-blue)]">
                      {j + 1}.
                    </span>
                    <span className="min-w-0 flex-1">{inline(line, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ol>
            );
          case 'quote':
            return (
              <blockquote
                key={key}
                className="border-l-2 border-[var(--color-ink-blue)]/30 pl-2 text-[var(--color-ink-soft)]"
              >
                {inline(block.lines.join(' '), key)}
              </blockquote>
            );
          default:
            return <p key={key}>{inline(block.lines.join(' '), key)}</p>;
        }
      })}
    </div>
  );
}
