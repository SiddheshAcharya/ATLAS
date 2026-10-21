import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { listRuns } from "../lib/api";
import { clearHistory, removeSearch, useHistory } from "../lib/history";
import type { RunListItem } from "../lib/types";
import StatusPill from "./StatusPill";
import ThemeToggle from "./ThemeToggle";

function ago(iso: string | null): string {
  if (!iso) return "unknown time";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const min = Math.round((Date.now() - t) / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d < 7 ? `${d} d ago` : new Date(t).toLocaleDateString();
}

function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between px-1">
      <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-500">{children}</h2>
      {action}
    </div>
  );
}

/** The ⋯ menu in the top-left corner and the history drawer it opens — on every page.
 *  The button is a solid medallion: on the home page it sits on the frame's corner. */
export default function Sidebar() {
  // open on the page it was opened from; navigating (a history item was clicked) closes it
  const [openOn, setOpenOn] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [runsError, setRunsError] = useState(false);
  const history = useHistory();
  const { pathname } = useLocation();
  const open = openOn === pathname;
  const setOpen = (o: boolean) => setOpenOn(o ? pathname : null);
  const activeRun = pathname.match(/^\/runs\/([^/]+)/)?.[1] ?? null;
  const menuRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  // refresh the server's run list each time the drawer opens
  useEffect(() => {
    if (!open) return;
    listRuns()
      .then((r) => {
        setRuns(r);
        setRunsError(false);
      })
      .catch(() => setRunsError(true));
  }, [open]);

  // focus moves into the drawer on open and back to the menu button on close; Esc closes
  useEffect(() => {
    if (open) closeRef.current?.focus();
    else if (wasOpen.current) menuRef.current?.focus();
    wasOpen.current = open;
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenOn(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const statusById = new Map(runs?.map((r) => [r.run_id, r.status]) ?? []);
  const mine = new Set(history.map((h) => h.runId));
  const saved = runs?.filter((r) => !mine.has(r.run_id)) ?? null;

  const itemClass = (runId: string) =>
    `block min-w-0 flex-1 rounded-lg border-l-2 py-2 pr-2 pl-3 transition-colors ${
      runId === activeRun
        ? "border-accent-500 bg-accent-500/10"
        : "border-transparent hover:border-accent-600 hover:bg-ink-800/60"
    }`;

  return (
    <>
      <button
        ref={menuRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open menu: search history and settings"
        aria-expanded={open}
        aria-controls="atlas-sidebar"
        className="fixed top-3 left-3 z-40 flex h-10 w-10 items-center justify-center rounded-full border border-ink-700 bg-ink-950 text-ink-400 transition-colors hover:border-accent-500 hover:text-accent-400"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>

      <div
        aria-hidden="true"
        onClick={() => setOpen(false)}
        className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px] transition-opacity duration-300 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <aside
        id="atlas-sidebar"
        role="dialog"
        aria-modal="true"
        aria-label="Search history and settings"
        inert={!open}
        className={`fixed top-0 left-0 z-50 flex h-full w-[min(86vw,22rem)] flex-col border-r border-ink-800 bg-ink-900 transition-[translate,box-shadow] duration-300 ease-out ${
          // shadow only while open: closed, it would bleed onto the page's left edge
          open ? "translate-x-0 shadow-2xl shadow-black/30" : "-translate-x-full shadow-none"
        }`}
      >
        <div className="flex items-center justify-between border-b border-ink-800 px-4 py-3">
          <Link
            to="/"
            className="font-display text-2xl font-semibold tracking-[0.16em] text-ink-100 hover:text-accent-400"
            aria-label="ATLAS — new search"
          >
            ATLAS
          </Link>
          <button
            ref={closeRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
            className="flex h-9 w-9 items-center justify-center rounded-full text-ink-400 transition-colors hover:bg-ink-800 hover:text-accent-400"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-7 overflow-y-auto px-3 py-4">
          <section aria-label="Recent searches">
            <SectionTitle
              action={
                history.length > 0 && (
                  <button
                    type="button"
                    onClick={() => clearHistory()}
                    className="rounded px-1.5 py-0.5 text-xs text-ink-500 transition-colors hover:text-accent-400"
                  >
                    Clear all
                  </button>
                )
              }
            >
              Recent searches
            </SectionTitle>
            {history.length === 0 ? (
              <div className="rounded-xl border border-dashed border-ink-700 px-4 py-6 text-center">
                <svg aria-hidden="true" viewBox="0 0 24 24" className="mx-auto h-6 w-6 text-ink-600" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <circle cx="11" cy="11" r="6.5" />
                  <path d="M16 16l4.5 4.5" />
                </svg>
                <p className="mt-2 text-sm text-ink-300">No searches yet</p>
                <p className="mt-1 text-xs text-ink-500">
                  Type a research question and press Enter — it will appear here.
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {history.map((h) => {
                  const status = statusById.get(h.runId);
                  return (
                    <li key={h.runId} className="group flex items-start gap-1">
                      <Link
                        to={`/runs/${h.runId}`}
                        className={itemClass(h.runId)}
                        aria-current={h.runId === activeRun ? "page" : undefined}
                      >
                        <div className="line-clamp-2 text-sm text-ink-100">{h.query}</div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-ink-500">
                          <span>{h.mode.replace("_", " ")} · {ago(h.at)}</span>
                          {status && <StatusPill status={status} />}
                        </div>
                      </Link>
                      <button
                        type="button"
                        onClick={() => removeSearch(h.runId)}
                        aria-label={`Remove “${h.query}” from history`}
                        title="Remove from history"
                        className="mt-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-600 opacity-60 transition hover:bg-ink-800 hover:text-accent-400 group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <path d="M6 6l12 12M18 6L6 18" />
                        </svg>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section aria-label="Saved runs">
            <SectionTitle>Saved runs</SectionTitle>
            {runs === null && !runsError && <p className="px-1 text-xs text-ink-500">Loading…</p>}
            {runsError && <p className="px-1 text-xs text-ink-500">Could not reach the ATLAS server.</p>}
            {saved?.length === 0 && <p className="px-1 text-xs text-ink-500">No other runs on this server.</p>}
            <ul className="space-y-1">
              {saved?.map((r) => (
                <li key={r.run_id}>
                  <Link
                    to={`/runs/${r.run_id}`}
                    className={itemClass(r.run_id)}
                    aria-current={r.run_id === activeRun ? "page" : undefined}
                  >
                    <div className="line-clamp-2 text-sm text-ink-200">{r.query}</div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-ink-500">
                      {r.offline && (
                        <span
                          className="rounded border border-accent-600/60 px-1 text-[10px] tracking-wide text-accent-400 uppercase"
                          title="Saved snapshot — opens instantly, works with the network unplugged"
                        >
                          demo
                        </span>
                      )}
                      <span>{r.mode.replace("_", " ")} · {ago(r.started_at)}</span>
                      {!r.offline && <StatusPill status={r.status} />}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="flex items-center justify-between border-t border-ink-800 px-4 py-3">
          <span className="text-xs text-ink-500">Theme</span>
          <ThemeToggle />
        </div>
      </aside>
    </>
  );
}
