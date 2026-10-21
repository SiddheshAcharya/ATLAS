import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "./api";
import type { AtlasEvent } from "./types";

// The full vocabulary from docs/API.md, plus pipeline_finished (ADR-014) — EventSource
// only dispatches to onmessage for unnamed events, so every named `event:` type the
// server sends needs its own addEventListener.
const EVENT_TYPES = [
  "run_started", "harvest_done", "paper_selected", "paper_ingested", "claims_extracted",
  "relation_judged", "bridge_promoted", "pagerank_updated", "frontier_updated",
  "saturation", "gap_found", "report_ready", "error", "run_finished", "pipeline_finished",
  // runs recorded before the event vocabulary was split still carry this one name —
  // EventSource silently drops any event name nobody listens for
  "paper_read",
] as const;

const MAX_LOG = 500;

export interface UseEventsResult {
  events: AtlasEvent[];
  connected: boolean;
  pipelineFinished: boolean;
}

export function useEvents(runId: string | undefined): UseEventsResult {
  const [events, setEvents] = useState<AtlasEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [pipelineFinished, setPipelineFinished] = useState(false);
  const seqRef = useRef(-1);

  useEffect(() => {
    if (!runId) return;
    const id = runId; // narrowed copy — the nested connect() below can't see the guard
    setEvents([]);
    setPipelineFinished(false);
    seqRef.current = -1;

    let cancelled = false;
    let es: EventSource | null = null;
    let retryTimer: number | undefined;
    // A ref, not state: onerror fires on the SSE stream's normal close too (the
    // EventSource spec has no distinct "clean close" signal), and it needs to see
    // this synchronously — a stale closure over the `pipelineFinished` state variable
    // would keep reconnecting forever after a legitimate finish.
    const finishedRef = { current: false };

    function push(type: string, ev: Event) {
      // "error" is a reserved EventSource event name: a native connection failure (or
      // the stream's own normal close) also dispatches an event named "error", but as a
      // plain Event with no `.data`/`.lastEventId` — not the server's business "error"
      // event, which arrives as a MessageEvent. Without this guard, every disconnect
      // shows up in the log as a fake "error (undefined): undefined" entry.
      if (!(ev instanceof MessageEvent)) return;
      const seq = Number(ev.lastEventId);
      if (Number.isFinite(seq)) seqRef.current = Math.max(seqRef.current, seq);
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(ev.data);
      } catch {
        // a malformed payload shouldn't drop the event from the log
      }
      setEvents((prev) => {
        const next = [...prev, { type, seq, payload }];
        return next.length > MAX_LOG ? next.slice(next.length - MAX_LOG) : next;
      });
      if (type === "pipeline_finished") {
        finishedRef.current = true;
        setPipelineFinished(true);
      }
    }

    function connect() {
      if (cancelled) return;
      es = new EventSource(eventsUrl(id, seqRef.current));
      es.onopen = () => setConnected(true);
      for (const t of EVENT_TYPES) {
        es.addEventListener(t, (ev) => push(t, ev));
      }
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (!cancelled && !finishedRef.current) {
          retryTimer = window.setTimeout(connect, 2000);
        }
      };
    }
    connect();

    return () => {
      cancelled = true;
      es?.close();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return { events, connected, pipelineFinished };
}
