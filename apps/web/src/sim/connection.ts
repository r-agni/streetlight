/**
 * The single live connection to the simulation, plus the buffers the renderer
 * reads from. Kept outside React so the sixty-times-a-second path never touches
 * component state.
 */
import { SimConnection } from '../ws/client';
import { Interpolator } from '../ws/interpolator';
import { useSim } from '../state/simStore';

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
      case 'error':
        console.warn('simulation error:', msg.message);
        break;
    }
  });

  connection.connect();
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
