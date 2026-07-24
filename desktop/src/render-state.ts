export type ProgressEvent =
  | {
      type: "plan";
      input: string;
      output: string;
      total_frames: number;
      total_chunks: number;
      stages: string[];
    }
  | { type: "stage_started"; stage: string; ordinal: number; stage_count: number; chunk?: number }
  | { type: "progress"; stage: string; current: number; total: number; unit: string; chunk?: number }
  | { type: "stage_completed"; stage: string; chunk?: number }
  | { type: "warning"; code: string; message: string }
  | { type: "completed"; output: string }
  | { type: "cancelled"; resumable: boolean; work_dir: string }
  | { type: "failed"; code: string; message: string };

export interface ProgressEnvelope {
  protocol: "auvide.progress";
  version: 1;
  run_id: string;
  event: ProgressEvent;
}

export interface RenderExited {
  run_id: string;
  exit_code: number;
}

export type RenderPhase = "idle" | "running" | "completed" | "cancelled" | "failed";

export interface RenderState {
  phase: RenderPhase;
  runId: string | null;
  status: string;
  progress: number;
  warning: string | null;
  output: string | null;
  resumableWorkDir: string | null;
}

export const initialRenderState: RenderState = {
  phase: "idle",
  runId: null,
  status: "Ready.",
  progress: 0,
  warning: null,
  output: null,
  resumableWorkDir: null,
};

export type RenderAction =
  | { type: "started"; runId: string }
  | { type: "progress"; envelope: ProgressEnvelope }
  | { type: "exited"; exit: RenderExited }
  | { type: "launch_failed"; runId: string; message: string };

export function reduceRenderState(state: RenderState, action: RenderAction): RenderState {
  switch (action.type) {
    case "started":
      return {
        ...initialRenderState,
        phase: "running",
        runId: action.runId,
        status: "Starting render...",
      };
    case "progress":
      if (state.phase !== "running" || state.runId !== action.envelope.run_id) return state;
      return applyProgressEvent(state, action.envelope.event);
    case "exited":
      if (state.runId !== action.exit.run_id) return state;
      return applyExitCode(state, action.exit.exit_code);
    case "launch_failed":
      if (state.runId !== action.runId) return state;
      return { ...state, phase: "failed", status: action.message };
  }
}

function applyProgressEvent(state: RenderState, event: ProgressEvent): RenderState {
  switch (event.type) {
    case "plan":
      return { ...state, status: "Preparing render..." };
    case "stage_started":
      return { ...state, status: stageLabel(event.stage, event.chunk) };
    case "progress":
      return {
        ...state,
        status: stageLabel(event.stage, event.chunk),
        progress: fractionToPercent(event.current, event.total),
      };
    case "stage_completed":
      return { ...state, status: `${stageLabel(event.stage, event.chunk)} complete` };
    case "warning":
      return { ...state, warning: event.message };
    case "completed":
      return { ...state, phase: "completed", status: "Done", progress: 100, output: event.output };
    case "cancelled":
      return {
        ...state,
        phase: "cancelled",
        status: "Cancelled",
        resumableWorkDir: event.resumable ? event.work_dir : null,
      };
    case "failed":
      return { ...state, phase: "failed", status: event.message };
  }
}

function applyExitCode(state: RenderState, exitCode: number): RenderState {
  if (exitCode === 0) {
    return state.phase === "completed" ? state : { ...state, phase: "failed", status: "Render exited without completion event." };
  }
  if (exitCode === 130) {
    return state.phase === "cancelled" ? state : { ...state, phase: "cancelled", status: "Cancelled" };
  }
  return state.phase === "failed"
    ? state
    : { ...state, phase: "failed", status: `Render failed (exit ${exitCode}).` };
}

function fractionToPercent(current: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round(Math.max(0, Math.min(1, current / total)) * 100);
}

function stageLabel(stage: string, chunk?: number): string {
  const title = stage.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
  return chunk === undefined ? title : `${title} (chunk ${chunk})`;
}
