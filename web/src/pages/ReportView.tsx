import { useEffect, useMemo, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";
import { ApiError, getReport, reportMarkdownUrl } from "../lib/api";
import type { Citation, Report, ReportSection as ReportSectionT } from "../lib/types";
import { useRunContext } from "../lib/runContext";
import { decodeEntities, numberCitations } from "../lib/text";

// Internal citation links navigate client-side instead of reloading the app.
const mdComponents: Components = {
  a: ({ href, children }) =>
    href?.startsWith("/runs/") ? (
      <Link to={href} className="font-medium text-accent-300 no-underline hover:underline">
        {children}
      </Link>
    ) : (
      <a href={href}>{children}</a>
    ),
};

function Section({
  section, body, caution,
}: { section: ReportSectionT; body: string; caution?: string }) {
  return (
    <section className="mb-8">
      <h2 className="mb-2 font-display text-2xl font-semibold text-ink-100">{section.heading}</h2>
      {caution && <Caution>{caution}</Caution>}
      <div className="prose max-w-none prose-p:text-ink-300">
        <ReactMarkdown components={mdComponents}>{body}</ReactMarkdown>
      </div>
    </section>
  );
}

export default function ReportView() {
  const { runId } = useRunContext();
  const [report, setReport] = useState<Report | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    getReport(runId)
      .then(setReport)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) setNote("Neo4j is not configured for this run — no report available.");
        else if (e instanceof ApiError && e.status === 404) setNote("This run hasn't produced a report yet.");
        else setNote(String(e));
      });
  }, [runId]);

  // One citation number per paper across the whole report, in order of first use.
  const numbered = useMemo(() => {
    if (!report) return null;
    const numbering = new Map<string, number>();
    const sections = [report.agreement, report.contradictions, report.methodology_timeline];
    const bodies = sections.map((s) => numberCitations(s.body_md, runId, numbering));
    const known = new Map<string, Citation>();
    for (const s of sections) for (const c of s.citations) known.set(c.paper_id, c);
    const refs = [...numbering.entries()].map(([id, n]) => ({ n, id, cite: known.get(id) }));
    return { sections, bodies, refs };
  }, [report, runId]);

  if (note) return <p className="p-6 text-sm text-ink-500">{note}</p>;
  if (!report || !numbered) return <p className="p-6 text-sm text-ink-500">Loading report…</p>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl leading-tight font-semibold text-ink-50">Literature review: {report.query}</h1>
        <a
          href={reportMarkdownUrl(runId)}
          download={`atlas-report-${runId.slice(0, 8)}.md`}
          className="shrink-0 rounded border border-ink-700 px-3 py-1.5 text-xs text-ink-300 transition-colors hover:border-accent-500 hover:text-accent-300"
        >
          Download .md
        </a>
      </div>

      {numbered.sections.map((s, i) => (
        <Section
          key={s.heading}
          section={s}
          body={numbered.bodies[i]}
          caution={
            i === 1
              ? "ATLAS's relation judge often mistakes two independent studies for a disagreement; in our evaluation its contradictions were false more often than not. Open both papers."
              : undefined
          }
        />
      ))}

      <section className="mb-8">
        <h2 className="mb-3 font-display text-2xl font-semibold text-ink-100">Gaps ({report.gaps.length})</h2>
        <Caution>
          Gaps are found by pattern detectors over extracted concepts; in our ratings most were
          wording artefacts. Each one lists the papers that bound it — check them.
        </Caution>
        {report.gaps.length === 0 && (
          <p className="text-sm text-ink-500">No gaps survived the citation-rule filter for this run.</p>
        )}
        <div className="space-y-3">
          {report.gaps.map((g) => (
            <div key={g.gap_id} className="rounded-lg border border-ink-800 bg-ink-900/40 p-4">
              <div className="flex items-center gap-2 text-xs text-ink-500">
                <span className="rounded bg-ink-800 px-1.5 py-0.5">#{g.rank}</span>
                <span className="text-amber-300">{g.type.replace(/_/g, " ")}</span>
                <span>score {g.gap_score.toFixed(3)}</span>
                {g.found_by.length > 1 && (
                  <span className="text-emerald-400">corroborated by {g.found_by.length} detectors</span>
                )}
              </div>
              <p className="mt-2 text-sm text-ink-200">{g.statement}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {g.bounding_papers.slice(0, 8).map((p) => (
                  <Link
                    key={p.paper_id}
                    to={`/runs/${runId}/paper/${encodeURIComponent(p.paper_id)}`}
                    title={p.paper_id}
                    className="rounded-full bg-ink-800 px-2 py-0.5 text-xs text-ink-400 hover:text-accent-300"
                  >
                    [{p.role}] {decodeEntities(p.title.length > 30 ? `${p.title.slice(0, 30)}…` : p.title)}
                  </Link>
                ))}
                {g.bounding_papers.length > 8 && (
                  <span className="text-xs text-ink-600">+{g.bounding_papers.length - 8} more</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {numbered.refs.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-2 font-display text-2xl font-semibold text-ink-100">References</h2>
          <ol className="space-y-1 text-sm text-ink-400">
            {numbered.refs.map(({ n, id, cite }) => (
              <li key={id} className="flex gap-2">
                <span className="w-7 shrink-0 text-right text-ink-500">[{n}]</span>
                <Link
                  to={`/runs/${runId}/paper/${encodeURIComponent(id)}`}
                  className="hover:text-accent-300"
                  title={id}
                >
                  {cite ? decodeEntities(cite.title) : id}
                  {cite?.year ? ` (${cite.year})` : ""}
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="border-t border-ink-800 pt-4 text-xs text-ink-500">
        <p>
          {report.stats.papers_read} papers read · {(report.stats.full_text_ratio * 100).toFixed(0)}% full text ·{" "}
          {report.stats.relations_judged} relations judged · {report.stats.contradictions_found} contradictions ·{" "}
          ${report.stats.total_usd.toFixed(4)} · {report.stats.wall_clock_seconds.toFixed(0)}s
        </p>
        <p className="mt-1">Generated {new Date(report.generated_at).toLocaleString()}</p>
      </section>
    </div>
  );
}

function Caution({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
      <span className="font-semibold">Auto-detected — verify before relying on it.</span> {children}
    </p>
  );
}
