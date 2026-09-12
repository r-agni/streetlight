/**
 * Application state.
 *
 * Deliberately excludes agent positions. Those live in a mutable buffer owned
 * by the interpolator and are handed straight to the GPU, because routing
 * 20,000 positions through React sixty times a second would stall the frame.
 * Only low-rate telemetry lands here.
 */
import { create } from 'zustand';

export type PanelMode = 'explore' | 'business' | 'housing' | 'events';
export type DensityMetric = 'live' | 'hour';

export interface GridMeta {
  origin: [number, number];
  step: [number, number];
  shape: [number, number];
}

/** What real moment the simulation minute currently stands for. */
export interface ClockState {
  iso: string;
  minute: number;
  horizon: 'past' | 'live' | 'future';
  dayName: string;
  label: string;
  daysFromNow: number;
  describe?: string;
}

export interface SimState {
  connected: boolean;
  dataMode: string;
  nAgents: number;
  bounds: [number, number, number, number] | null;
  grid: GridMeta | null;
  categories: { id: string; label: string }[];
  segments: string[];

  minute: number;
  clock: ClockState | null;
  setClock: (clock: ClockState) => void;
  playing: boolean;
  speed: number;
  moving: number;
  dwelling: number;
  atHome: number;
  ticksPerSecond: number;

  fps: number;
  frameAge: number;

  mode: PanelMode;
  showDensity: boolean;
  showPlaces: boolean;
  showAgents: boolean;
  densityMetric: DensityMetric;
  selectedAgent: number | null;

  setHello: (p: Partial<SimState>) => void;
  setStats: (p: Partial<SimState>) => void;
  setPerf: (fps: number, frameAge: number) => void;
  set: (p: Partial<SimState>) => void;
}

export const useSim = create<SimState>((set) => ({
  connected: false,
  dataMode: 'loading',
  nAgents: 0,
  bounds: null,
  grid: null,
  categories: [],
  segments: [],

  minute: 500,
  clock: null,
  setClock: (clock) => set({ clock, minute: clock.minute }),
  playing: true,
  speed: 20,
  moving: 0,
  dwelling: 0,
  atHome: 0,
  ticksPerSecond: 0,

  fps: 0,
  frameAge: 0,

  mode: 'explore',
  showDensity: true,
  showPlaces: false,
  showAgents: true,
  densityMetric: 'live',
  selectedAgent: null,

  setHello: (p) => set({ ...p, connected: true }),
  setStats: (p) => set(p),
  setPerf: (fps, frameAge) => set({ fps, frameAge }),
  set: (p) => set(p),
}));

// ------------------------------------------------------------------ helpers

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Split a minute-of-week into its display parts. */
export function clockParts(minuteOfWeek: number) {
  const day = Math.floor(minuteOfWeek / 1440) % 7;
  const minuteOfDay = minuteOfWeek % 1440;
  const hour = Math.floor(minuteOfDay / 60);
  const minute = minuteOfDay % 60;
  return {
    day,
    dayName: DAYS[day],
    hour,
    minute,
    minuteOfDay,
    label: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
  };
}

/** Daylight fraction, used to tint the map between night and midday. */
export function daylight(minuteOfDay: number): number {
  const t = (minuteOfDay / 1440) * Math.PI * 2;
  return Math.max(0, Math.sin(t - Math.PI / 2) * 0.5 + 0.5);
}
