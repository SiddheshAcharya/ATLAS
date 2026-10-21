import { useSyncExternalStore } from "react";
import type { Mode } from "./types";

// The searches this browser started, newest first, for the sidebar. Kept in localStorage —
// it is a per-viewer convenience, not run data (that lives on the server: listRuns()).
export interface HistoryEntry {
  runId: string;
  query: string;
  mode: Mode;
  at: string; // ISO timestamp
}

const KEY = "atlas-history";
const MAX = 50;
const listeners = new Set<() => void>();
let cache: HistoryEntry[] = read();

function read(): HistoryEntry[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed)
      ? parsed.filter((e): e is HistoryEntry => typeof e?.runId === "string" && typeof e?.query === "string")
      : [];
  } catch {
    return [];
  }
}

function write(next: HistoryEntry[]) {
  cache = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // blocked storage: history still works for this page load
  }
  listeners.forEach((l) => l());
}

// another tab started or cleared a search
window.addEventListener("storage", (e) => {
  if (e.key !== KEY) return;
  cache = read();
  listeners.forEach((l) => l());
});

export function addSearch(entry: Omit<HistoryEntry, "at">) {
  const rest = cache.filter((e) => e.runId !== entry.runId);
  write([{ ...entry, at: new Date().toISOString() }, ...rest].slice(0, MAX));
}

export function removeSearch(runId: string) {
  write(cache.filter((e) => e.runId !== runId));
}

export function clearHistory() {
  write([]);
}

export function useHistory(): HistoryEntry[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => cache,
  );
}

// Depth and paper cap for new searches — set in the sidebar, read by the home search box.
export interface SearchOptions {
  mode: Mode;
  maxPapers: string; // "" = the mode's default
}

const OPTIONS_KEY = "atlas-search-options";
const optionListeners = new Set<() => void>();
let options: SearchOptions = readOptions();

function readOptions(): SearchOptions {
  try {
    const o = JSON.parse(localStorage.getItem(OPTIONS_KEY) ?? "{}") as Partial<SearchOptions>;
    const mode: Mode = o.mode === "deep" || o.mode === "extra_deep" ? o.mode : "standard";
    return { mode, maxPapers: typeof o.maxPapers === "string" ? o.maxPapers.replace(/\D/g, "") : "" };
  } catch {
    return { mode: "standard", maxPapers: "" };
  }
}

export function setSearchOptions(patch: Partial<SearchOptions>) {
  options = { ...options, ...patch };
  try {
    localStorage.setItem(OPTIONS_KEY, JSON.stringify(options));
  } catch {
    // blocked storage: the options still apply for this page load
  }
  optionListeners.forEach((l) => l());
}

export function useSearchOptions(): SearchOptions {
  return useSyncExternalStore(
    (l) => {
      optionListeners.add(l);
      return () => optionListeners.delete(l);
    },
    () => options,
  );
}
