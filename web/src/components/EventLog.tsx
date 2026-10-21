import { useEffect, useRef, useState } from "react";
import type { AtlasEvent } from "../lib/types";

type Line = { text: string; detail?: string };

// Plain-language line for each event (docs/API.md vocabulary + the legacy `paper_read`).
function describe(ev: AtlasEvent): Line {
  const p = ev.payload;
  switch (ev.type) {
    case "run_started":
      return { text: `Started — expanded the question into ${(p.keywords as string[] | undefined)?.length ?? 0} search keywords` };
    case "harvest_done":
      return { text: `Found ${p.n_candidates ?? "?"} candidate papers across four databases` };
    case "paper_selected":
      return { text: `Reading paper #${Number(p.read_order ?? 0) + 1}`, detail: String(p.title ?? p.paper_id ?? "") };
    case "paper_read":
      return {
        text: `Read paper #${Number(p.order ?? 0) + 1} — ${p.claims_kept ?? 0} claims kept`,
        detail: String(p.title ?? p.paper_id ?? ""),
      };
    case "paper_ingested":
      return { text: `Parsed: ${String(p.depth ?? "").replace(/_/g, " ")} (${p.n_chunks ?? 0} text chunks)` };
    case "claims_extracted":
      return { text: `${p.n_kept ?? 0} claims kept, ${p.n_dropped ?? 0} dropped by the grounding gate` };
    case "relation_judged":
      return { text: `Judged a claim pair: ${String(p.type ?? "").toLowerCase().replace("_", " ")}` };
    case "bridge_promoted":
      return { text: "Bridge promotion — a parked paper connects two clusters", detail: String(p.paper_id ?? "") };
    case "pagerank_updated":
      return { text: "Recomputed PageRank and clusters" };
    case "frontier_updated":
      return { text: "Re-scored the reading queue" };
    case "saturation":
      return { text: `New information from this paper: ${p.new_info ?? "?"}` };
    case "gap_found":
      return { text: `Gap #${p.rank ?? "?"} found (${String(p.type ?? "").replace(/_/g, " ")})` };
    case "report_ready":
      return { text: "Report ready" };
    case "error":
      return { text: `Error in ${p.stage ?? "a step"}`, detail: String(p.message ?? "") };
    case "run_finished":
      return { text: `Stopped reading — ${p.stop_reason ?? ""}` };
    case "pipeline_finished":
      return { text: "Finished" };
    default:
      return { text: ev.type };
  }
}

const KEY_EVENTS = new Set([
  "run_started", "harvest_done", "paper_selected", "paper_read", "claims_extracted",
  "bridge_promoted", "gap_found", "report_ready", "error", "run_finished", "pipeline_finished",
]);

const DOT: Record<string, string> = {
  paper_selected: "bg-accent-400",
  paper_read: "bg-accent-400",
  claims_extracted: "bg-emerald-400",
  bridge_promoted: "bg-fuchsia-400",
  gap_found: "bg-amber-400",
  error: "bg-red-400",
  report_ready: "bg-emerald-400",
  pipeline_finished: "bg-emerald-400",
  run_finished: "bg-emerald-400",
};

export default function EventLog({ events }: { events: AtlasEvent[] }) {
  const listRef = useRef<HTMLOListElement>(null);
  const [all, setAll] = useState(false);
  const shown = all ? events : events.filter((e) => KEY_EVENTS.has(e.type));

  useEffect(() => {
    // scroll the list only — scrollIntoView would also scroll the page, which on a phone
    // (graph stacked above the log) jumps past the graph on every new event
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [shown.length]);

  return (
    <div className="flex h-full flex-col">
      <label className="flex items-center gap-2 border-b border-ink-900 px-3 py-1.5 text-xs text-ink-500">
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
        show technical events ({events.length - events.filter((e) => KEY_EVENTS.has(e.type)).length} hidden)
      </label>
      <ol ref={listRef} className="flex-1 overflow-y-auto px-3 py-2 text-sm" aria-live="polite">
        {shown.length === 0 && <li className="text-ink-500">Waiting for events…</li>}
        {shown.map((ev) => {
          const line = describe(ev);
          return (
            <li key={ev.seq} className="flex gap-2.5 py-1">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[ev.type] ?? "bg-ink-600"}`} />
              <div className="min-w-0">
                <div className={ev.type === "error" ? "text-red-300" : "text-ink-300"}>{line.text}</div>
                {line.detail && <div className="truncate text-xs text-ink-500">{line.detail}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
