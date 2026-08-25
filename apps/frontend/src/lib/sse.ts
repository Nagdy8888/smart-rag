/**
 * Fetch SSE framing for FastAPI `text/event-stream` bodies.
 *
 * Unknown event types are returned so callers can log and continue. Terminal
 * types match the backend SSE catalog.
 */

import {
  KNOWN_SSE_EVENT_TYPES,
  TERMINAL_SSE_EVENT_TYPES,
  type KnownSseEventType,
} from "./types";

/** One parsed SSE frame. `id` is the persisted sequence when present. */
export type SseFrame = {
  event: string;
  id: string | null;
  data: string;
};

const KNOWN = new Set<string>(KNOWN_SSE_EVENT_TYPES);
const TERMINAL = new Set<string>(TERMINAL_SSE_EVENT_TYPES);

/**
 * Return whether an event name is in the packet-6 catalog.
 *
 * @param eventType - SSE `event:` field.
 * @returns True for allow-listed types.
 */
export function isKnownSseEvent(eventType: string): eventType is KnownSseEventType {
  return KNOWN.has(eventType);
}

/**
 * Return whether an event name ends the stream.
 *
 * @param eventType - SSE `event:` field.
 * @returns True for completed/cancelled/error/partial.
 */
export function isTerminalSseEvent(eventType: string): boolean {
  return TERMINAL.has(eventType);
}

/**
 * Split a decoded SSE buffer into frames, leaving an incomplete tail.
 *
 * @param buffer - Accumulated UTF-8 text.
 * @returns Complete frames and the unparsed remainder.
 */
export function parseSseBuffer(buffer: string): {
  frames: SseFrame[];
  rest: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const chunks = normalized.split("\n\n");
  const rest = chunks.pop() ?? "";
  const frames: SseFrame[] = [];
  for (const chunk of chunks) {
    if (chunk.trim() === "") {
      continue;
    }
    frames.push(parseSseBlock(chunk));
  }
  return { frames, rest };
}

/**
 * Parse one SSE block of `event`/`id`/`data` lines.
 *
 * @param block - Text between blank lines.
 * @returns Frame. Default event is `message` per the SSE spec.
 */
export function parseSseBlock(block: string): SseFrame {
  let event = "message";
  let id: string | null = null;
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":") || line === "") {
      continue;
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "event") {
      event = value;
    } else if (field === "id") {
      id = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }
  return { event, id, data: dataLines.join("\n") };
}

/**
 * Parse a JSON object payload, or return an empty object on failure.
 *
 * @param data - SSE data field.
 * @returns JSON object when the payload is an object.
 */
export function parseSsePayload(data: string): Record<string, unknown> {
  if (data.trim() === "") {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(data);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return {};
  }
  return {};
}

/**
 * Parse a numeric sequence from `id:` or payload `sequence`.
 *
 * @param frame - Parsed frame.
 * @param payload - JSON payload.
 * @returns Sequence integer, or null.
 */
export function sequenceFromFrame(
  frame: SseFrame,
  payload: Record<string, unknown>,
): number | null {
  if (frame.id !== null && frame.id !== "") {
    const fromId = Number.parseInt(frame.id, 10);
    if (Number.isFinite(fromId)) {
      return fromId;
    }
  }
  const raw = payload.sequence;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw;
  }
  if (typeof raw === "string") {
    const fromPayload = Number.parseInt(raw, 10);
    if (Number.isFinite(fromPayload)) {
      return fromPayload;
    }
  }
  return null;
}
