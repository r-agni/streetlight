/**
 * Cross-language contract test.
 *
 * The fixture is produced by the Python encoder. If either side's layout
 * drifts, this fails rather than the browser silently drawing agents in the
 * Gulf of Guinea.
 */
import { describe, expect, it } from 'vitest';
import {
  decodeFrame,
  decodeGridFrame,
  frameKind,
  modeOf,
  personaOf,
  FLAG_HAS_IDS,
} from '../src/index';
import fixture from './fixture.json';

const bytes = (b64: string): ArrayBuffer => {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
};

describe('agent frames encoded by the simulation service', () => {
  const buffer = bytes(fixture.agents.b64);

  it('is recognised as an agent frame', () => {
    expect(frameKind(buffer)).toBe('agents');
  });

  it('round-trips the header', () => {
    const f = decodeFrame(buffer);
    expect(f.tick).toBe(fixture.agents.tick);
    expect(f.minute).toBe(fixture.agents.minute);
    expect(f.count).toBe(fixture.agents.lon.length);
    expect(f.flags & FLAG_HAS_IDS).toBe(0);
  });

  it('round-trips positions, heading and state', () => {
    const f = decodeFrame(buffer);
    fixture.agents.lon.forEach((lon, i) => {
      expect(f.positions[i * 2]).toBeCloseTo(lon, 4);
      expect(f.positions[i * 2 + 1]).toBeCloseTo(fixture.agents.lat[i], 4);
      expect(f.heading[i]).toBe(fixture.agents.heading[i]);
      expect(f.state[i]).toBe(fixture.agents.state[i]);
      expect(f.segment[i]).toBe(fixture.agents.segment[i]);
    });
  });

  it('reads agent ids from a full frame', () => {
    const f = decodeFrame(bytes(fixture.agentsWithIds.b64));
    expect(f.flags & FLAG_HAS_IDS).toBe(FLAG_HAS_IDS);
    expect([...(f.ids ?? [])]).toEqual(fixture.agentsWithIds.ids);
    // positions must still be found after the id block
    expect(f.positions[0]).toBeCloseTo(fixture.agents.lon[0], 4);
  });

  it('unpacks persona and travel mode from the segment byte', () => {
    const f = decodeFrame(buffer);
    fixture.agents.persona.forEach((persona, i) => {
      expect(personaOf(f.segment[i])).toBe(persona);
      expect(modeOf(f.segment[i])).toBe(fixture.agents.mode[i]);
    });
  });

  it('rejects a buffer that is not a frame', () => {
    expect(() => decodeFrame(new ArrayBuffer(32))).toThrow(/magic/);
  });
});

describe('density grid frames', () => {
  const buffer = bytes(fixture.grid.b64);

  it('is recognised as a grid frame', () => {
    expect(frameKind(buffer)).toBe('grid');
  });

  it('round-trips cell indices and counts', () => {
    const g = decodeGridFrame(buffer);
    expect(g.minute).toBe(fixture.grid.minute);
    expect(g.count).toBe(fixture.grid.indices.length);
    expect([...g.indices]).toEqual(fixture.grid.indices);
    expect([...g.values]).toEqual(fixture.grid.values);
  });
});
