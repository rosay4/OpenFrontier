#!/usr/bin/env python3
"""Run the existing benchmark with observation-only timing and request counters."""
import argparse
import contextvars
import datetime
import functools
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

CURRENT_AGENT = contextvars.ContextVar("metrics_agent", default=None)
CURRENT_ROLE = contextvars.ContextVar("metrics_role", default=None)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def measure_vlm(function, role):
    @functools.wraps(function)
    def measured(*args, **kwargs):
        agent = CURRENT_AGENT.get()
        token = CURRENT_ROLE.set(role)
        started = time.perf_counter()
        parsed = None
        try:
            result = function(*args, **kwargs)
            parsed = bool(result[0])
            return result
        finally:
            CURRENT_ROLE.reset(token)
            if agent is not None:
                stats = agent._measurements["vlm"].setdefault(role, {
                    "calls": 0, "seconds": 0.0, "parse_failures": 0,
                    "exceptions": 0, "calls_by_step": {}})
                stats["calls"] += 1
                stats["seconds"] += time.perf_counter() - started
                stats["parse_failures"] += int(parsed is False)
                stats["exceptions"] += int(parsed is None)
                step = str(agent.navigation_steps)
                stats["calls_by_step"][step] = stats["calls_by_step"].get(step, 0) + 1
    return measured


def measure_post(function):
    @functools.wraps(function)
    def measured(url, *args, **kwargs):
        agent = CURRENT_AGENT.get()
        port = urllib.parse.urlparse(url).port
        if agent is None or port not in (12184, 12185):
            return function(url, *args, **kwargs)
        service = "sam3" if port == 12184 else "vlm"
        role = CURRENT_ROLE.get() or service
        key = service + "/" + role
        started = time.perf_counter()
        successful = False
        try:
            response = function(url, *args, **kwargs)
            successful = response.status_code == 200
            return response
        finally:
            stats = agent._measurements["http"].setdefault(key, {"requests": 0, "seconds": 0.0, "errors": 0})
            stats["requests"] += 1
            stats["seconds"] += time.perf_counter() - started
            stats["errors"] += int(not successful)
    return measured


def install_measurements(identities):
    import requests
    import nav.agent as navigation
    import nav.pointnav_agent as pointnav

    original = pointnav.PointnavAgent

    class MeasuredPointnavAgent(original):
        def __init__(self, habitat_env, args, save_dir, openfrontier_config, habitat_config, scene):
            self._started = time.perf_counter()
            episode = habitat_env.current_episode
            identity = identities.get((scene, str(episode.episode_id)), {})
            self._measurements = {"scene": scene, "habitat_episode_id": str(episode.episode_id),
                "benchmark_episode": int(Path(save_dir).name.split("-")[1]),
                "original_episode_id": identity.get("original_episode_id"),
                "object_category": episode.object_category, "vlm": {}, "http": {},
                "navigation_seconds": 0.0, "models": {key: openfrontier_config.get(key)
                    for key in ("segmentation_source", "probabilities_source", "detection_source")}}
            super().__init__(habitat_env, args, save_dir, openfrontier_config, habitat_config, scene)

        def navigation(self, *args, **kwargs):
            token = CURRENT_AGENT.set(self)
            started = time.perf_counter()
            try:
                return super().navigation(*args, **kwargs)
            finally:
                self._measurements["navigation_seconds"] += time.perf_counter() - started
                CURRENT_AGENT.reset(token)

        def save_trajectory(self, directory="output_objnav/"):
            self._measurements["agent_seconds_before_video_export"] = time.perf_counter() - self._started
            self._measurements["navigation_steps"] = self.navigation_steps
            self._measurements["builtin_timings"] = getattr(self, "timings", {})
            path = Path(directory) / "episode_telemetry.json"
            write_json(path, self._measurements)
            started = time.perf_counter()
            try:
                return super().save_trajectory(directory)
            finally:
                self._measurements["video_export_seconds"] = time.perf_counter() - started
                write_json(path, self._measurements)

    navigation.detect_frontier_probabilities = measure_vlm(navigation.detect_frontier_probabilities, "frontier")
    navigation.detect_target_object = measure_vlm(navigation.detect_target_object, "verification")
    requests.post = measure_post(requests.post)
    pointnav.PointnavAgent = MeasuredPointnavAgent


def snapshot_file(source, destination):
    if destination.exists():
        if source.read_bytes() != destination.read_bytes():
            raise RuntimeError("Existing run uses a different snapshot: " + str(destination))
    else:
        shutil.copyfile(source, destination)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--config", required=True)
    args, _ = parser.parse_known_args()
    project = Path.cwd()
    if not (project / "benchmark.py").is_file():
        raise RuntimeError("Run this launcher from /home/chenhongyuan/projects/openfrontier")
    view = Path(os.environ["OPENFRONTIER_DATA_ROOT"])
    manifest = json.loads((view / "episode_manifest.json").read_text())
    check_path = Path(manifest.get("runtime_check_file", view / "habitat_runtime_check.json"))
    report = json.loads(check_path.read_text())
    if report["failed"] or report["passed"] != 39:
        raise RuntimeError("HM3D runtime checks have not all passed")
    if (manifest["validation_scenes"] != len(manifest["files"])
            or manifest["validation_episodes"] != sum(len(item["episodes"]) for item in manifest["files"])):
        raise RuntimeError("Unexpected baseline evaluation set")
    for port in (12184, 12185):
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            pass
    output = Path(args.output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    snapshot_file(Path(args.config), output / "navigation_baseline_a.yaml")
    snapshot_file(Path(os.environ["HABITAT_HM3D_CONFIG"]), output / "habitat_config.yaml")
    snapshot_file(view / "episode_manifest.json", output / "episode_manifest.json")
    sys.argv[sys.argv.index("--config") + 1] = str(output / "navigation_baseline_a.yaml")
    os.environ["HABITAT_HM3D_CONFIG"] = str(output / "habitat_config.yaml")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    provenance = output / "provenance" / stamp
    provenance.mkdir(parents=True)
    for name in ("run_with_metrics.py", "summarize.py"):
        shutil.copyfile(Path(__file__).with_name(name), provenance / name)
    for command, name in ((["git", "rev-parse", "HEAD"], "source_commit.txt"),
                          (["git", "diff", "--binary", "HEAD"], "source_changes.patch"),
                          (["git", "status", "--short"], "git_status.txt"),
                          (["git", "submodule", "status"], "submodules.txt")):
        result = subprocess.run(command, capture_output=True, check=True)
        (provenance / name).write_bytes(result.stdout)
    write_json(provenance / "command.json", {"cwd": str(project), "argv": sys.argv,
               "data_root": str(view), "habitat_config": os.environ["HABITAT_HM3D_CONFIG"]})
    identities = {(Path(item["source_file"]).name.split(".")[0], e["habitat_episode_id_after_loading"]): e
                  for item in manifest["files"] for e in item["episodes"]}
    started = time.perf_counter()
    status = "exception"
    try:
        sys.path.insert(0, str(project))
        install_measurements(identities)
        sys.argv[0] = str(project / "benchmark.py")
        runpy.run_path(str(project / "benchmark.py"), run_name="__main__")
        status = "returned"
    except SystemExit as error:
        if error.code not in (None, 0):
            raise
        status = "exited_zero"
    finally:
        write_json(provenance / "run_time.json", {"status": status, "seconds": time.perf_counter() - started})
        helper = runpy.run_path(str(Path(__file__).with_name("summarize.py")))
        summary = helper["summarize"](output)
        write_json(output / "summary.json", summary)
        print(json.dumps(summary, indent=2), flush=True)
    if not summary["complete"]:
        raise SystemExit("BASELINE_INCOMPLETE: inspect summary.json and run.log")
    print("BASELINE_A_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
