/**
 * Where to open something.
 *
 * Candidates are real parcels registered under San Francisco's commercial
 * vacancy tax, not invented points. Scores are relative to the set being
 * compared, which the panel states, because a score with no comparison group
 * invites being read as an absolute grade.
 */
import { Loader2, Search } from 'lucide-react';

import { api } from '../../lib/api';
import { INK } from '../../lib/palette';
import { useApp } from '../../state/appStore';

const CATEGORIES = [
  'cafe', 'restaurant', 'bar', 'grocery', 'retail',
  'clothing', 'gym', 'pharmacy', 'hotel', 'fast_food',
];

const COMPONENT_LABEL: Record<string, string> = {
  footfall: 'Footfall',
  catchment: '10-min walk',
  complement: 'Complements',
  headroom: 'Headroom',
};

export function BusinessPanel() {
  const {
    siteCategory, siteNear, sites, sitesLoading, selectedSite,
    setSiteQuery, setSites, setSitesLoading, selectSite,
    setMarkers, setCatchmentHull,
  } = useApp();

  const run = async () => {
    setSitesLoading(true);
    setCatchmentHull(null);
    try {
      const result = await api.sites(siteCategory, siteNear, 8);
      setSites(result.ranked ?? []);
      setMarkers(
        (result.ranked ?? []).map((s) => ({
          label: `${s.rank}`,
          lon: s.location[0],
          lat: s.location[1],
          kind: 'site',
        })),
      );
    } catch {
      setSites([]);
    }
  };

  const choose = async (rank: number, lon: number, lat: number) => {
    selectSite(rank);
    try {
      const c = await api.catchment(lon, lat, 10);
      setCatchmentHull(c.hull ?? null);
    } catch {
      setCatchmentHull(null);
    }
    (window as unknown as Record<string, unknown> & {
      __setView?: (c: [number, number], z: number) => void;
    }).__setView?.([lon, lat], 16);
  };

  return (
    <div className="card-paper flex flex-col px-4 py-3">
      <div className="eyebrow mb-2 text-[var(--color-ink-soft)]">Find a site</div>

      <div className="flex gap-1.5">
        <select
          value={siteCategory}
          onChange={(e) => setSiteQuery(e.target.value, siteNear)}
          className="rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5 text-[12px] outline-none focus:border-[var(--color-ink-blue)]"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c.replace('_', ' ')}
            </option>
          ))}
        </select>
        <input
          value={siteNear}
          onChange={(e) => setSiteQuery(siteCategory, e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder="neighbourhood"
          className="min-w-0 flex-1 rounded-[8px] border border-[var(--color-hairline)] bg-white px-2 py-1.5 text-[12px] outline-none focus:border-[var(--color-ink-blue)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={sitesLoading}
          className="flex items-center gap-1 rounded-[8px] bg-[var(--color-ink-blue)] px-2.5 text-[12px] font-medium text-white disabled:opacity-40"
        >
          {sitesLoading ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
        </button>
      </div>

      {sitesLoading && (
        <div className="mt-3 text-[11.5px] text-[var(--color-ink-soft)]">
          Scoring vacant parcels. Each one needs a walking catchment, so this
          takes a few seconds.
        </div>
      )}

      {!sitesLoading && !sites.length && (
        <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--color-ink-soft)]">
          Candidates are parcels registered under the commercial vacancy tax.
          Pick a category and a neighbourhood to rank them.
        </p>
      )}

      <div className="mt-2 max-h-[46vh] space-y-1.5 overflow-y-auto">
        {sites.map((site) => {
          const open = selectedSite === site.rank;
          return (
            <button
              key={site.candidateId}
              type="button"
              onClick={() => choose(site.rank, site.location[0], site.location[1])}
              className={[
                'w-full rounded-[10px] border px-2.5 py-2 text-left transition-colors',
                open
                  ? 'border-[var(--color-ink-blue)] bg-white'
                  : 'border-[var(--color-hairline)] bg-white/60 hover:bg-white',
              ].join(' ')}
            >
              <div className="flex items-baseline gap-2">
                <span
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold text-white"
                  style={{ background: INK.sites }}
                >
                  {site.rank}
                </span>
                <span className="truncate text-[11.5px] font-medium">
                  {site.address || 'Unnamed parcel'}
                </span>
                <span className="tnum ml-auto text-[13px] font-semibold">{site.score}</span>
              </div>

              {open && (
                <div className="mt-2 space-y-2">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
                    <span className="text-[var(--color-ink-soft)]">Peak footfall</span>
                    <span className="tnum text-right">
                      {site.modelledPeakFootfall.toLocaleString()}
                    </span>
                    <span className="text-[var(--color-ink-soft)]">Within 10-min walk</span>
                    <span className="tnum text-right">
                      {site.walkCatchmentResidents.toLocaleString()}
                    </span>
                    <span className="text-[var(--color-ink-soft)]">Competitors</span>
                    <span className="tnum text-right">{site.competitorsWithinRadius}</span>
                    <span className="text-[var(--color-ink-soft)]">Complements</span>
                    <span className="tnum text-right">{site.complementaryPlaces}</span>
                  </div>

                  <div className="space-y-1">
                    {Object.entries(site.components).map(([key, c]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className="w-[68px] shrink-0 text-[10px] text-[var(--color-ink-soft)]">
                          {COMPONENT_LABEL[key] ?? key}
                        </span>
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-hairline)]">
                          <span
                            className="block h-full rounded-full"
                            style={{
                              width: `${Math.round(c.relative * 100)}%`,
                              background: INK.people,
                            }}
                          />
                        </span>
                        <span className="tnum w-6 shrink-0 text-right text-[9.5px] text-[var(--color-ink-soft)]">
                          {Math.round(c.weight * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>

                  <p className="text-[10.5px] leading-snug text-[var(--color-ink-soft)]">
                    {site.reading}
                  </p>
                </div>
              )}
            </button>
          );
        })}
      </div>

      {!!sites.length && (
        <p className="mt-2 border-t border-[var(--color-hairline)] pt-2 text-[10px] leading-snug text-[var(--color-ink-soft)]">
          Scores are relative to these {sites.length} candidates, not absolute.
          Footfall and catchment are model output; vacancy is a filed record.
        </p>
      )}
    </div>
  );
}
