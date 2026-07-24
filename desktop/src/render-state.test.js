import { describe, expect, test } from "bun:test";

import { initialRenderState, reduceRenderState } from "./render-state";

const runId = "run-1";

function started() {
  return reduceRenderState(initialRenderState, { type: "started", runId });
}

describe("reduceRenderState", () => {
  test("maps typed progress to a bounded percentage and useful status", () => {
    const state = reduceRenderState(started(), {
      type: "progress",
      envelope: {
        protocol: "auvide.progress",
        version: 1,
        run_id: runId,
        event: { type: "progress", stage: "encode", current: 3, total: 4, unit: "chunks", chunk: 3 },
      },
    });

    expect(state.progress).toBe(75);
    expect(state.status).toBe("Encode (chunk 3)");
  });

  test("ignores events from another render", () => {
    const state = started();
    const next = reduceRenderState(state, {
      type: "progress",
      envelope: {
        protocol: "auvide.progress",
        version: 1,
        run_id: "other-run",
        event: { type: "completed", output: "other.mp4" },
      },
    });

    expect(next).toBe(state);
  });

  test("keeps cancellation resumability separate from a failure", () => {
    const state = reduceRenderState(started(), {
      type: "progress",
      envelope: {
        protocol: "auvide.progress",
        version: 1,
        run_id: runId,
        event: { type: "cancelled", resumable: true, work_dir: "C:/jobs/run-1" },
      },
    });

    expect(state.phase).toBe("cancelled");
    expect(state.resumableWorkDir).toBe("C:/jobs/run-1");
  });

  test("requires a completion event for a successful process exit", () => {
    const failed = reduceRenderState(started(), {
      type: "exited",
      exit: { run_id: runId, exit_code: 0 },
    });
    expect(failed.phase).toBe("failed");

    const completed = reduceRenderState(started(), {
      type: "progress",
      envelope: {
        protocol: "auvide.progress",
        version: 1,
        run_id: runId,
        event: { type: "completed", output: "out.mp4" },
      },
    });
    expect(reduceRenderState(completed, {
      type: "exited",
      exit: { run_id: runId, exit_code: 0 },
    }).phase).toBe("completed");
  });

  test("ignores terminal exits from another render and keeps launch errors typed", () => {
    const state = started();
    expect(reduceRenderState(state, {
      type: "exited",
      exit: { run_id: "other-run", exit_code: 1 },
    })).toBe(state);

    const failed = reduceRenderState(state, {
      type: "launch_failed",
      runId,
      message: "Could not start render.",
    });
    expect(failed.phase).toBe("failed");
    expect(failed.status).toBe("Could not start render.");
  });
});
