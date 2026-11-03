"""Aggregate scene CSVs once per episode, preserving incomplete-run coverage."""
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path


def summarize(run):
    manifest = json.loads((run / "episode_manifest.json").read_text())
    expected = {(Path(item["source_file"]).name.split(".")[0], i)
                for item in manifest["files"] for i in range(len(item["episodes"]))}
    rows = {}
    for path in sorted(run.glob("*/metrics/*.csv")):
        with path.open(newline="") as source:
            for row in csv.DictReader(source):
                key = (path.stem, int(row["episode"]))
                if key not in expected or key in rows:
                    raise RuntimeError("Unexpected/duplicate episode in metrics: " + str(key))
                if float(row["success"]) not in (0, 1) or not math.isfinite(float(row["spl"])):
                    raise RuntimeError("Invalid success/SPL metric: " + str(key))
                rows[key] = row
    telemetry = {}
    for path in run.glob("*/*/*/episode-*/episode_telemetry.json"):
        item = json.loads(path.read_text())
        key = (item["scene"], item["benchmark_episode"])
        if key not in expected or key in telemetry:
            raise RuntimeError("Unexpected/duplicate episode telemetry: " + str(key))
        telemetry[key] = item
    count = len(rows)
    successes = sum(float(row["success"]) for row in rows.values())
    quality_complete = set(rows) == expected
    telemetry_complete = set(rows).issubset(telemetry)
    result = {"expected_episodes": len(expected), "completed_episodes": count,
              "missing_episodes": len(expected - set(rows)),
              "complete": quality_complete and telemetry_complete,
              "quality_complete": quality_complete, "telemetry_complete": telemetry_complete,
              "successes": successes, "SR_on_completed": successes / count if count else None,
              "SPL_on_completed": statistics.mean(float(r["spl"]) for r in rows.values()) if count else None,
              "SR_full_set": successes / len(expected) if quality_complete else None,
              "SPL_full_set": statistics.mean(float(r["spl"]) for r in rows.values()) if quality_complete else None,
              "termination_counts": dict(Counter(r["termination_reason"] for r in rows.values())),
              "telemetry_episodes": len(set(telemetry) & set(rows)), "categories": {}}
    for category, total in manifest["category_counts"].items():
        group = [r for r in rows.values() if r["object_goal"] == category]
        result["categories"][category] = {"expected": total, "completed": len(group),
            "SR": statistics.mean(float(r["success"]) for r in group) if group else None,
            "SPL": statistics.mean(float(r["spl"]) for r in group) if group else None}
    measured = [telemetry[k] for k in rows if k in telemetry]
    result["mean_agent_seconds_before_video_export"] = statistics.mean(
        t["agent_seconds_before_video_export"] for t in measured) if measured else None
    result["vlm"] = {}
    for role in ("frontier", "verification"):
        stats = [t["vlm"].get(role, {}) for t in measured]
        calls = sum(s.get("calls", 0) for s in stats)
        seconds = sum(s.get("seconds", 0.0) for s in stats)
        result["vlm"][role] = {"calls": calls, "seconds": seconds,
            "mean_seconds_per_call": seconds / calls if calls else None,
            "calls_per_measured_episode": calls / len(measured) if measured else None,
            "agent_retry_calls": sum(max(n - 1, 0) for s in stats for n in s.get("calls_by_step", {}).values()),
            "parse_failures": sum(s.get("parse_failures", 0) for s in stats),
            "exceptions": sum(s.get("exceptions", 0) for s in stats)}
    result["http"] = {}
    for t in measured:
        for key, stats in t["http"].items():
            target = result["http"].setdefault(key, {"requests": 0, "seconds": 0.0, "errors": 0})
            for field in target:
                target[field] += stats[field]
    return result


if __name__ == "__main__":
    run = Path(sys.argv[1]).resolve()
    result = summarize(run)
    (run / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
