import { MapView } from './map/MapView';
import { PosterCard } from './components/PosterCard';
import { Controls } from './components/Controls';
import { Assistant } from './components/Assistant';
import { LayerPanel } from './components/LayerPanel';
import { AreaPanel } from './components/AreaReport';
import { BusinessPanel } from './components/panels/BusinessPanel';
import { EventsPanel } from './components/panels/EventsPanel';
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
    <div className="card-paper flex gap-1 p-1">
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

export default function App() {
  const mode = useApp((s) => s.mode);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapView />

      {/* deck.gl mounts its own canvas over the map, so the interface needs an
          explicit stacking context to stay above it */}
      <div className="pointer-events-none absolute inset-0 z-20 flex gap-4 p-4">
        <div className="pointer-events-auto flex w-[360px] shrink-0 flex-col gap-3 overflow-y-auto pb-24">
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

        <div className="flex-1" />

        <div className="pointer-events-auto h-full max-h-[calc(100vh-8rem)] shrink-0">
          <Assistant />
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-4 left-1/2 z-20 -translate-x-1/2">
        <div className="pointer-events-auto">
          <Controls />
        </div>
      </div>
    </div>
  );
}
