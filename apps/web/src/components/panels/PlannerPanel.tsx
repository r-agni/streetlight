/**
 * Planning tools: how far people can actually walk, and what is being built.
 *
 * The catchment is the piece planners reach for first, and it is measured
 * along the street network rather than drawn as a circle. In a city cut by
 * freeways, water and hills, the difference between those two is the
 * difference between a defensible service area and a decorative one.
 */
import { useState } from 'react';
import { Footprints, Loader2 } from 'lucide-react';

import { api } from '../../lib/api';
import { INK } from '../../lib/palette';
import { useApp } from '../../state/appStore';

const MINUTES = [5, 10, 15, 20];

export function PlannerPanel() {
  const [place, setPlace] = useState('civic center');
  const [minutes, setMinutes] = useState(10);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    method: string;
    minutes: number;
    nodesReached?: number;
  } | null>(null);
  const { setCatchmentHull, setMarkers } = useApp();

  const run = async () => {
    setBusy(true);
    try {
      const point = await api.geocode(place);
      const hull = await api.catchment(point.lon, point.lat, minutes);
      setCatchmentHull(hull.hull ?? null);
      setResult({
        method: hull.method,
        minutes: hull.minutes,
        nodesReached: (hull as { nodesReached?: number }).nodesReached,
      });
      setMarkers([{ label: place, lon: point.lon, lat: point.lat, kind: 'site' }]);
      (
        window as unknown as { __setView?: (c: [number, number], z: number) => void }
      ).__setView?.([point.lon, point.lat], 14.4);
    } catch {
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card-paper px-4 py-3">
      <div className="eyebrow mb-2 text-[var(--color-ink-soft)]">Walking access</div>

      <div className="flex gap-1.5">
        <input
          value={place}
          onChange={(e) => setPlace(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder="Address or neighbourhood"
          className="min-w-0 flex-1 rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5 text-[12px] outline-none focus:border-[var(--color-ink-blue)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="flex items-center gap-1 rounded-[8px] bg-[var(--color-ink-blue)] px-2.5 text-[12px] font-medium text-white disabled:opacity-40"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Footprints size={12} />}
        </button>
      </div>

      <div className="mt-1.5 flex gap-1">
        {MINUTES.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMinutes(m)}
            className={[
              'tnum flex-1 rounded-[7px] px-1 py-1 text-[11px] transition-colors',
              minutes === m
                ? 'bg-[var(--color-ink-blue)] text-white'
                : 'bg-white/70 text-[var(--color-ink-soft)] hover:bg-white',
            ].join(' ')}
          >
            {m} min
          </button>
        ))}
      </div>

      {result ? (
        <div className="mt-2.5 border-t border-[var(--color-hairline)] pt-2">
          <div className="flex items-baseline gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: INK.sites }}
            />
            <span className="text-[11.5px]">
              {result.minutes}-minute walk drawn on the map
            </span>
          </div>
          {result.nodesReached !== undefined && (
            <div className="tnum mt-0.5 pl-4 text-[11px] text-[var(--color-ink-soft)]">
              {result.nodesReached.toLocaleString()} street junctions reachable
            </div>
          )}
          <div className="mt-1 pl-4 text-[10px] leading-snug text-[var(--color-ink-soft)]">
            Measured {result.method}, so it does not cross water or a freeway
            the way a radius would.
          </div>
        </div>
      ) : (
        <p className="mt-2.5 text-[11.5px] leading-relaxed text-[var(--color-ink-soft)]">
          Draw the area a person can actually reach on foot. Useful for testing
          whether a site, a school or a transit stop serves who you think it does.
        </p>
      )}
    </div>
  );
}
