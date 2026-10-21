import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import EventLog from "../components/EventLog";
import FrontierTable from "../components/FrontierTable";
import GraphView, { type GraphViewHandle } from "../components/GraphView";
import SaturationChart from "../components/SaturationChart";
import { ApiError, getFrontier, getGraph, getTimeline, stopRun } from "../lib/api";
import type { FrontierRow, GraphSnapshot, TimelinePoint } from "../lib/types";
import { useRunContext } from "../lib/runContext";

const GRAPH_REFRESH_ON = new Set([
  "paper_ingested", "frontier_updated", "bridge_promoted", "pagerank_updated", "run_finished",
  "saturation",
]);
const TERMINAL_EVENTS = new Set(["run_finished", "pipeline_finished"]);

// R6 (docs/RISKS.md): a full fcose re-layout measured ~33s at 1000 nodes
// (web/scripts/stress_test_layout.cjs) — stuttery well before that. Below this size, a
// full graph refresh on every relevant event is still what invariant #6
// (CLAUDE.md — "the UI streams it live, never batch the whole graph write to the end")
// requires, and typical runs (6-15 papers) never get near this threshold. Above it,
// throttle refreshes by time so the graph stays live without re-laying-out on every
// single event.
const LARGE_GRAPH_NODE_COUNT = 100;
const LARGE_GRAPH_REFRESH_INTERVAL_MS = 4000;

function TabButton({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-2 py-1 transition-colors ${active ? "bg-ink-800 text-accent-300" : "text-ink-500 hover:text-ink-300"}`}
    >
      {children}
    </button>
  );
}

export default function RunView() {
  const { runId, run, events, pipelineFinished } = useRunContext();
  const navigate = useNavigate();
  const [tab, setTab] = useState<"graph" | "frontier" | "timeline">("graph");
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [frontier, setFrontier] = useState<FrontierRow[]>([]);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [graphNote, setGraphNote] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = graph?.nodes.find((n) => n.data.id === selectedId)?.data ?? null;
  const graphRef = useRef<GraphViewHandle>(null);
  const lastGraphRefreshAt = useRef(0);
  const lastGraphSize = useRef(0);

  // The demo moment (TESTING.md demo arc, step 2): a parked paper promoted because its
  // citations connect two clusters. Keep the latest one to flash in the graph.
  const bridgeEvents = events.filter((e) => e.type === "bridge_promoted");
  const lastBridge = bridgeEvents[bridgeEvents.length - 1];
  const bridgePaperId = lastBridge ? String(lastBridge.payload.paper_id ?? "") : null;
  const bridgeClusters = lastBridge && Array.isArray(lastBridge.payload.clusters)
    ? (lastBridge.payload.clusters as unknown[]).join(" & ")
    : "";

  function onExportGraph() {
    const dataUrl = graphRef.current?.exportPng();
    if (!dataUrl) return;
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `atlas-graph-${runId.slice(0, 8)}.png`;
    a.click();
  }

  function refresh() {
    getGraph(runId)
      .then((g) => {
        setGraph(g);
        setGraphNote(null);
        lastGraphRefreshAt.current = Date.now();
        lastGraphSize.current = g.nodes.length;
      })
      .catch((e) => setGraphNote(e instanceof ApiError && e.status === 409 ? "neo4j not configured for this run" : String(e)));
    getFrontier(runId).then(setFrontier).catch(() => {});
    getTimeline(runId).then(setTimeline).catch(() => {});
  }

  useEffect(refresh, [runId]);

  useEffect(() => {
    const last = events[events.length - 1];
    if (!last || !GRAPH_REFRESH_ON.has(last.type)) return;
    const isSmall = lastGraphSize.current < LARGE_GRAPH_NODE_COUNT;
    const dueForRefresh = Date.now() - lastGraphRefreshAt.current >= LARGE_GRAPH_REFRESH_INTERVAL_MS;
    if (isSmall || dueForRefresh || TERMINAL_EVENTS.has(last.type)) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  async function onStop() {
    setStopping(true);
    try {
      await stopRun(runId);
    } finally {
      setStopping(false);
    }
  }

  return (
    // stacked on small screens (graph above, log below); side by side from lg up
    <div className="grid grid-cols-1 gap-px bg-ink-800 lg:h-full lg:grid-cols-3">
      <div className="flex h-[65vh] flex-col bg-ink-950 lg:col-span-2 lg:h-auto">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-800 px-3 py-1.5">
          <div className="flex gap-1 text-xs">
            <TabButton active={tab === "graph"} onClick={() => setTab("graph")}>
              Graph
            </TabButton>
            <TabButton active={tab === "frontier"} onClick={() => setTab("frontier")}>
              Frontier
            </TabButton>
            <TabButton active={tab === "timeline"} onClick={() => setTab("timeline")}>
              Timeline
            </TabButton>
          </div>
          <div className="flex items-center gap-2">
            {tab === "graph" && !graphNote && graph && graph.nodes.length > 0 && (
              <button
                onClick={() => graphRef.current?.relayout()}
                className="rounded bg-ink-800 px-2 py-1 text-xs text-ink-300 hover:bg-ink-700 transition-colors"
              >
                Re-layout
              </button>
            )}
            {tab === "graph" && !graphNote && graph && graph.nodes.length > 0 && (
              <button
                onClick={onExportGraph}
                className="rounded bg-ink-800 px-2 py-1 text-xs text-ink-300 hover:bg-ink-700 transition-colors"
              >
                Export PNG
              </button>
            )}
            {run?.status === "running" && (
              <button
                onClick={onStop}
                disabled={stopping}
                className="rounded bg-red-500/20 px-2 py-1 text-xs text-red-300 hover:bg-red-500/30 disabled:opacity-40"
              >
                {stopping ? "Stopping…" : "Stop run"}
              </button>
            )}
          </div>
        </div>
        {bridgePaperId && (
          <div className="flex items-center gap-2 border-b border-yellow-400/30 bg-yellow-400/10 px-3 py-1.5 text-xs text-yellow-200">
            <span className="font-semibold">Bridge promotion</span>
            <span className="truncate">
              {bridgeEvents.length > 1 ? `${bridgeEvents.length} so far; latest: ` : ""}
              a parked paper was pulled back into the queue because its citations connect
              clusters {bridgeClusters} ({bridgePaperId})
            </span>
          </div>
        )}
        <div className="flex-1 overflow-hidden">
          {tab === "graph" &&
            (graphNote ? (
              <div className="flex h-full items-center justify-center text-sm text-ink-500">{graphNote}</div>
            ) : (
              <GraphView
                ref={graphRef}
                snapshot={graph}
                highlightId={bridgePaperId}
                onNodeClick={setSelectedId}
              />
            ))}
          {tab === "frontier" && <FrontierTable runId={runId} rows={frontier} />}
          {tab === "timeline" && <SaturationChart points={timeline} />}
        </div>
      </div>

      <div className="flex h-[60vh] flex-col bg-ink-950 lg:h-auto">
        {selected && (
          <PaperPreview
            data={selected}
            onOpen={() => navigate(`/runs/${runId}/paper/${encodeURIComponent(String(selected.id))}`)}
            onClose={() => setSelectedId(null)}
          />
        )}
        <div className="border-b border-ink-800 px-3 py-1.5 text-xs uppercase tracking-wide text-ink-500">
          What ATLAS did {pipelineFinished && <span className="text-emerald-400">· finished</span>}
        </div>
        <div className="flex-1 overflow-hidden">
          <EventLog events={events} />
        </div>
      </div>
    </div>
  );
}

function PaperPreview({
  data, onOpen, onClose,
}: { data: Record<string, unknown>; onOpen: () => void; onClose: () => void }) {
  const read = typeof data.read_order === "number";
  const depth = String(data.depth ?? "not read").replace(/_/g, " ");
  return (
    <div className="border-b border-ink-800 bg-ink-900/60 p-3" role="region" aria-label="Selected paper">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium leading-snug text-ink-100">{String(data.label ?? data.id)}</div>
        <button onClick={onClose} aria-label="Close preview" className="text-ink-500 hover:text-ink-300">
          ✕
        </button>
      </div>
      <div className="mt-1 text-xs text-ink-500">
        {data.year ? `${String(data.year)} · ` : ""}
        {read ? `read #${Number(data.read_order) + 1} · ${depth}` : "cited by what ATLAS read — not read itself"}
        {typeof data.cluster_id === "number" ? ` · cluster ${data.cluster_id}` : ""}
      </div>
      {read && (
        <button
          onClick={onOpen}
          className="mt-2 rounded bg-accent-500 px-2.5 py-1 text-xs font-medium text-ink-950 hover:bg-accent-400"
        >
          Open paper — claims and quotes →
        </button>
      )}
    </div>
  );
}
