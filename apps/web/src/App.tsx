/**
 * Application shell.
 *
 * Three zones over a full-bleed map: a tool rail on the left, the map itself in
 * the middle with playback pinned to its bottom edge, and the assistant on the
 * right. Laid out as a grid rather than as absolutely positioned boxes, so the
 * playback bar can never slide underneath a rail and the rails scroll
 * independently instead of running off the bottom of the screen.
 *
 * Both rails collapse, because on a laptop the map is the thing worth seeing
 * and two 350px rails leave little of it.
 */
import { useState } from 'react';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';

import { MapView } from './map/MapView';
import { PosterCard } from './components/PosterCard';
import { Controls } from './components/Controls';
import { Assistant } from './components/Assistant';
import { LayerPanel } from './components/LayerPanel';
import { AreaPanel } from './components/AreaReport';
import { BusinessPanel } from './components/panels/BusinessPanel';
import { EventsPanel } from './components/panels/EventsPanel';
import { PlannerPanel } from './components/panels/PlannerPanel';
import { useApp, type Mode } from './state/appStore';

const MODES: { id: Mode; label: string }[] = [
  { id: 'explore', label: 'Explore' },
  { id: 'business', label: 'Business' },
  { id: 'planner', label: 'Planner' },
  { id: 'events', label: 'Events' },
];

function ModeTabs() {
  const { mode, setMode } = useApp();
  return (
    <div className="card-paper flex shrink-0 gap-1 p-1">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => setMode(m.id)}
          className={[
            'flex-1 rounded-[12px] px-2 py-1.5 text-[11.5px] font-medium transition-colors',
            mode === m.id
              ? 'bg-[var(--color-ink-blue)] text-white'
              : 'text-[var(--color-ink-soft)] hover:bg-white',
          ].join(' ')}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

function RailToggle({
  side,
  open,
  onClick,
}: {
  side: 'left' | 'right';
  open: boolean;
  onClick: () => void;
}) {
  const Icon = side === 'left'
    ? open ? PanelLeftClose : PanelLeftOpen
    : open ? PanelRightClose : PanelRightOpen;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${open ? 'Hide' : 'Show'} the ${side} panel`}
      className="card-paper pointer-events-auto flex h-8 w-8 items-center justify-center text-[var(--color-ink-soft)] transition-colors hover:text-[var(--color-ink-blue)]"
    >
      <Icon size={14} strokeWidth={2} />
    </button>
  );
}

export default function App() {
  const mode = useApp((s) => s.mode);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapView />

      {/* deck.gl mounts its own canvas over the map, so the interface needs an
          explicit stacking context to stay above it. min-h-0 on every track is
          what lets the rails scroll rather than stretch the grid. */}
      <div className="pointer-events-none absolute inset-0 z-20 grid grid-cols-[auto_1fr_auto] gap-3 p-3">
        {/* ---- tools ---- */}
        <div className="flex min-h-0 flex-col gap-2">
          <div className="pointer-events-auto flex shrink-0 items-start gap-2">
            <RailToggle side="left" open={leftOpen} onClick={() => setLeftOpen(!leftOpen)} />
          </div>
          {leftOpen && (
            <div className="pointer-events-auto flex w-[340px] min-h-0 flex-col gap-2 overflow-y-auto pr-0.5">
              <PosterCard />
              <ModeTabs />
              {mode === 'explore' && (
                <>
                  <LayerPanel />
                  <AreaPanel />
                </>
              )}
              {mode === 'business' && (
                <>
                  <BusinessPanel />
                  <AreaPanel />
                </>
              )}
              {mode === 'planner' && (
                <>
                  <PlannerPanel />
                  <LayerPanel />
                  <AreaPanel />
                </>
              )}
              {mode === 'events' && (
                <>
                  <EventsPanel />
                  <LayerPanel />
                </>
              )}
            </div>
          )}
        </div>

        {/* ---- map keeps this column; playback sits on its bottom edge ---- */}
        <div className="flex min-h-0 flex-col justify-end">
          <div className="pointer-events-auto mx-auto w-full max-w-[640px]">
            <Controls />
          </div>
        </div>

        {/* ---- assistant ---- */}
        <div className="flex min-h-0 flex-col gap-2">
          <div className="pointer-events-auto flex shrink-0 justify-end gap-2">
            <RailToggle side="right" open={rightOpen} onClick={() => setRightOpen(!rightOpen)} />
          </div>
          {rightOpen && (
            <div className="pointer-events-auto min-h-0 flex-1">
              <Assistant />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
