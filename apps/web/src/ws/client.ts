/**
 * WebSocket connection to the simulation service.
 *
 * Two things arrive here: binary agent frames, which are kept in a small
 * double buffer for interpolation, and JSON control/telemetry messages, which
 * are dispatched to listeners. The socket intentionally keeps only the two
 * newest position frames, so a stalled tab resumes at the live time rather
 * than replaying a backlog.
 */
import {
  decodeFrame,
  decodeGridFrame,
  frameKind,
  type AgentFrame,
  type GridFrame,
  type ServerMessage,
} from '@sfcs/protocol';

export interface TimedFrame extends AgentFrame {
  /** performance.now() when this frame arrived. */
  at: number;
}

type JsonListener = (msg: ServerMessage) => void;

export class SimConnection {
  private socket: WebSocket | null = null;
  private listeners = new Set<JsonListener>();
  private retry = 0;
  private closed = false;

  /** The two newest position frames, oldest first. */
  prev: TimedFrame | null = null;
  next: TimedFrame | null = null;
  grid: GridFrame | null = null;
  gridAt = 0;
  connected = false;

  /** Called with the outgoing and incoming frame whenever a new one lands. */
  onAgentFrame: ((prev: TimedFrame | null, next: TimedFrame) => void) | null = null;

  private readonly url: string;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.closed = false;
    this.open();
  }

  private open(): void {
    const socket = new WebSocket(this.url);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    socket.onopen = () => {
      this.connected = true;
      this.retry = 0;
    };

    socket.onmessage = (event) => {
      if (typeof event.data === 'string') {
        let msg: ServerMessage;
        try {
          msg = JSON.parse(event.data) as ServerMessage;
        } catch {
          return;
        }
        for (const fn of this.listeners) fn(msg);
        return;
      }
      const buffer = event.data as ArrayBuffer;
      switch (frameKind(buffer)) {
        case 'agents': {
          const frame = decodeFrame(buffer) as TimedFrame;
          frame.at = performance.now();
          this.prev = this.next;
          this.next = frame;
          this.onAgentFrame?.(this.prev, frame);
          break;
        }
        case 'grid': {
          this.grid = decodeGridFrame(buffer);
          this.gridAt = performance.now();
          break;
        }
      }
    };

    socket.onclose = () => {
      this.connected = false;
      if (this.closed) return;
      // back off, but stay responsive when the service restarts during development
      const wait = Math.min(4000, 250 * 2 ** this.retry++);
      setTimeout(() => this.open(), wait);
    };

    socket.onerror = () => socket.close();
  }

  onMessage(fn: JsonListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  send(msg: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(msg));
    }
  }

  control(action: string, value?: number): void {
    this.send({ type: 'control', action, value });
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
  }
}
