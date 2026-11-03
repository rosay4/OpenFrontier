#!/usr/bin/env python3
"""Print the current detached job and partial evaluation results."""
import json
from pathlib import Path
from summarize import summarize


def main():
    bundle = Path(__file__).resolve().parent
    state = json.loads((bundle / "state.json").read_text())
    print("Run: " + state["run_dir"])
    for name, item in {**state.get("services", {}), "benchmark": state.get("benchmark", {})}.items():
        if item:
            running = (Path("/proc") / str(item["pid"]) / "cmdline").exists()
            print("%s: PID %d, GPU %d, %s" % (name, item["pid"], item["gpu"], "running" if running else "stopped"))
    run = Path(state["run_dir"])
    if not (run / "episode_manifest.json").exists():
        print("Benchmark is starting; inspect launch.log")
        return
    try:
        result = summarize(run)
    except (ValueError, KeyError, OSError) as error:
        print("Metrics may be updating; check again. " + str(error))
        return
    output = {key: result[key] for key in ("completed_episodes", "expected_episodes", "complete",
        "SR_on_completed", "SPL_on_completed", "mean_agent_seconds_before_video_export", "termination_counts")}
    print(json.dumps(output, indent=2))
    if result["completed_episodes"] and result["mean_agent_seconds_before_video_export"] is not None:
        seconds = (result["expected_episodes"] - result["completed_episodes"]) * result["mean_agent_seconds_before_video_export"]
        print("Rough remaining time from completed episodes: %.1f hours" % (seconds / 3600))


if __name__ == "__main__":
    main()
