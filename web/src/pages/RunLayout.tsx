import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import StatusPill from "../components/StatusPill";
import ThemeToggle from "../components/ThemeToggle";
import { getRun } from "../lib/api";
import type { RunContext } from "../lib/runContext";
import type { RunDetail } from "../lib/types";
import { useEvents } from "../lib/useEvents";

function Tab({ to, end, label }: { to: string; end?: boolean; label: string }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
          isActive
            ? "border-accent-400 text-accent-300"
            : "border-transparent text-ink-400 hover:text-ink-200"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

const REFRESH_ON: ReadonlySet<string> = new Set([
  "run_finished", "pipeline_finished", "saturation", "frontier_updated",
]);

export default function RunLayout() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<RunDetail | null>(null);
  const { events, connected, pipelineFinished } = useEvents(runId);

  function refreshRun() {
    if (runId) getRun(runId).then(setRun).catch(() => {});
  }

  useEffect(() => {
    refreshRun();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    const last = events[events.length - 1];
    if (last && REFRESH_ON.has(last.type)) refreshRun();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.length]);

  if (!runId) return null;
  const running = run?.status === "running" && !pipelineFinished;

  return (
    // header takes its natural height; the tab body fills the rest (no guessed calc())
    <div className="flex h-full flex-col">
      {/* pl-16 clears the fixed sidebar menu button (components/Sidebar.tsx) */}
      <header className="shrink-0 border-b border-ink-800 bg-ink-950/80 pt-4 pr-4 pl-16 sm:pr-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <Link to="/" className="text-xs text-ink-500 transition-colors hover:text-accent-400">
              ← ATLAS
            </Link>
            <h1 className="mt-0.5 max-w-3xl truncate text-2xl font-semibold text-ink-50">
              {run?.query ?? "Loading run…"}
            </h1>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span
              className={running ? (connected ? "text-emerald-400" : "text-amber-400") : "text-ink-500"}
              title={running ? "streaming events from the running crawl" : "replaying this run's recorded events"}
            >
              {running ? (connected ? "● live" : "○ reconnecting…") : "● finished · replay"}
            </span>
            {run && <StatusPill status={run.status} />}
            <ThemeToggle />
          </div>
        </div>
        {run && (
          <dl data-testid="run-stats" className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <Fact label="papers read" value={run.stats.papers_read} />
            <Fact
              label="claims kept"
              value={run.stats.claims_extracted - run.stats.claims_dropped_ungrounded}
            />
            <Fact label="quotes rejected by the grounding gate" value={run.stats.claims_dropped_ungrounded} />
            <Fact label="relations judged" value={run.stats.relations_judged} />
            <Fact
              label={run.stats.contradictions_found === 1 ? "contradiction" : "contradictions"}
              value={run.stats.contradictions_found}
            />
            <Fact label="full text" value={`${Math.round(run.stats.full_text_ratio * 100)}%`} />
            {run.stop_reason && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-ink-500">stopped:</dt>
                <dd className="font-semibold text-ink-100">{run.stop_reason}</dd>
              </div>
            )}
          </dl>
        )}
        <nav className="mt-4 flex gap-1 overflow-x-auto">
          <Tab to={`/runs/${runId}`} end label="Live" />
          <Tab to={`/runs/${runId}/report`} label="Report" />
          <Tab to={`/runs/${runId}/chat`} label="Chat" />
        </nav>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <Suspense
          fallback={<p className="p-6 text-sm text-ink-500">Loading…</p>}
        >
          <Outlet
            context={{ runId, run, refreshRun, events, connected, pipelineFinished } satisfies RunContext}
          />
        </Suspense>
      </main>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dd className="font-semibold text-ink-100">{value}</dd>
      <dt className="text-ink-500">{label}</dt>
    </div>
  );
}
