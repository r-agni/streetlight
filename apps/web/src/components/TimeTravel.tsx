/**
 * Move between a past date, now, and a projected future one.
 *
 * The simulation runs a typical week, so a date does two different jobs
 * depending on which side of now it falls. Looking back replays that typical
 * week against a real past date; looking forward projects it onto a future one.
 * Neither is a record or a forecast of that particular day, and the panel says
 * so rather than letting a date imply more certainty than the model has.
 */
import { useEffect, useState } from 'react';
import { CalendarClock, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

import { API_URL } from '../sim/connection';
import { useSim, type ClockState } from '../state/simStore';

const HORIZON_STYLE: Record<string, { label: string; className: string }> = {
  past: { label: 'looking back', className: 'bg-[#8b3dff]/12 text-[#6d2ecb]' },
  live: { label: 'now', className: 'bg-[#00a878]/14 text-[#00875f]' },
  future: { label: 'projected', className: 'bg-[#f5b301]/18 text-[#8a6400]' },
};

async function moveClock(params: Record<string, unknown>): Promise<ClockState | null> {
  const url = new URL(`${API_URL}/api/clock`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
  }
  try {
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) return null;
    return (await res.json()) as ClockState;
  } catch {
    return null;
  }
}

export function TimeTravel() {
  const clock = useSim((s) => s.clock);
  const setClock = useSim((s) => s.setClock);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (clock) return;
    fetch(`${API_URL}/api/clock`)
      .then((r) => r.json())
      .then((c: ClockState) => setClock(c))
      .catch(() => undefined);
  }, [clock, setClock]);

  const go = async (params: Record<string, unknown>) => {
    setBusy(true);
    const next = await moveClock(params);
    if (next) setClock(next);
    setBusy(false);
  };

  const horizon = HORIZON_STYLE[clock?.horizon ?? 'live'] ?? HORIZON_STYLE.live;
  const offset = clock?.daysFromNow ?? 0;

  return (
    <div className="card-paper px-4 py-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 text-left"
      >
        <CalendarClock size={13} className="shrink-0 text-[var(--color-ink-blue)]" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold">
            {clock?.label ?? 'Reading the clock…'}
          </div>
          <div className="text-[10px] text-[var(--color-ink-soft)]">
            San Francisco time
          </div>
        </div>
        <span
          className={`shrink-0 rounded-[5px] px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.06em] ${horizon.className}`}
        >
          {horizon.label}
        </span>
        {busy && <Loader2 size={11} className="animate-spin text-[var(--color-ink-soft)]" />}
      </button>

      {open && (
        <div className="mt-3 space-y-2 border-t border-[var(--color-hairline)] pt-2.5">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => go({ day_offset: offset - 1, hour: clock?.minute ? undefined : 12 })}
              className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-white/70 text-[var(--color-ink-soft)] hover:bg-white"
              aria-label="One day back"
            >
              <ChevronLeft size={13} />
            </button>
            <button
              type="button"
              onClick={() => go({})}
              className={[
                'flex-1 rounded-[7px] px-2 py-1.5 text-[11px] font-medium transition-colors',
                clock?.horizon === 'live'
                  ? 'bg-[var(--color-ink-blue)] text-white'
                  : 'bg-white/70 text-[var(--color-ink-soft)] hover:bg-white',
              ].join(' ')}
            >
              Back to now
            </button>
            <button
              type="button"
              onClick={() => go({ day_offset: offset + 1 })}
              className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-white/70 text-[var(--color-ink-soft)] hover:bg-white"
              aria-label="One day forward"
            >
              <ChevronRight size={13} />
            </button>
          </div>

          <div className="grid grid-cols-4 gap-1">
            {[
              { label: '-7d', days: -7 },
              { label: '-1d', days: -1 },
              { label: '+1d', days: 1 },
              { label: '+7d', days: 7 },
            ].map((jump) => (
              <button
                key={jump.label}
                type="button"
                onClick={() => go({ day_offset: jump.days })}
                className="tnum rounded-[7px] bg-white/70 px-1 py-1 text-[10.5px] text-[var(--color-ink-soft)] transition-colors hover:bg-white hover:text-[var(--color-ink-blue)]"
              >
                {jump.label}
              </button>
            ))}
          </div>

          <input
            type="date"
            onChange={(e) => e.target.value && go({ iso: e.target.value })}
            className="w-full rounded-[7px] border border-[var(--color-hairline)] bg-white px-2 py-1.5 text-[11.5px] outline-none focus:border-[var(--color-ink-blue)]"
          />

          {clock?.describe && (
            <p className="text-[10px] leading-snug text-[var(--color-ink-soft)]">
              {clock.describe}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
