import { useEffect, useRef, useState } from "react";
import type { RunEvent } from "./types";

export const RUN_EVENT_NAMES = [
  "run.started",
  "message.delta",
  "tool.call",
  "tool.result",
  "agent.step",
  "token.usage",
  "run.retry",
  "run.approval_required",
  "run.approval_resolved",
  "subrun.started",
  "subrun.completed",
  "run.completed",
  "run.failed",
  "run.cancelled",
] as const;

const TERMINAL_EVENTS: Record<string, true> = {
  "run.completed": true,
  "run.failed": true,
  "run.cancelled": true,
};

export interface StreamedRunEvent extends RunEvent {
  raw: string;
}

function parsePayload(raw: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return { value: parsed };
  } catch {
    return { raw };
  }
}

/**
 * Подписка на SSE-поток запуска. Поток закрывается сам на терминальном событии,
 * повторная подписка происходит только при смене runId.
 */
export function useRunStream(runId: string | null | undefined): {
  events: StreamedRunEvent[];
  finished: boolean;
} {
  const [events, setEvents] = useState<StreamedRunEvent[]>([]);
  const [finished, setFinished] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    if (!runId) {
      return;
    }

    setEvents([]);
    setFinished(false);
    seqRef.current = 0;

    const source = new EventSource(`/v1/runs/${encodeURIComponent(runId)}/events`, {
      withCredentials: true,
    });

    const handle = (name: string) => (ev: MessageEvent<string>) => {
      const id = Number(ev.lastEventId);
      const seq = Number.isFinite(id) && id > 0 ? id : seqRef.current + 1;
      seqRef.current = Math.max(seqRef.current, seq);
      const raw = typeof ev.data === "string" ? ev.data : "";
      const entry: StreamedRunEvent = { seq, event: name, data: parsePayload(raw), raw };
      setEvents((prev) => (prev.some((item) => item.seq === seq && item.event === name) ? prev : [...prev, entry]));
      if (TERMINAL_EVENTS[name]) {
        setFinished(true);
        source.close();
      }
    };

    for (const name of RUN_EVENT_NAMES) {
      source.addEventListener(name, handle(name) as EventListener);
    }
    // На случай события без имени
    source.onmessage = handle("message");

    return () => {
      source.close();
    };
  }, [runId]);

  return { events, finished };
}

export function streamedText(events: StreamedRunEvent[]): string {
  return events
    .filter((event) => event.event === "message.delta")
    .map((event) => (typeof event.data.delta === "string" ? event.data.delta : ""))
    .join("");
}

export function formatStreamEvent(event: StreamedRunEvent): string {
  const payload = event.raw || JSON.stringify(event.data);
  return `#${event.seq} ${event.event} ${payload}`;
}
