/**
 * Character and vehicle sprites for close zooms.
 *
 * Dots are the right representation for a whole city; at street level they say
 * nothing about who is passing. This module turns the interpolated agent
 * buffers into a small, viewport-culled set of animated figures.
 *
 * Two deliberate limits keep it cheap. Only agents inside the current view are
 * considered, and the set is capped, because the honest upper bound on useful
 * characters is a few thousand rather than the whole population. Frame choice
 * is plain arithmetic on a phase offset, so no per-agent state is kept between
 * frames.
 */
import { modeOf, personaOf, TravelMode } from '@sfcs/protocol';

import type { InterpolatedFrame } from '../ws/interpolator';

export interface SpriteAtlas {
  cell: number;
  frames: number;
  people: string[];
  vehicles: string[];
  mapping: Record<string, { x: number; y: number; width: number; height: number }>;
}

/** Below this zoom, individual figures are smaller than the dot that replaces them. */
export const SPRITE_ZOOM = 14.9;

/** Above this many on-screen figures, the view is a crowd and dots read better. */
const MAX_SPRITES = 4000;

/** Walk cycles per simulated minute of travel. */
const CYCLES_PER_SECOND = 1.35;

export interface SpriteSet {
  /** Indices into the interpolated buffers, one per drawn figure. */
  indices: Uint32Array;
  count: number;
}

/**
 * Collect the agents worth drawing as figures.
 *
 * `bounds` is the current viewport as [west, south, east, north], padded by the
 * caller so figures do not pop in at the edge.
 */
export function collectSprites(
  frame: InterpolatedFrame,
  bounds: [number, number, number, number],
  out: Uint32Array,
): number {
  const [west, south, east, north] = bounds;
  const pos = frame.positions;
  const kind = frame.kind;
  let n = 0;

  for (let i = 0; i < frame.count && n < out.length; i++) {
    // people resting at home are inside buildings; drawing them on the
    // pavement would misrepresent where the street activity actually is
    if (kind[i] === 2) continue;
    const lon = pos[i * 2];
    const lat = pos[i * 2 + 1];
    if (lon < west || lon > east || lat < south || lat > north) continue;
    out[n++] = i;
  }
  return n;
}

export function makeSpriteBuffer(): Uint32Array {
  return new Uint32Array(MAX_SPRITES);
}

/**
 * Pick the atlas icon for one agent.
 *
 * `seconds` is wall-clock time, so the cycle keeps running smoothly regardless
 * of how fast the simulation clock is set.
 */
export function iconNameFor(
  atlas: SpriteAtlas,
  packedSegment: number,
  kindByte: number,
  angleDegrees: number,
  index: number,
  seconds: number,
): string {
  const facing = angleDegrees > 90 && angleDegrees < 270 ? 'l' : 'r';
  const mode = modeOf(packedSegment);

  if (mode === TravelMode.Transit) return `bus_${Math.floor(seconds * 4) % 2}_${facing}`;
  if (mode === TravelMode.Car) return `car_${Math.floor(seconds * 6) % 2}_${facing}`;
  if (mode === TravelMode.Bike) return `bike_${Math.floor(seconds * 5) % 2}_${facing}`;

  const persona = atlas.people[personaOf(packedSegment) % atlas.people.length];
  if (kindByte !== 0) return `${persona}_0_${facing}`; // standing still

  // an offset per agent stops a whole street stepping in unison
  const phase = (index * 0.37) % 1;
  const f = Math.floor((seconds * CYCLES_PER_SECOND + phase) * atlas.frames) % atlas.frames;
  return `${persona}_${f}_${facing}`;
}

/** Load the atlas image and its mapping, produced by scripts/make_sprites.mjs. */
export async function loadAtlas(base = '/sprites'): Promise<SpriteAtlas | null> {
  try {
    const res = await fetch(`${base}/atlas.json`);
    if (!res.ok) throw new Error(`atlas ${res.status}`);
    return (await res.json()) as SpriteAtlas;
  } catch (err) {
    console.warn('sprite atlas unavailable; staying with dots', err);
    return null;
  }
}
