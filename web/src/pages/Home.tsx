import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Frame, Globe } from "../components/HomeBackdrop";
import { createRun } from "../lib/api";
import { addSearch, setSearchOptions, useSearchOptions } from "../lib/history";
import type { Mode } from "../lib/types";

const MODES: { value: Mode; label: string; cap: number }[] = [
  { value: "standard", label: "Standard", cap: 25 },
  { value: "deep", label: "Deep", cap: 75 },
  { value: "extra_deep", label: "Extra deep", cap: 200 },
];

// The timing the previous home page quoted from real runs. There is no measured figure per
// mode, so the visible hint states only the paper cap and this stays in the tooltip.
const TIMING_NOTE =
  "On free-tier language models a new run takes roughly 20–40 minutes for 3 papers and 1–4 hours for 15, mostly waiting on rate limits.";

function Rule({ className = "" }: { className?: string }) {
  return <span aria-hidden="true" className={`h-px flex-1 ${className}`} />;
}

// The title, one search box, and the depth / paper-cap controls under it. History, saved runs
// and the theme toggle live in the sidebar (components/Sidebar.tsx). Enter starts the run and
// opens its live view.
export default function Home() {
  const [query, setQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mode, maxPapers } = useSearchOptions();
  const navigate = useNavigate();
  const modeRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const cap = maxPapers ? Number(maxPapers) : MODES.find((m) => m.value === mode)!.cap;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const n = maxPapers ? Number(maxPapers) : undefined;
      const { run_id } = await createRun(q, mode, n);
      addSearch({ runId: run_id, query: q, mode });
      navigate(`/runs/${run_id}`);
    } catch (err) {
      setError(String(err));
      setSubmitting(false);
    }
  }

  // radio-group keyboard pattern: arrows move the selection, Tab leaves the group
  function onModeKey(e: React.KeyboardEvent, i: number) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (i + step + MODES.length) % MODES.length;
    setSearchOptions({ mode: MODES[next].value });
    modeRefs.current[next]?.focus();
  }

  return (
    <div className="atlas-home relative flex min-h-full flex-col overflow-hidden">
      <Frame />

      <main className="relative isolate z-10 flex flex-1 flex-col items-center justify-center px-12 pt-20 pb-6 sm:px-16">
        {/* the globe encloses the whole composition, sized to fit inside the frame */}
        <div aria-hidden="true" className="atlas-glow atlas-globe-size absolute top-1/2 left-1/2 -z-10 -translate-x-1/2 -translate-y-1/2 scale-110 rounded-full" />
        <div className="atlas-globe-size absolute top-1/2 left-1/2 -z-10 -translate-x-1/2 -translate-y-1/2">
          <Globe />
        </div>

        <div className="flex w-full flex-col items-center">
          <h1 className="atlas-rise pl-[0.2em] text-[clamp(3.5rem,15vw,8.5rem)] leading-none font-medium tracking-[0.2em] text-ink-100 select-none">
            ATLAS
          </h1>
          <div className="atlas-rise mt-4 flex w-full max-w-xl items-center gap-3 [animation-delay:150ms] sm:gap-4">
            <Rule className="bg-gradient-to-r from-transparent to-accent-600/70" />
            <p className="font-display text-base whitespace-nowrap text-ink-400 italic sm:text-lg">
              Agentic literature analysis &amp; synthesis
            </p>
            <Rule className="bg-gradient-to-l from-transparent to-accent-600/70" />
          </div>
        </div>

        <form onSubmit={onSubmit} role="search" className="atlas-rise mt-10 w-full max-w-xl [animation-delay:300ms] sm:mt-12">
          <div className="relative">
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="pointer-events-none absolute top-1/2 left-5 z-10 h-5 w-5 -translate-y-1/2 text-ink-500" // above the input, whose backdrop-blur paints over earlier siblings
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            >
              <circle cx="11" cy="11" r="6.5" />
              <path d="M16 16l4.5 4.5" />
            </svg>
            <input
              id="query"
              aria-label="Research question"
              aria-describedby={error ? "query-error" : "search-hint"}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={submitting}
              autoFocus
              autoComplete="off"
              enterKeyHint="search"
              placeholder="Ask a research question"
              className="w-full rounded-full border border-ink-700 bg-ink-900/85 py-4 pr-14 pl-13 text-base text-ink-100 shadow-lg shadow-black/10 backdrop-blur-sm outline-none transition-[border-color,box-shadow,background-color] duration-300 placeholder:text-ink-500 hover:border-accent-700 focus:border-accent-500 focus:bg-ink-900 focus:shadow-[0_0_0_4px_color-mix(in_srgb,var(--color-accent-500)_18%,transparent)] focus-visible:outline-none disabled:opacity-70"
            />
            {submitting ? (
              <span
                role="status"
                aria-label="Starting the run"
                className="absolute top-1/2 right-5 h-5 w-5 -translate-y-1/2 animate-spin rounded-full border-2 border-accent-500 border-t-transparent"
              />
            ) : (
              <kbd aria-hidden="true" className="absolute top-1/2 right-4 hidden -translate-y-1/2 rounded-md border border-ink-700 px-1.5 py-0.5 font-sans text-[11px] text-ink-500 sm:block">
                ↵ Enter
              </kbd>
            )}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
            <div
              role="radiogroup"
              aria-label="Research depth"
              className="inline-flex rounded-full border border-ink-700 bg-ink-900/85 p-1 backdrop-blur-sm"
            >
              {MODES.map((m, i) => {
                const on = mode === m.value;
                return (
                  <button
                    key={m.value}
                    ref={(el) => {
                      modeRefs.current[i] = el;
                    }}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    tabIndex={on ? 0 : -1}
                    onClick={() => setSearchOptions({ mode: m.value })}
                    onKeyDown={(e) => onModeKey(e, i)}
                    title={`Reads up to ${m.cap} papers`}
                    className={`rounded-full px-3.5 py-1.5 text-sm transition-colors duration-200 sm:px-4 ${
                      on ? "bg-accent-500 font-medium text-ink-950 shadow-sm" : "text-ink-400 hover:text-ink-100"
                    }`}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>

            <label className="inline-flex items-center gap-2 rounded-full border border-ink-700 bg-ink-900/85 py-1 pr-1 pl-4 text-sm text-ink-400 backdrop-blur-sm transition-colors focus-within:border-accent-500 hover:border-accent-700">
              Max papers
              <input
                id="maxPapers"
                value={maxPapers}
                inputMode="numeric"
                maxLength={3}
                onChange={(e) => setSearchOptions({ maxPapers: e.target.value.replace(/\D/g, "") })}
                placeholder="auto"
                className="w-14 rounded-full bg-ink-950 px-2 py-1 text-center text-ink-100 outline-none placeholder:text-ink-600 focus-visible:outline-none"
              />
            </label>
          </div>

          {error ? (
            <p id="query-error" role="alert" className="mt-4 text-center text-sm text-red-400">
              {error}
            </p>
          ) : (
            <p id="search-hint" className="mt-4 text-center font-display text-base text-ink-500 italic" title={TIMING_NOTE}>
              Reads up to {cap} {cap === 1 ? "paper" : "papers"}, following citations as it goes
            </p>
          )}
        </form>
      </main>

      <footer aria-hidden="true" className="atlas-fade-slow relative z-10 flex items-center justify-center gap-3 pb-14 text-[11px] tracking-[0.32em] text-ink-500 uppercase">
        <span>Forage</span>
        <span className="h-1.5 w-1.5 rotate-45 bg-accent-600" />
        <span>Ground</span>
        <span className="h-1.5 w-1.5 rotate-45 bg-accent-600" />
        <span>Report</span>
      </footer>
    </div>
  );
}
