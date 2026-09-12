/**
 * Character and vehicle sprites for close zooms.
 *
 * Dots are the right representation for a whole city; at street level they say
 * nothing about who is passing. This module turns the interpolated agent
 * buffers into a small, viewport-culled set of animated figures.
 *
 * Two deliberate limits keep it cheap. Only agents inside the current view are
 * considered, and the set is capped, because the honest upper bound on useful
 * characters is a couple of thousand rather than the whole population. Frame
 * choice is arithmetic on a per-agent phase, so no state is kept between
 * frames.
 */
import { modeOf, personaOf, TravelMode } from '@sfcs/protocol';

import type { InterpolatedFrame } from '../ws/interpolator';

export interface SpriteAtlas {
  cell: number;
  frames: number;
  directions: string[];
  people: string[];
  personaColours: Record<string, string>;
  vehicles: string[];
  places: Record<string, string>;
  mapping: Record<string, { x: number; y: number; width: number; height: number }>;
}

/** Below this zoom, a figure is smaller than the dot that replaces it. */
export const SPRITE_ZOOM = 14.9;

/** Above this many on-screen figures the view is a crowd, and dots read better. */
const MAX_SPRITES = 2500;

/** Walk cycles per second of wall-clock time. */
const CYCLES_PER_SECOND = 1.6;

export function makeSpriteBuffer(): Uint32Array {
  return new Uint32Array(MAX_SPRITES);
}

/**
 * Collect the agents worth drawing as figures.
 *
 * `bounds` is the viewport as [west, south, east, north], padded by the caller
 * so figures do not pop in at the edge.
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
    // pavement would misrepresent where street activity actually is
    if (kind[i] === 2) continue;
    const lon = pos[i * 2];
    const lat = pos[i * 2 + 1];
    if (lon < west || lon > east || lat < south || lat > north) continue;
    out[n++] = i;
  }
  return n;
}

/**
 * Which way the figure faces.
 *
 * Heading is degrees counter-clockwise from due east, so the quadrants fall on
 * the diagonals rather than the axes.
 */
export function facingOf(angleDegrees: number): string {
  const a = ((angleDegrees % 360) + 360) % 360;
  if (a >= 45 && a < 135) return 'up';
  if (a >= 135 && a < 225) return 'left';
  if (a >= 225 && a < 315) return 'down';
  return 'right';
}

/** The atlas icon for one agent. */
export function iconNameFor(
  atlas: SpriteAtlas,
  packedSegment: number,
  kindByte: number,
  angleDegrees: number,
  index: number,
  seconds: number,
): string {
  const mode = modeOf(packedSegment);

  // A car or a bicycle carries the one person it is drawn for, so those are
  // literally true. A bus is not: this model has no transit vehicles of its
  // own, riders simply move along streets at a transit speed, and drawing one
  // bus per rider put thousands of buses on residential streets. Riders are
  // therefore drawn as the people they are.
  if (mode === TravelMode.Car) return 'v_car';
  if (mode === TravelMode.Bike) return 'v_bike';

  const persona = atlas.people[personaOf(packedSegment) % atlas.people.length];
  const facing = facingOf(angleDegrees);
  if (kindByte !== 0) return `${persona}_${facing}_0`; // standing at a place

  // an offset per agent stops a whole street stepping in unison
  const phase = (index * 0.37) % 1;
  const f = Math.floor((seconds * CYCLES_PER_SECOND + phase) * atlas.frames) % atlas.frames;
  return `${persona}_${facing}_${f}`;
}

/** Vehicles are drawn nose-up, so rotate them from heading into screen space. */
export function vehicleAngle(angleDegrees: number): number {
  return angleDegrees - 90;
}

/** Whether this agent is drawn as a vehicle rather than a person. */
export function isVehicle(packedSegment: number): boolean {
  const mode = modeOf(packedSegment);
  return mode === TravelMode.Car || mode === TravelMode.Bike;
}

/** Load the atlas mapping produced by scripts/make_sprites.mjs. */
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
