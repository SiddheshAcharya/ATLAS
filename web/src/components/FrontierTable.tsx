import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { FrontierRow } from "../lib/types";

type SortKey = "score" | "relevance" | "novelty" | "recency" | "pagerank" | "contest";

const STATE_COLOR: Record<string, string> = {
  read: "text-emerald-300",
  reading: "text-amber-300",
  pending: "text-ink-300",
  parked: "text-ink-500",
  dropped: "text-ink-600",
  failed: "text-red-400",
};

function fmt(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

export default function FrontierTable({ runId, rows }: { runId: string; rows: FrontierRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("score");

  const sorted = useMemo(
    () => [...rows].sort((a, b) => (b[sortKey] ?? -1) - (a[sortKey] ?? -1)),
    [rows, sortKey],
  );

  const columns: { key: SortKey; label: string }[] = [
    { key: "score", label: "score" },
    { key: "relevance", label: "rel" },
    { key: "novelty", label: "nov" },
    { key: "recency", label: "rec" },
    { key: "pagerank", label: "pr" },
    { key: "contest", label: "con" },
  ];

  if (rows.length === 0) {
    return <p className="p-6 text-sm text-ink-500">No frontier rows yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-ink-950/95 text-xs uppercase text-ink-500">
          <tr>
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">title</th>
            <th className="px-3 py-2">state</th>
            {columns.map((c) => (
              <th
                key={c.key}
                onClick={() => setSortKey(c.key)}
                className={`cursor-pointer px-3 py-2 hover:text-ink-300 ${
                  sortKey === c.key ? "text-accent-400" : ""
                }`}
                title={`sort by ${c.label}`}
              >
                {c.label}
              </th>
            ))}
            <th className="px-3 py-2">via</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={r.paper_id} className="border-t border-ink-900 hover:bg-ink-900/40">
              <td className="px-3 py-1.5 text-ink-600">{r.read_order ?? i + 1}</td>
              <td className="max-w-sm truncate px-3 py-1.5">
                <Link
                  to={`/runs/${runId}/paper/${encodeURIComponent(r.paper_id)}`}
                  className="hover:text-accent-300 hover:underline"
                  title={r.title}
                >
                  {r.title}
                </Link>
              </td>
              <td className={`px-3 py-1.5 ${STATE_COLOR[r.state] ?? ""}`}>
                {r.state}
                {r.parked_reason ? (
                  <span className="ml-1 text-xs text-ink-600" title={r.parked_reason}>
                    ⓘ
                  </span>
                ) : null}
              </td>
              <td className="px-3 py-1.5 font-medium">{fmt(r.score)}</td>
              <td className="px-3 py-1.5 text-ink-400">{fmt(r.relevance)}</td>
              <td className="px-3 py-1.5 text-ink-400">{fmt(r.novelty)}</td>
              <td className="px-3 py-1.5 text-ink-400">{fmt(r.recency)}</td>
              <td className="px-3 py-1.5 text-ink-400">{fmt(r.pagerank)}</td>
              <td className="px-3 py-1.5 text-ink-400">{fmt(r.contest)}</td>
              <td className="max-w-[10rem] truncate px-3 py-1.5 text-xs text-ink-600" title={r.discovered_via ?? ""}>
                {r.discovered_via ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
