/**
 * Wire protocol shared by the simulation service and the browser.
 *
 * Agent positions travel as a binary struct-of-arrays frame so the browser can
 * hand the coordinate buffer straight to the GPU with no per-agent parsing.
 * Everything else travels as JSON text frames.
 */

export const FRAME_MAGIC = 0x5346; // "SF"
export const FRAME_VERSION = 2;
export const HEADER_BYTES = 16;

/** Frame header flag bits. */
export const FLAG_HAS_IDS = 1 << 0; // full frame: agent ids are included
export const FLAG_POPULATION_CHANGED = 1 << 1; // agent set changed since last frame

/** Agent movement states. Values are wire-stable. */
export const AgentState = {
  Home: 0,
  Dwell: 1,
  Travel: 2,
  WaitTransit: 3,
  Hidden: 4,
} as const;
export type AgentStateValue = (typeof AgentState)[keyof typeof AgentState];

/** Travel modes. Values are wire-stable. */
export const TravelMode = {
  Walk: 0,
  Bike: 1,
  Transit: 2,
  Car: 3,
} as const;
export type TravelModeValue = (typeof TravelMode)[keyof typeof TravelMode];

export interface AgentFrame {
  tick: number;
  /** Minute of the simulated week, 0 to 10079. */
  minute: number;
  count: number;
  flags: number;
  /** Interleaved longitude/latitude pairs, length 2 * count. */
  positions: Float32Array;
  /** Heading quantised to 0-255 over the full circle. */
  heading: Uint8Array;
  /** One {@link AgentState} per agent. */
  state: Uint8Array;
  /**
   * Packed persona and travel mode per agent: the low three bits are the
   * persona segment, the next two are the {@link TravelMode} of the current
   * leg. Unpack with {@link personaOf} and {@link modeOf}.
   */
  segment: Uint8Array;
  /** Present only on full frames. */
  ids?: Uint32Array;
}

/** Decode a binary agent frame. Views alias the incoming buffer; copy if retained. */
export function decodeFrame(buffer: ArrayBuffer): AgentFrame {
  const head = new DataView(buffer);
  const magic = head.getUint16(0, true);
  if (magic !== FRAME_MAGIC) {
    throw new Error(`bad frame magic 0x${magic.toString(16)}`);
  }
  const version = head.getUint8(2);
  if (version !== FRAME_VERSION) {
    throw new Error(`unsupported frame version ${version}`);
  }
  const flags = head.getUint8(3);
  const tick = head.getUint32(4, true);
  const minute = head.getUint32(8, true);
  const count = head.getUint32(12, true);

  let offset = HEADER_BYTES;
  let ids: Uint32Array | undefined;
  if (flags & FLAG_HAS_IDS) {
    ids = new Uint32Array(buffer, offset, count);
    offset += count * 4;
  }
  const positions = new Float32Array(buffer, offset, count * 2);
  offset += count * 8;
  const heading = new Uint8Array(buffer, offset, count);
  offset += count;
  const state = new Uint8Array(buffer, offset, count);
  offset += count;
  const segment = new Uint8Array(buffer, offset, count);

  return { tick, minute, count, flags, positions, heading, state, segment, ids };
}

export const GRID_MAGIC = 0x4744; // "GD"

export interface GridFrame {
  minute: number;
  count: number;
  /** Flat row-major cell indices with a non-zero count. */
  indices: Uint32Array;
  /** Agent count in each listed cell. */
  values: Uint16Array;
}

/** Decode a density-grid frame. Views alias the incoming buffer. */
export function decodeGridFrame(buffer: ArrayBuffer): GridFrame {
  const head = new DataView(buffer);
  const minute = head.getUint32(8, true);
  const count = head.getUint32(12, true);
  const indices = new Uint32Array(buffer, HEADER_BYTES, count);
  const values = new Uint16Array(buffer, HEADER_BYTES + count * 4, count);
  return { minute, count, indices, values };
}

/** Which kind of binary frame this buffer holds. */
export function frameKind(buffer: ArrayBuffer): 'agents' | 'grid' | 'unknown' {
  const magic = new DataView(buffer).getUint16(0, true);
  if (magic === FRAME_MAGIC) return 'agents';
  if (magic === GRID_MAGIC) return 'grid';
  return 'unknown';
}

/** Byte length of a frame carrying `count` agents. */
export function frameByteLength(count: number, hasIds: boolean): number {
  const ids = hasIds ? count * 4 : 0;
  const body = ids + count * 8 + count * 3;
  return HEADER_BYTES + body + ((4 - (body % 4)) % 4);
}

// ------------------------------------------------------------------ messages

export interface HelloMessage {
  type: 'hello';
  runId: string;
  nAgents: number;
  minute: number;
  speed: number;
  playing: boolean;
  bounds: [number, number, number, number];
  categories: { id: string; label: string }[];
  segments: string[];
  archetypes: { id: number; label: string }[];
  dataMode: string;
}

export interface StatsMessage {
  type: 'stats';
  minute: number;
  tick: number;
  moving: number;
  dwelling: number;
  atHome: number;
  ticksPerSecond: number;
  /** Busiest cells this minute: H3 index and person count. */
  topCells: { cell: string; count: number }[];
}

export interface CountersMessage {
  type: 'counters';
  kind: 'hex' | 'poi' | 'edge';
  hour: number;
  /** H3 cell index or entity id. */
  keys: string[];
  values: number[];
}

export interface PromptMessage {
  type: 'prompt';
  id: string;
  kind: string;
  title: string;
  body: string;
  actions: { label: string; action: string; payload?: unknown }[];
}

export interface MapActionMessage {
  type: 'mapAction';
  action: 'flyTo' | 'highlight' | 'setLayer' | 'showCard' | 'clear';
  payload: Record<string, unknown>;
}

export interface AssistantDeltaMessage {
  type: 'assistantDelta';
  text: string;
  done?: boolean;
}

export interface AssistantToolMessage {
  type: 'assistantTool';
  name: string;
  status: 'start' | 'ok' | 'error';
  summary?: string;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export type ServerMessage =
  | HelloMessage
  | StatsMessage
  | CountersMessage
  | PromptMessage
  | MapActionMessage
  | AssistantDeltaMessage
  | AssistantToolMessage
  | ErrorMessage;

export interface ControlMessage {
  type: 'control';
  action: 'play' | 'pause' | 'seek' | 'speed' | 'frameHz';
  value?: number;
}

export interface AskMessage {
  type: 'ask';
  text: string;
  context?: Record<string, unknown>;
}

export interface PromptReplyMessage {
  type: 'promptReply';
  id: string;
  action: string;
}

export type ClientMessage = ControlMessage | AskMessage | PromptReplyMessage;

/** Persona index from a packed segment byte. */
export const personaOf = (packed: number): number => packed & 0x07;

/** Travel mode from a packed segment byte. */
export const modeOf = (packed: number): number => (packed >> 3) & 0x03;

/** Persona segment labels, indexed by the segment byte on each agent. */
export const SEGMENT_LABELS = [
  'Office worker',
  'Tech commuter',
  'Student',
  'Service worker',
  'Remote worker',
  'Retiree',
  'Visitor',
  'Other',
] as const;
