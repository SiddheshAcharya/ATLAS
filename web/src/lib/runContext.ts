import { useOutletContext } from "react-router-dom";
import type { RunDetail } from "./types";
import type { useEvents } from "./useEvents";

export interface RunContext {
  runId: string;
  run: RunDetail | null;
  refreshRun: () => void;
  events: ReturnType<typeof useEvents>["events"];
  connected: boolean;
  pipelineFinished: boolean;
}

export function useRunContext(): RunContext {
  return useOutletContext<RunContext>();
}
