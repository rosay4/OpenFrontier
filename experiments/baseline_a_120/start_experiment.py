#!/usr/bin/env python3
"""Prepare the fixed subset and detach the two services and benchmark."""
import datetime
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
PROJECT = BUNDLE.parents[1]
STATE = BUNDLE / "state.json"


def save(state):
    temporary = STATE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(STATE)


def alive(pid, marker):
    process = Path("/proc") / str(pid)
    try:
        if (process / "stat").read_text().split(") ", 1)[1].split()[0] == "Z":
            return False
        return not marker or marker.encode() in (process / "cmdline").read_bytes()
    except FileNotFoundError:
        return False


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def detach(command, log, environment):
    with log.open("ab", buffering=0) as output:
        process = subprocess.Popen(["nohup", *command], cwd=PROJECT, env=environment,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    return process.pid


def patch_gpu_selection():
    path = PROJECT / "benchmark.py"
    source = path.read_text()
    old = 'os.environ["CUDA_VISIBLE_DEVICES"] = "0"'
    new = 'os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")'
    if new in source and old not in source:
        return
    if source.count(old) != 1:
        raise RuntimeError("Unexpected benchmark GPU configuration; refusing to replace it")
    backup = BUNDLE / "backups/benchmark.py.before_gpu_env"
    backup.parent.mkdir(exist_ok=True)
    if backup.exists():
        raise RuntimeError("A GPU-selection backup already exists; inspect benchmark.py")
    shutil.copy2(path, backup)
    updated = source.replace(old, new)
    compile(updated, str(path), "exec")
    temporary = path.with_name(path.name + ".gpu_tmp")
    temporary.write_text(updated)
    temporary.chmod(path.stat().st_mode)
    temporary.replace(path)


def main():
    import fcntl

    lock = (BUNDLE / ".start.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    benchmark = previous.get("benchmark", {})
    if benchmark and alive(benchmark["pid"], str(BUNDLE / "launch.sh")):
        print("Benchmark is already running: " + str(benchmark["pid"]), flush=True)
        return
    python_bin = Path.home() / ".conda/envs/habitat-headless/bin/python"
    subprocess.run([str(python_bin), str(BUNDLE / "prepare_subset.py")], check=True)
    patch_gpu_selection()
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    run = PROJECT / "output" / ("baseline_a_120_" + stamp)
    if previous.get("run_dir") and not previous.get("benchmark"):
        run = Path(previous["run_dir"])
    logs = run / "services"
    logs.mkdir(parents=True, exist_ok=True)
    state = {"run_dir": str(run), "bundle_dir": str(BUNDLE), "episodes": 120, "services": {}}
    save(state)
    for name, gpu, port, env_name, script, extra in (
        ("sam3", 1, 12184, "sam3", "sam3_server.py", []),
        ("vlm", 2, 12185, "openfrontier-vlm", "vlm_server.py", ["--model", "InternVL3_5-4B"]),
    ):
        old = previous.get("services", {}).get(name, {})
        if old and alive(old["pid"], script):
            state["services"][name] = old
        else:
            if listening(port):
                raise RuntimeError("Port %d belongs to an untracked service; leaving it untouched" % port)
            environment = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "MPLBACKEND": "Agg"}
            log = logs / (name + ".log")
            command = [str(Path.home() / ".conda/envs" / env_name / "bin/python"),
                       "-u", str(PROJECT / script), *extra]
            pid = detach(command, log, environment)
            state["services"][name] = {"pid": pid, "gpu": gpu, "port": port, "log": str(log)}
            print("Started %s: PID=%d GPU=%d log=%s" % (name, pid, gpu, log), flush=True)
        save(state)
    deadline = time.monotonic() + 300
    while not all(listening(s["port"]) for s in state["services"].values()):
        for name, service in state["services"].items():
            if not alive(service["pid"], ""):
                raise RuntimeError(name + " exited; inspect " + service["log"])
        if time.monotonic() > deadline:
            raise TimeoutError("Services are still loading; inspect their logs and state.json")
        print("Waiting for SAM3 and InternVL to finish loading...", flush=True)
        time.sleep(10)
    environment = {**os.environ, "OF_RUN_DIR": str(run), "OPENFRONTIER_BENCHMARK_GPU": "3"}
    log = run / "launch.log"
    pid = detach(["bash", str(BUNDLE / "launch.sh")], log, environment)
    state["benchmark"] = {"pid": pid, "gpu": 3, "log": str(log)}
    save(state)
    time.sleep(5)
    if not alive(pid, str(BUNDLE / "launch.sh")):
        raise RuntimeError("Benchmark exited during startup; inspect " + str(log))
    print("EXPERIMENT_STARTED", flush=True)
    print(json.dumps(state, indent=2), flush=True)


if __name__ == "__main__":
    main()
