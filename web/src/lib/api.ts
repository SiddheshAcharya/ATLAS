// Thin fetch wrappers over docs/API.md. Relative paths — vite.config.ts proxies
// /api and /health to the FastAPI server in dev; a production build would be served
// behind the same origin as the API, or this base swapped for an env var.
import type {
  ChatMessage,
  ChatResponse,
  FrontierRow,
  GraphSnapshot,
  HealthStatus,
  Mode,
  PaperDetail,
  PaperSource,
  RankedGap,
  Report,
  RunCreateResponse,
  RunDetail,
  RunListItem,
  TimelinePoint,
} from "./types";

const BASE = "/api/v1";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new ApiError(r.status, body || r.statusText);
  }
  return r.json() as Promise<T>;
}

export { ApiError };

export function getHealth(): Promise<HealthStatus> {
  return fetch("/health").then((r) => r.json());
}

export function createRun(query: string, mode: Mode, maxPapers?: number): Promise<RunCreateResponse> {
  return req("/runs", {
    method: "POST",
    body: JSON.stringify({ query, mode, max_papers: maxPapers ?? null }),
  });
}

export function listRuns(): Promise<RunListItem[]> {
  return req("/runs");
}

export function getRun(runId: string): Promise<RunDetail> {
  return req(`/runs/${runId}`);
}

export function stopRun(runId: string): Promise<{ stopping: boolean }> {
  return req(`/runs/${runId}/stop`, { method: "POST" });
}

export function getGraph(runId: string): Promise<GraphSnapshot> {
  return req(`/runs/${runId}/graph`);
}

export function getFrontier(runId: string): Promise<FrontierRow[]> {
  return req(`/runs/${runId}/frontier`);
}

export function getTimeline(runId: string): Promise<TimelinePoint[]> {
  return req(`/runs/${runId}/timeline`);
}

export function getPaper(runId: string, paperId: string): Promise<PaperDetail> {
  return req(`/runs/${runId}/papers/${encodeURIComponent(paperId)}`);
}

export function getPaperSource(runId: string, paperId: string): Promise<PaperSource> {
  return req(`/runs/${runId}/papers/${encodeURIComponent(paperId)}/source`);
}

export function getGaps(runId: string): Promise<RankedGap[]> {
  return req(`/runs/${runId}/gaps`);
}

export function getReport(runId: string): Promise<Report> {
  return req(`/runs/${runId}/report`);
}

export function reportMarkdownUrl(runId: string): string {
  return `${BASE}/runs/${runId}/report.md`;
}

export function sendChat(
  runId: string,
  message: string,
  history: ChatMessage[],
): Promise<ChatResponse> {
  return req(`/runs/${runId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

export function eventsUrl(runId: string, sinceSeq: number): string {
  return `${BASE}/runs/${runId}/events?since_seq=${sinceSeq}`;
}
