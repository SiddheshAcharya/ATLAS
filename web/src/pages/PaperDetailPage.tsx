import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPaper, getPaperSource } from "../lib/api";
import type { Claim, PaperDetail, PaperSource } from "../lib/types";
import { useRunContext } from "../lib/runContext";
import { decodeEntities } from "../lib/text";

const RELATION_COLOR: Record<string, string> = {
  SUPPORTS: "text-emerald-300",
  CONTRADICTS: "text-red-400",
  EXTENDS: "text-accent-300",
  REPLICATES: "text-violet-300",
  DIFF_SCOPE: "text-amber-300",
  UNRELATED: "text-ink-500",
};

const squash = (s: string) => s.replace(/\s+/g, " ").trim();

/** Does the source text at the claim's recorded offsets read exactly like its quote? */
function matchesSource(c: Claim, source: PaperSource | null): "exact" | "differs" | "unknown" {
  if (!source || c.quote_char_start == null || c.quote_char_end == null) return "unknown";
  const span = source.text.slice(c.quote_char_start, c.quote_char_end);
  return squash(span) === squash(c.quote) ? "exact" : "differs";
}

/** The source text split into plain runs and quote highlights (overlaps are merged). */
function segments(text: string, claims: Claim[]) {
  const spans = claims
    .filter((c) => c.quote_char_start != null && c.quote_char_end != null)
    .map((c) => ({ start: c.quote_char_start!, end: c.quote_char_end!, id: c.claim_id }))
    .sort((a, b) => a.start - b.start);
  const out: { text: string; ids: string[] }[] = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start < pos) {
      // overlapping quote: extend the previous highlight to cover it
      const last = out[out.length - 1];
      if (last && s.end > pos) {
        last.text += text.slice(pos, s.end);
        pos = s.end;
      }
      last?.ids.push(s.id);
      continue;
    }
    if (s.start > pos) out.push({ text: text.slice(pos, s.start), ids: [] });
    out.push({ text: text.slice(s.start, s.end), ids: [s.id] });
    pos = s.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), ids: [] });
  return out;
}

export default function PaperDetailPage() {
  const { runId } = useRunContext();
  const { paperId } = useParams<{ paperId: string }>();
  const [detail, setDetail] = useState<PaperDetail | null>(null);
  const [source, setSource] = useState<PaperSource | null>(null);
  const [sourceNote, setSourceNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const sourceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!paperId) return;
    getPaper(runId, paperId)
      .then(setDetail)
      .catch((e) => setError(String(e)));
    getPaperSource(runId, paperId)
      .then(setSource)
      .catch(() => setSourceNote("ATLAS kept no stored text for this paper in this run."));
  }, [runId, paperId]);

  const parts = useMemo(
    () => (source && detail ? segments(source.text, detail.claims) : []),
    [source, detail],
  );

  useEffect(() => {
    if (!selected) return;
    sourceRef.current
      ?.querySelector(`[data-claims~="${CSS.escape(selected)}"]`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);

  if (error) return <p className="p-6 text-sm text-red-400">{error}</p>;
  if (!detail) return <p className="p-6 text-sm text-ink-500">Loading…</p>;

  const { paper, claims, relations } = detail;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <Link to={`/runs/${runId}`} className="text-xs text-ink-500 transition-colors hover:text-accent-400">
        ← back to run
      </Link>
      <h1 className="mt-2 max-w-4xl text-3xl leading-tight font-semibold text-ink-50">{decodeEntities(paper.title)}</h1>
      <p className="mt-1 text-sm text-ink-500">
        {paper.authors.map((a) => decodeEntities(a.name)).join(", ") || "unknown authors"}
        {paper.year ? ` · ${paper.year}` : ""}
        {paper.venue ? ` · ${decodeEntities(paper.venue)}` : ""}
        {" · "}
        <span className="uppercase">{paper.depth.replace("_", " ")}</span>
      </p>
      {paper.doi && (
        <a
          href={`https://doi.org/${paper.doi.replace(/^doi:/, "")}`}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-block text-xs text-accent-400 hover:underline"
        >
          {paper.doi}
        </a>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-400">
            Claims ({claims.length}) <span className="normal-case text-ink-600">· click one to find its quote</span>
          </h2>
          {claims.length === 0 && (
            <p className="text-sm text-ink-500">No claims survived grounding for this paper.</p>
          )}
          <div className="space-y-3">
            {claims.map((c) => {
              const match = matchesSource(c, source);
              const active = selected === c.claim_id;
              return (
                <button
                  key={c.claim_id}
                  onClick={() => setSelected(active ? null : c.claim_id)}
                  aria-pressed={active}
                  className={`block w-full rounded-lg border p-4 text-left transition ${
                    active ? "border-yellow-300/70 bg-yellow-300/5" : "border-ink-800 bg-ink-900/40 hover:border-ink-700"
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-ink-500">
                    <span className="rounded bg-ink-800 px-1.5 py-0.5">{c.section}</span>
                    {c.verified ? (
                      <span className="text-emerald-400">verified · {c.verify_method}</span>
                    ) : (
                      <span className="text-red-400">unverified</span>
                    )}
                    {match === "exact" && <span className="text-emerald-400/80">· quote found verbatim in source</span>}
                    {match === "differs" && <span className="text-amber-300">· source span differs (fuzzy match)</span>}
                  </div>
                  <p className="text-sm text-ink-200">{c.text}</p>
                  <blockquote className="mt-2 border-l-2 border-accent-500/60 bg-accent-500/5 px-3 py-1.5 text-sm italic text-accent-200">
                    “{c.quote}”
                  </blockquote>
                </button>
              );
            })}
          </div>
        </div>

        <div className="lg:sticky lg:top-4 lg:self-start">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-400">
            The text ATLAS read
            {source && (
              <span className="ml-2 normal-case text-ink-600">
                {source.text.length.toLocaleString()} chars · {source.sections.map((s) => s.name).join(", ")}
              </span>
            )}
          </h2>
          {sourceNote && <p className="text-sm text-ink-500">{sourceNote}</p>}
          {source && source.origin !== "this_run" && (
            <p className="mb-2 text-xs text-ink-500">
              {source.origin === "abstract"
                ? "Rebuilt from the stored abstract (normalized exactly as ATLAS read it)."
                : "This paper's stored text is labelled with a later run that re-read it; shown here from that copy."}
            </p>
          )}
          {!source && !sourceNote && <p className="text-sm text-ink-500">Loading source…</p>}
          {source && (
            <div
              ref={sourceRef}
              className="max-h-[70vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-ink-800 bg-ink-950 p-4 text-sm leading-relaxed text-ink-400"
            >
              {parts.map((p, i) =>
                p.ids.length ? (
                  <mark
                    key={i}
                    data-claims={p.ids.join(" ")}
                    className={`rounded px-0.5 ${
                      selected && p.ids.includes(selected)
                        ? "bg-yellow-300 text-ink-950"
                        : "bg-accent-500/20 text-accent-100"
                    }`}
                  >
                    {p.text}
                  </mark>
                ) : (
                  <span key={i}>{p.text}</span>
                ),
              )}
            </div>
          )}
        </div>
      </div>

      <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-ink-400">
        Relations ({relations.length})
      </h2>
      {relations.length === 0 && (
        <p className="text-sm text-ink-500">No relations judged involving this paper's claims.</p>
      )}
      <div className="grid gap-2 lg:grid-cols-2">
        {relations.map((r, i) => (
          <div key={i} className="rounded-lg border border-ink-800 bg-ink-900/40 p-3 text-sm">
            <span className={`font-medium ${RELATION_COLOR[r.type] ?? ""}`}>{r.type}</span>
            <span className="ml-2 text-ink-500">confidence {r.confidence.toFixed(2)}</span>
            <p className="mt-1 text-ink-400">{r.rationale}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
