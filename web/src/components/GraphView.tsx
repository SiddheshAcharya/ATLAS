import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
// @ts-expect-error -- cytoscape-fcose ships no types
import fcose from "cytoscape-fcose";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { cssVar, useTheme } from "../lib/theme";
import type { GraphSnapshot } from "../lib/types";

export interface GraphViewHandle {
  exportPng: () => string | null;
  relayout: () => void;
}

cytoscape.use(fcose);

// docs/API.md: node colour = Louvain cluster, node size = PageRank.
const CLUSTER_COLORS = [
  "#38bdf8", "#f472b6", "#a78bfa", "#4ade80", "#fb923c",
  "#facc15", "#f87171", "#2dd4bf", "#818cf8", "#fb7185",
];

// docs/API.md: edge colour by relation — contradictions red, supports green. CITES is the
// paper-to-paper citation graph; the rest are claim relations rolled up to paper pairs.
const EDGE_STYLES: Record<string, { color: string; label: string; dashed?: boolean }> = {
  CONTRADICTS: { color: "#ef4444", label: "contradicts" },
  SUPPORTS: { color: "#22c55e", label: "supports" },
  REPLICATES: { color: "#14b8a6", label: "replicates" },
  EXTENDS: { color: "#60a5fa", label: "extends" },
  DIFF_SCOPE: { color: "#a1a1aa", label: "different scope", dashed: true },
  CITES: { color: "#475569", label: "cites" },
};

// R6 (docs/RISKS.md): a full fcose layout measured ~12 s at 500 nodes and ~33 s at 1000.
// Below this size a short, position-preserving layout runs on every update; above it new
// nodes are only placed beside their neighbours and a full layout runs on request.
const LIVE_LAYOUT_MAX_NODES = 100;

function clusterColor(clusterId: unknown): string {
  if (typeof clusterId !== "number") return "#8c867b"; // warm grey: reads on black and beige
  const n = CLUSTER_COLORS.length;
  return CLUSTER_COLORS[((clusterId % n) + n) % n];
}

type ElData = Record<string, unknown>;

function nodeData(snapshot: GraphSnapshot): ElData[] {
  const maxPr = Math.max(1e-9, ...snapshot.nodes.map((n) => Number(n.data.pagerank) || 0));
  return snapshot.nodes.map((n) => ({
    ...n.data,
    // explicit flag: a Cytoscape selector like [read_order >= 0] also matches null
    // (JavaScript's null >= 0 is true), which labelled every node
    is_read: typeof n.data.read_order === "number" ? "yes" : "no",
    color: clusterColor(n.data.cluster_id),
    size: 18 + 42 * ((Number(n.data.pagerank) || 0) / maxPr),
  }));
}

function edgeData(snapshot: GraphSnapshot): ElData[] {
  return snapshot.edges.map((e) => {
    const type = typeof e.data.type === "string" ? e.data.type : "CITES";
    const style = EDGE_STYLES[type] ?? EDGE_STYLES.CITES;
    return { ...e.data, type, color: style.color, dashed: style.dashed ? "yes" : "no" };
  });
}

// Built from index.css theme variables, so it is rebuilt when the light/dark theme changes.
function buildStyle(): cytoscape.StylesheetJson {
  return [
    // Papers ATLAS never read (only cited / discovered) are background: small, faded,
    // unlabelled until hovered. The papers it read carry the story on a projector.
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: "mapData(size, 18, 60, 10, 30)",
        height: "mapData(size, 18, 60, 10, 30)",
        opacity: 0.45,
        label: "",
        "font-size": 9,
        color: cssVar("--graph-label"),
        "text-wrap": "ellipsis",
        "text-max-width": "120px",
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-outline-color": cssVar("--graph-label-outline"),
        "text-outline-width": 2,
      },
    },
    {
      selector: 'node[is_read = "yes"]',
      style: {
        width: "data(size)",
        height: "data(size)",
        opacity: 1,
        label: "data(label)",
        "border-width": 2,
        "border-color": cssVar("--graph-read-ring"),
        "z-index": 10,
      },
    },
    { selector: "node.hover", style: { label: "data(label)", opacity: 1, "z-index": 20 } },
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": "data(color)",
        "target-arrow-color": "data(color)",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        opacity: 0.6,
      },
    },
    {
      selector: "edge[type != 'CITES']",
      style: { width: 2.5, opacity: 0.9, "target-arrow-shape": "none" },
    },
    { selector: "edge[dashed = 'yes']", style: { "line-style": "dashed" } },
    {
      selector: "edge[type = 'CITES']",
      style: { "line-color": cssVar("--graph-cites"), "target-arrow-color": cssVar("--graph-cites") },
    },
    {
      selector: "node.flash",
      style: {
        "border-width": 6,
        "border-color": cssVar("--graph-flash"),
        "border-opacity": 1,
        "z-index": 999,
      },
    },
  ] as cytoscape.StylesheetJson;
}

function runLayout(cy: Core, randomize: boolean) {
  cy.layout({
    name: "fcose",
    animate: !randomize,
    animationDuration: 350,
    randomize,
    fit: true,
    padding: 30,
  } as never).run();
}

function GraphView(
  {
    snapshot,
    onNodeClick,
    highlightId,
  }: {
    snapshot: GraphSnapshot | null;
    onNodeClick?: (paperId: string) => void;
    /** a paper to flash, e.g. the one a `bridge_promoted` event just named */
    highlightId?: string | null;
  },
  ref: React.Ref<GraphViewHandle>,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [theme] = useTheme();
  const clickRef = useRef(onNodeClick);
  useEffect(() => {
    clickRef.current = onNodeClick;
  }, [onNodeClick]);

  useImperativeHandle(ref, () => ({
    exportPng: () =>
      cyRef.current?.png({ full: true, scale: 2, bg: cssVar("--graph-png-bg") }) ?? null,
    relayout: () => {
      if (cyRef.current) runLayout(cyRef.current, false);
    },
  }));

  // The container is always rendered (the empty state is an overlay), so Cytoscape can be
  // created on mount even though the first snapshot arrives later.
  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      wheelSensitivity: 0.3,
      style: buildStyle(),
      elements: [],
    });
    cy.on("tap", "node", (evt) => clickRef.current?.(evt.target.id()));
    cy.on("mouseover", "node", (evt) => evt.target.addClass("hover"));
    cy.on("mouseout", "node", (evt) => evt.target.removeClass("hover"));
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  // restyle (colours come from the theme's CSS variables) when the theme flips
  useEffect(() => {
    cyRef.current?.style(buildStyle());
  }, [theme]);

  // Incremental update: keep existing nodes where they are, update their data (PageRank
  // size, cluster colour), place new ones beside their neighbours, drop vanished ones.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !snapshot) return;
    const nodes = nodeData(snapshot);
    const edges = edgeData(snapshot);
    const wasEmpty = cy.nodes().length === 0;
    const keepIds = new Set([...nodes.map((n) => String(n.id)), ...edges.map((e) => String(e.id))]);

    cy.batch(() => {
      cy.elements().filter((el) => !keepIds.has(el.id())).remove();
      const added: ElementDefinition[] = [];
      for (const n of nodes) {
        const existing = cy.getElementById(String(n.id));
        if (existing.nonempty()) existing.data(n);
        else added.push({ group: "nodes", data: n });
      }
      const addedNodes = cy.add(added);
      for (const e of edges) {
        const existing = cy.getElementById(String(e.id));
        if (existing.nonempty()) existing.data(e);
        else cy.add({ group: "edges", data: e });
      }
      if (!wasEmpty) {
        // seed each new node beside the already-placed nodes it connects to
        const extent = cy.extent();
        addedNodes.nodes().forEach((node) => {
          const placed = node.neighborhood().nodes().filter((nb) => !addedNodes.has(nb));
          let base = { x: (extent.x1 + extent.x2) / 2, y: (extent.y1 + extent.y2) / 2 };
          if (placed.nonempty()) {
            base = { x: 0, y: 0 };
            placed.forEach((nb) => {
              base.x += nb.position("x") / placed.length;
              base.y += nb.position("y") / placed.length;
            });
          }
          node.position({ x: base.x + (Math.random() - 0.5) * 60, y: base.y + (Math.random() - 0.5) * 60 });
        });
      }
    });

    if (wasEmpty) runLayout(cy, true);
    else if (cy.nodes().length <= LIVE_LAYOUT_MAX_NODES) runLayout(cy, false);
  }, [snapshot]);

  // Flash once per promotion. A promoted paper is usually still unread (it was parked), so
  // it may only join the graph on a later snapshot — keep waiting for it until then.
  const flashedRef = useRef<string | null>(null);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !highlightId || flashedRef.current === highlightId) return;
    const node = cy.getElementById(highlightId);
    if (node.empty()) return;
    flashedRef.current = highlightId;
    node.addClass("flash");
    cy.animate({ center: { eles: node }, duration: 500 });
    window.setTimeout(() => node.removeClass("flash"), 8000);
  }, [highlightId, snapshot]);

  const empty = !snapshot || snapshot.nodes.length === 0;
  const edgeTypes = new Set(snapshot?.edges.map((e) => String(e.data.type ?? "CITES")) ?? []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" aria-label="Citation and claim-relation graph" />
      {empty && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-500">
          No graph yet — waiting for papers to be read.
        </div>
      )}
      {!empty && (
        <div className="pointer-events-none absolute bottom-2 left-2 flex flex-wrap gap-x-3 gap-y-1 rounded bg-ink-950/80 px-2 py-1 text-[11px] text-ink-400">
          {Object.entries(EDGE_STYLES)
            .filter(([type]) => edgeTypes.has(type))
            .map(([type, s]) => (
              <span key={type} className="flex items-center gap-1">
                <span
                  className="inline-block h-0.5 w-4"
                  style={{
                    background: s.dashed ? "transparent" : s.color,
                    borderTop: s.dashed ? `2px dashed ${s.color}` : undefined,
                  }}
                />
                {s.label}
              </span>
            ))}
          <span>· ringed = read by ATLAS · size = PageRank · colour = cluster</span>
        </div>
      )}
    </div>
  );
}

export default forwardRef(GraphView);
