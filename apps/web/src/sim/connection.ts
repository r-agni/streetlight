/**
 * The single live connection to the simulation, plus the buffers the renderer
 * reads from. Kept outside React so the sixty-times-a-second path never touches
 * component state.
 */
import { SimConnection } from '../ws/client';
import { Interpolator } from '../ws/interpolator';
import { useSim } from '../state/simStore';
import { useApp } from '../state/appStore';

const WS_URL = import.meta.env.VITE_SIM_WS ?? 'ws://localhost:8000/ws';
export const API_URL = import.meta.env.VITE_SIM_API ?? 'http://localhost:8000';

export const connection = new SimConnection(WS_URL);
export const interpolator = new Interpolator();

let started = false;

export function startConnection(): void {
  if (started) return;
  started = true;

  // the interpolator needs the real snapshot cadence to pace its blending
  connection.onAgentFrame = (prev, next) => interpolator.observe(prev, next);

  connection.onMessage((msg) => {
    const store = useSim.getState();
    switch (msg.type) {
      case 'hello':
        store.setHello({
          nAgents: msg.nAgents,
          bounds: msg.bounds,
          categories: msg.categories,
          segments: msg.segments,
          dataMode: msg.dataMode,
          minute: msg.minute,
          playing: msg.playing,
          speed: msg.speed,
          grid: (msg as unknown as { grid: SimGrid }).grid ?? null,
        });
        break;
      case 'stats':
        store.setStats({
          minute: msg.minute,
          moving: msg.moving,
          dwelling: msg.dwelling,
          atHome: msg.atHome,
          ticksPerSecond: msg.ticksPerSecond,
        });
        break;
      case 'assistantDelta': {
        const app = useApp.getState();
        if (msg.text) app.appendToLast(msg.text);
        if (msg.done) app.setAssistantBusy(false);
        break;
      }
      case 'assistantTool':
        useApp.getState().noteTool(msg.name, msg.status);
        break;
      case 'mapAction':
        applyMapAction(msg as unknown as MapActionEvent);
        break;
      case 'error':
        console.warn('simulation error:', msg.message);
        break;
    }
  });

  connection.connect();
}

interface MapActionEvent {
  action: string;
  payload: Record<string, unknown>;
}

/** Tool side effects: the map reacts while the answer is still being written. */
function applyMapAction(event: MapActionEvent): void {
  const app = useApp.getState();
  const p = event.payload ?? {};
  switch (event.action) {
    case 'flyTo': {
      const fly = (window as unknown as {
        __setView?: (c: [number, number], z: number) => void;
      }).__setView;
      fly?.([Number(p.lon), Number(p.lat)], Number(p.zoom ?? 15));
      break;
    }
    case 'highlight':
      app.setMarkers(
        ((p.markers as { label: string; lon: number; lat: number }[]) ?? []).map((m) => ({
          ...m,
          kind: String(p.kind ?? 'pin'),
        })),
      );
      break;
    case 'event':
      app.setMarkers([
        {
          label: String(p.label ?? 'Event'),
          lon: Number(p.lon),
          lat: Number(p.lat),
          kind: 'event',
        },
      ]);
      app.setEventOrigins((p.origins as [number, number][]) ?? []);
      break;
    case 'setLayer':
      app.setLayerOn(String(p.layer), p.on !== false);
      break;
    case 'setTime':
      useSim.getState().set({ minute: Number(p.minute) });
      break;
    case 'clear':
      app.setMarkers([]);
      app.setCatchmentHull(null);
      app.setEventOrigins([]);
      break;
  }
}

interface SimGrid {
  origin: [number, number];
  step: [number, number];
  shape: [number, number];
}

/** Convert flat grid cell indices into longitude/latitude centre points. */
export function gridCellsToPoints(
  indices: Uint32Array,
  grid: SimGrid,
): Float32Array {
  const [lon0, lat0] = grid.origin;
  const [dlon, dlat] = grid.step;
  const cols = grid.shape[1];
  const out = new Float32Array(indices.length * 2);
  for (let i = 0; i < indices.length; i++) {
    const cell = indices[i];
    const row = Math.floor(cell / cols);
    const col = cell - row * cols;
    out[i * 2] = lon0 + (col + 0.5) * dlon;
    out[i * 2 + 1] = lat0 + (row + 0.5) * dlat;
  }
  return out;
}
