/**
 * Playback: transport controls, a day scrubber and the layer switches.
 *
 * The scrubber writes straight to the service rather than to local state, so
 * the clock shown always reflects what the simulation actually did.
 */
import { Pause, Play } from 'lucide-react';

import { connection } from '../sim/connection';
import { clockParts, useSim } from '../state/simStore';

const SPEEDS = [1, 5, 20, 60, 180];

function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={[
        'tnum rounded-[8px] px-2.5 py-1 text-[11px] font-medium transition-colors',
        active
          ? 'bg-[var(--color-ink-blue)] text-white'
          : 'bg-white/70 text-[var(--color-ink-soft)] hover:bg-white',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

export function Controls() {
  const { minute, playing, speed, showDensity, showAgents, fps, frameAge, ticksPerSecond } =
    useSim();
  const set = useSim((s) => s.set);
  const clock = clockParts(minute);

  const toggledPlay = () => {
    const next = !playing;
    set({ playing: next });
    connection.control(next ? 'play' : 'pause');
  };

  const seek = (minuteOfDay: number) => {
    const target = clock.day * 1440 + minuteOfDay;
    set({ minute: target });
    connection.control('seek', target);
  };

  return (
    <div className="card-paper flex w-[640px] flex-col gap-3 px-5 py-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggledPlay}
          aria-label={playing ? 'Pause' : 'Play'}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-ink-blue)] text-white"
        >
          {playing ? <Pause size={14} strokeWidth={2.4} /> : <Play size={14} strokeWidth={2.4} />}
        </button>

        <div className="tnum font-display text-[20px] leading-none tracking-tight">
          {clock.label}
        </div>
        <div className="eyebrow text-[var(--color-ink-soft)]">{clock.dayName}</div>

        <div className="ml-auto flex items-center gap-1.5">
          {SPEEDS.map((s) => (
            <Chip
              key={s}
              active={speed === s}
              title={`${s} simulated minutes per second`}
              onClick={() => {
                set({ speed: s });
                connection.control('speed', s);
              }}
            >
              {s}&times;
            </Chip>
          ))}
        </div>
      </div>

      {/* day scrubber: the track is the day, the fill is elapsed time */}
      <div className="relative">
        <input
          type="range"
          min={0}
          max={1439}
          value={clock.minuteOfDay}
          onChange={(e) => seek(Number(e.target.value))}
          className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[var(--color-hairline)] accent-[var(--color-ink-blue)]"
          aria-label="Time of day"
        />
        <div className="tnum mt-1.5 flex justify-between text-[9.5px] text-[var(--color-ink-soft)]">
          {['00', '06', '12', '18', '24'].map((h) => (
            <span key={h}>{h}:00</span>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-1.5 border-t border-[var(--color-hairline)] pt-3">
        <Chip active={showAgents} onClick={() => set({ showAgents: !showAgents })}>
          People
        </Chip>
        <Chip active={showDensity} onClick={() => set({ showDensity: !showDensity })}>
          Density
        </Chip>
        <div className="tnum ml-auto text-[10px] text-[var(--color-ink-soft)]">
          {fps} fps &nbsp;·&nbsp; {frameAge} ms &nbsp;·&nbsp; {ticksPerSecond} sim min/s
        </div>
      </div>
    </div>
  );
}
