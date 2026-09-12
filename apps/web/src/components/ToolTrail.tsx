/**
 * What an answer actually did.
 *
 * Each row is one tool call: what it was asked, what it did, and which datasets
 * it read, with record counts and time windows. The trail is built from what
 * the tools reported, not from the model's account of itself, so it cannot
 * drift from what really happened.
 *
 * Sources are tagged recorded, modelled, derived or reference, because the
 * difference between a measured complaint count and a simulated footfall
 * number is the difference between evidence and a hypothesis.
 */
import { useState } from 'react';
import { Check, ChevronRight, Loader2, X } from 'lucide-react';

import type { ToolSource, ToolStep } from '../state/appStore';

const TOOL_LABEL: Record<string, string> = {
  get_area_report: 'Read the area',
  find_opportunity: 'Searched demand against supply',
  rank_sites: 'Scored vacant parcels',
  simulate_event: 'Modelled the event',
  compare_areas: 'Compared areas',
  control_interface: 'Adjusted the interface',
  show_on_map: 'Moved the map',
  set_time: 'Moved the clock',
};

const KIND_STYLE: Record<ToolSource['kind'], { label: string; className: string }> = {
  recorded: { label: 'recorded', className: 'bg-[#e8384f]/12 text-[#b32a3c]' },
  modelled: { label: 'modelled', className: 'bg-[var(--color-ink-blue)]/12 text-[var(--color-ink-blue)]' },
  derived: { label: 'derived', className: 'bg-[#8b3dff]/12 text-[#6d2ecb]' },
  reference: { label: 'reference', className: 'bg-black/8 text-[var(--color-ink-soft)]' },
};

/** Show the arguments that actually change the answer, not the whole object. */
function describeInput(input?: Record<string, unknown>): string {
  if (!input) return '';
  const parts: string[] = [];
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === null || value === '') continue;
    const text = Array.isArray(value) ? value.join(', ') : String(value);
    if (!text || text === 'false') continue;
    parts.push(`${key.replace(/_/g, ' ')}: ${text}`);
  }
  return parts.join(' · ').slice(0, 220);
}

function SourceRow({ source }: { source: ToolSource }) {
  const style = KIND_STYLE[source.kind] ?? KIND_STYLE.reference;
  return (
    <div className="flex items-baseline gap-1.5 py-[3px]">
      <span
        className={`shrink-0 rounded-[4px] px-1 py-[1px] text-[8.5px] font-medium uppercase tracking-[0.05em] ${style.className}`}
      >
        {style.label}
      </span>
      <span className="text-[10.5px] font-medium">{source.label}</span>
      {source.count !== undefined && (
        <span className="tnum text-[10px] text-[var(--color-ink-soft)]">
          {source.count.toLocaleString()}
        </span>
      )}
      {source.window && (
        <span className="text-[10px] text-[var(--color-ink-soft)]">· {source.window}</span>
      )}
    </div>
  );
}

export function ToolTrail({ steps }: { steps: ToolStep[] }) {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;

  const running = steps.some((s) => s.status === 'start');
  const sourceCount = new Set(
    steps.flatMap((s) => (s.sources ?? []).map((x) => x.label)),
  ).size;

  return (
    <div className="rounded-[10px] border border-[var(--color-hairline)] bg-white/60">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left"
      >
        <ChevronRight
          size={11}
          className={`shrink-0 text-[var(--color-ink-soft)] transition-transform ${open ? 'rotate-90' : ''}`}
        />
        <span className="text-[10.5px] font-medium">
          {running ? 'Working' : 'How this was answered'}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {running && <Loader2 size={10} className="animate-spin text-[var(--color-ink-soft)]" />}
          <span className="tnum text-[9.5px] text-[var(--color-ink-soft)]">
            {steps.length} step{steps.length === 1 ? '' : 's'}
            {sourceCount ? ` · ${sourceCount} source${sourceCount === 1 ? '' : 's'}` : ''}
          </span>
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-[var(--color-hairline)] px-2 py-2">
          {steps.map((step, i) => (
            <div key={`${step.name}-${i}`} className="space-y-1">
              <div className="flex items-baseline gap-1.5">
                <span className="mt-[3px] shrink-0">
                  {step.status === 'ok' ? (
                    <Check size={10} className="text-[#00875f]" strokeWidth={3} />
                  ) : step.status === 'error' ? (
                    <X size={10} className="text-[#b32a3c]" strokeWidth={3} />
                  ) : (
                    <Loader2 size={10} className="animate-spin text-[var(--color-ink-soft)]" />
                  )}
                </span>
                <span className="text-[11px] font-medium">
                  {TOOL_LABEL[step.name] ?? step.name.replace(/_/g, ' ')}
                </span>
              </div>

              {!!describeInput(step.input) && (
                <div className="pl-[18px] text-[10px] leading-snug text-[var(--color-ink-soft)]">
                  {describeInput(step.input)}
                </div>
              )}
              {step.summary && (
                <div className="pl-[18px] text-[10.5px] leading-snug">{step.summary}</div>
              )}
              {!!step.sources?.length && (
                <div className="pl-[18px]">
                  {step.sources.map((source, k) => (
                    <SourceRow key={`${source.label}-${k}`} source={source} />
                  ))}
                </div>
              )}
            </div>
          ))}

          <p className="border-t border-[var(--color-hairline)] pt-1.5 text-[9.5px] leading-snug text-[var(--color-ink-soft)]">
            Recorded figures come from San Francisco open data and public
            listings. Modelled figures are simulation output, not measurement.
          </p>
        </div>
      )}
    </div>
  );
}
