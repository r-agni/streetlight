import { MapView } from './map/MapView';
import { PosterCard } from './components/PosterCard';
import { Controls } from './components/Controls';

export default function App() {
  return (
    <div className="relative h-full w-full overflow-hidden">
      <MapView />

      {/* deck.gl mounts its own canvas over the map, so the interface needs an
          explicit stacking context to stay on top of it */}
      <div className="pointer-events-none absolute inset-0 z-20 p-5">
        <div className="pointer-events-auto absolute left-5 top-5">
          <PosterCard />
        </div>
        <div className="pointer-events-auto absolute bottom-5 left-1/2 -translate-x-1/2">
          <Controls />
        </div>
      </div>
    </div>
  );
}
