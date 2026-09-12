/**
 * Smooth the 6 Hz position stream up to display rate.
 *
 * The service sends positions a few times a second; the browser draws sixty.
 * Each animation frame we blend the two newest snapshots into reusable buffers,
 * so agents glide along their routes instead of stepping. Rendering
 * deliberately lags one snapshot behind live, which is what makes the motion
 * continuous rather than predictive.
 *
 * Three things here exist because the naive version looks wrong:
 *
 *  - Blend progress comes from a smoothed estimate of the snapshot interval,
 *    not from the gap between the last two arrival timestamps. Using arrival
 *    times directly makes every agent in the city speed up and slow down with
 *    network jitter.
 *  - A jump in simulated time means the clock was scrubbed or the day rolled
 *    over. Interpolating across that would drag fifty thousand agents in
 *    straight lines across San Francisco, so it snaps instead.
 *  - Heading blends the short way around the circle. Without that, an agent
 *    turning past due north spins a full revolution several times a second.
 */
import type { TimedFrame } from './client';

export interface InterpolatedFrame {
  /** Interleaved longitude/latitude, length 2 * count. Reused between frames. */
  positions: Float32Array;
  /** Per-agent colour index: 0 travelling, 1 dwelling, 2 at home. */
  kind: Uint8Array;
  /** Heading in degrees, blended the short way around. */
  angle: Float32Array;
  /** Persona segment, for choosing a character sprite. */
  segment: Uint8Array;
  count: number;
  /** How stale the newest snapshot is, in milliseconds. */
  age: number;
  /** True when this frame snapped rather than blended. */
  snapped: boolean;
}

/** Simulated minutes between snapshots beyond which we assume a time jump. */
const JUMP_MINUTES = 20;

/** How quickly the interval estimate follows a change in the real cadence. */
const INTERVAL_SMOOTHING = 0.12;

export class Interpolator {
  private positions = new Float32Array(0);
  private kind = new Uint8Array(0);
  private angle = new Float32Array(0);
  private lastCount = -1;
  private intervalMs = 167; // one frame at the service's default 6 Hz

  /** Bumped whenever the buffers change, to drive deck.gl attribute uploads. */
  revision = 0;

  private ensure(count: number): void {
    if (count === this.lastCount) return;
    this.positions = new Float32Array(count * 2);
    this.kind = new Uint8Array(count);
    this.angle = new Float32Array(count);
    this.lastCount = count;
  }

  /** Note the real cadence between snapshots, ignoring obvious outliers. */
  observe(prev: TimedFrame | null, next: TimedFrame): void {
    if (!prev) return;
    const gap = next.at - prev.at;
    if (gap > 20 && gap < 2000) {
      this.intervalMs += (gap - this.intervalMs) * INTERVAL_SMOOTHING;
    }
  }

  sample(prev: TimedFrame | null, next: TimedFrame | null, now: number): InterpolatedFrame | null {
    if (!next) return null;
    this.ensure(next.count);

    const n = next.count;
    const out = this.positions;
    const angle = this.angle;

    const minuteGap = prev ? Math.abs(next.minute - prev.minute) : 0;
    const continuous =
      prev !== null && prev.count === n && minuteGap <= JUMP_MINUTES;

    if (!continuous) {
      out.set(next.positions);
      for (let i = 0; i < n; i++) angle[i] = (next.heading[i] * 360) / 256;
    } else {
      const alpha = Math.min(1, Math.max(0, (now - next.at) / this.intervalMs));
      const a = prev!.positions;
      const b = next.positions;
      for (let i = 0; i < n * 2; i++) {
        const from = a[i];
        out[i] = from + (b[i] - from) * alpha;
      }
      const ha = prev!.heading;
      const hb = next.heading;
      for (let i = 0; i < n; i++) {
        const from = ha[i];
        // shortest signed step around a 256-unit circle
        const delta = (((hb[i] - from + 128) % 256) + 256) % 256 - 128;
        const blended = (((from + delta * alpha) % 256) + 256) % 256;
        angle[i] = (blended * 360) / 256;
      }
    }

    // state 2 is travelling, 0 is at home; anything else is dwelling
    const state = next.state;
    const kind = this.kind;
    for (let i = 0; i < n; i++) {
      const s = state[i];
      kind[i] = s === 2 ? 0 : s === 0 ? 2 : 1;
    }

    this.revision++;
    return {
      positions: out,
      kind,
      angle,
      segment: next.segment,
      count: n,
      age: now - next.at,
      snapped: !continuous,
    };
  }
}
