// Mirrors the stage-6 API models in src/atlas/contracts.py (docs/CONTRACTS.md).
// Kept to what the UI actually reads — not a byte-for-byte transcription of every field.

export type Mode = "standard" | "deep" | "extra_deep";
export type FrontierState = "pending" | "parked" | "reading" | "read" | "dropped" | "failed";
export type GapType =
  | "unlinked_concepts"
  | "predicted_link"
  | "empty_combination"
  | "unanswered_call"
  | "unresolved_conflict"
  | "shared_weakness";

export interface RunCreateResponse {
  run_id: string;
}

export interface RunListItem {
  run_id: string;
  query: string;
  mode: string;
  status: string | null;
  stop_reason: string | null;
  started_at: string | null;
  offline: boolean;
}

export interface RunStats {
  papers_discovered: number;
  papers_read: number;
  full_text_ratio: number;
  claims_extracted: number;
  claims_dropped_ungrounded: number;
  relations_judged: number;
  contradictions_found: number;
  bridge_promotions: number;
  clusters_covered: number;
  stop_reason: string;
  total_usd: number;
  wall_clock_seconds: number;
}

export interface RunDetail {
  run_id: string;
  query: string;
  mode: string;
  status: string | null;
  stop_reason: string | null;
  config_hash: string | null;
  started_at: string | null;
  finished_at: string | null;
  keywords: string[];
  stats: RunStats;
}

export interface GraphSnapshot {
  nodes: { data: Record<string, unknown> }[];
  edges: { data: Record<string, unknown> }[];
}

export interface TimelinePoint {
  read_order: number;
  paper_id: string;
  title: string;
  score: number | null;
  new_info: number | null;
  ema: number | null;
  cumulative_claims: number;
  cumulative_usd: number;
}

export interface FrontierRow {
  paper_id: string;
  title: string;
  state: FrontierState;
  score: number | null;
  relevance: number | null;
  novelty: number | null;
  recency: number | null;
  pagerank: number | null;
  contest: number | null;
  discovered_via: string | null;
  parked_reason: string | null;
  read_order: number | null;
  depth: string | null;
}

export interface Author {
  name: string;
  author_id?: string | null;
  orcid?: string | null;
}

export interface PaperMeta {
  paper_id: string;
  title: string;
  abstract?: string | null;
  year?: number | null;
  venue?: string | null;
  authors: Author[];
  doi?: string | null;
  citation_count?: number | null;
  depth: string;
}

export interface ClaimScope {
  what_was_tested: string;
  population_or_setting?: string | null;
  method?: string | null;
  dataset_or_context?: string | null;
  metric?: string | null;
  conditions?: string | null;
}

export interface Claim {
  claim_id: string;
  paper_id: string;
  text: string;
  quote: string;
  section: string;
  scope: ClaimScope;
  polarity: "positive" | "negative" | "neutral";
  confidence: number;
  verified: boolean;
  verify_method: "exact" | "fuzzy97" | "failed" | null;
  quote_char_start: number | null;
  quote_char_end: number | null;
}

export interface Relation {
  source_claim_id: string;
  target_claim_id: string;
  type: "SUPPORTS" | "CONTRADICTS" | "EXTENDS" | "REPLICATES" | "DIFF_SCOPE" | "UNRELATED";
  confidence: number;
  rationale: string;
  judged_by: string;
  run_id: string;
}

export interface PaperDetail {
  paper: PaperMeta;
  claims: Claim[];
  relations: Relation[];
}

export interface PaperSource {
  paper_id: string;
  text: string;
  sections: { name: string; char_start: number; char_end: number }[];
  origin: "this_run" | "other_run" | "abstract";
}

export interface PaperRef {
  paper_id: string;
  title: string;
  year: number | null;
  role: "a_side" | "b_side" | "evidence";
}

export interface RankedGap {
  gap_id: string;
  type: GapType;
  statement: string;
  detector_score: number;
  bounding_papers: PaperRef[];
  entities: string[];
  detail: Record<string, unknown>;
  gap_score: number;
  rank: number;
  found_by: GapType[];
}

export interface Citation {
  paper_id: string;
  title: string;
  year: number | null;
}

export interface ReportSection {
  heading: string;
  body_md: string;
  citations: Citation[];
}

export interface Report {
  run_id: string;
  query: string;
  agreement: ReportSection;
  contradictions: ReportSection;
  gaps: RankedGap[];
  methodology_timeline: ReportSection;
  stats: RunStats;
  generated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatCitation {
  paper_id: string;
  title: string;
  quote: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
}

export interface ServiceHealth {
  name: string;
  ok: boolean | null;
  detail: string;
}

export interface HealthStatus {
  services: ServiceHealth[];
  healthy: boolean;
}

// SSE frame (api/sse.py forwards `event`/`data` verbatim from the events table row).
export interface AtlasEvent {
  type: string;
  seq: number;
  payload: Record<string, unknown>;
}
