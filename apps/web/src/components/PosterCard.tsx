/**
 * The signature card.
 *
 * This is the product's whole visual identity in one component: a solid
 * electric-blue rectangle, white headline, a second headline line at 55% white,
 * a short body paragraph, and a two-column footer pairing a bright line with a
 * muted one. Every other panel is a variation on it.
 */
import { clockParts, useSim } from '../state/simStore';

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="tnum text-[15px] leading-tight text-white">{value}</div>
      <div className="eyebrow muted mt-0.5">{label}</div>
    </div>
  );
}

export function PosterCard() {
  const { minute, clock, nAgents, moving, dwelling, dataMode, connected } = useSim();
  const parts = clockParts(minute);
  const people = Math.round((nAgents || 0) * (830_000 / Math.max(nAgents, 1)));

  return (
    <div className="card-blue w-full px-6 py-5 shadow-[0_10px_40px_rgba(11,11,18,0.18)]">
      <div className="font-display text-[26px] leading-[1.06] tracking-tight text-white">
        SAN FRANCISCO
      </div>
      <div className="font-display muted-display text-[26px] leading-[1.06] tracking-tight">
        City Simulation
      </div>

      <p className="mt-4 max-w-[30ch] text-[12.5px] leading-[1.45] text-white/90">
        Synthetic residents, workers and visitors moving on the real street
        network. Foot traffic here is emergent, not drawn.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-y-4">
        <Stat
          label={
            clock?.horizon === 'past'
              ? 'Looking back at'
              : clock?.horizon === 'future'
                ? 'Projecting'
                : 'Now in San Francisco'
          }
          value={clock?.label ?? `${parts.dayName.slice(0, 3)} ${parts.label}`}
        />
        <Stat label="People modelled" value={people.toLocaleString()} />
        <Stat label="On the move" value={moving.toLocaleString()} />
        <Stat label="At a place" value={dwelling.toLocaleString()} />
      </div>

      <div className="faint mt-6 flex items-center justify-between border-t border-white/15 pt-3 text-[10px] uppercase tracking-[0.09em]">
        <span>{connected ? `${dataMode} data` : 'connecting'}</span>
        <span className="tnum">{(nAgents || 0).toLocaleString()} agents</span>
      </div>
    </div>
  );
}
