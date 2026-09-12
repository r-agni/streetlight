/**
 * Ask the city a question.
 *
 * Questions go over the same socket the position frames use, so the map can
 * react to a tool call while the answer is still being written rather than
 * after it. Every number in an answer comes from a tool, not from the model.
 */
import { useEffect, useRef, useState } from 'react';
import { CornerDownLeft, Loader2, Sparkles } from 'lucide-react';

import { connection } from '../sim/connection';
import { SUGGESTIONS, useApp } from '../state/appStore';

export function Assistant() {
  const [draft, setDraft] = useState('');
  const scroller = useRef<HTMLDivElement>(null);
  const { messages, assistantBusy, mode, pushMessage, setAssistantBusy } = useApp();

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const ask = (text: string) => {
    const question = text.trim();
    if (!question || assistantBusy) return;
    pushMessage({ role: 'user', text: question });
    pushMessage({ role: 'assistant', text: '' });
    setAssistantBusy(true);
    setDraft('');
    connection.send({
      type: 'ask',
      text: question,
      context: { mode, shownAt: new Date().toISOString() },
    });
  };

  return (
    <div className="card-paper flex h-full w-[360px] flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
        <Sparkles size={14} className="text-[var(--color-ink-blue)]" strokeWidth={2.2} />
        <div className="text-[12.5px] font-semibold">Ask about the city</div>
        {assistantBusy && (
          <Loader2 size={13} className="ml-auto animate-spin text-[var(--color-ink-soft)]" />
        )}
      </div>

      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-[12px] leading-relaxed text-[var(--color-ink-soft)]">
              Questions are answered from the running simulation and San Francisco
              open data. Answers say which numbers are modelled and which are
              recorded.
            </p>
            {SUGGESTIONS[mode].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => ask(s)}
                className="block w-full rounded-[10px] border border-[var(--color-hairline)] bg-white/70 px-3 py-2 text-left text-[12px] leading-snug transition-colors hover:border-[var(--color-ink-blue)] hover:text-[var(--color-ink-blue)]"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-[12px] bg-[var(--color-ink-blue)] px-3 py-2 text-[12px] leading-snug text-white">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="space-y-1.5">
              {!!m.tools?.length && (
                <div className="flex flex-wrap gap-1">
                  {m.tools.map((t) => (
                    <span
                      key={t.name}
                      className={[
                        'rounded-[6px] px-1.5 py-0.5 text-[9.5px] font-medium uppercase tracking-[0.06em]',
                        t.status === 'error'
                          ? 'bg-[#e8384f]/12 text-[#c02a3f]'
                          : 'bg-[var(--color-ink-blue)]/10 text-[var(--color-ink-blue)]',
                      ].join(' ')}
                    >
                      {t.name.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              )}
              <div className="whitespace-pre-wrap text-[12.5px] leading-relaxed">
                {m.text || (
                  <span className="text-[var(--color-ink-soft)]">thinking…</span>
                )}
              </div>
            </div>
          ),
        )}
      </div>

      <div className="border-t border-[var(--color-hairline)] p-2.5">
        <div className="flex items-end gap-2 rounded-[12px] border border-[var(--color-hairline)] bg-white px-3 py-2 focus-within:border-[var(--color-ink-blue)]">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                ask(draft);
              }
            }}
            rows={2}
            placeholder="Where should I open a cafe in the Mission?"
            className="flex-1 resize-none bg-transparent text-[12.5px] leading-snug outline-none placeholder:text-[var(--color-ink-soft)]"
          />
          <button
            type="button"
            onClick={() => ask(draft)}
            disabled={!draft.trim() || assistantBusy}
            aria-label="Ask"
            className="mb-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-[7px] bg-[var(--color-ink-blue)] text-white disabled:opacity-30"
          >
            <CornerDownLeft size={12} strokeWidth={2.4} />
          </button>
        </div>
      </div>
    </div>
  );
}
