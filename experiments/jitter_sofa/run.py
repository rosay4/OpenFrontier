import os
import json
import random
import runpy
import sys
from collections import deque
from pathlib import Path

import numpy as np
import torch

seed = int(os.environ.get("OF_JITTER_SEED", "20261103"))
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
torch.cuda.manual_seed_all(seed)

sys.path.insert(0, str(Path.cwd()))
from nav.pointnav_agent import PointnavAgent

original_move = PointnavAgent.move_actions
original_init = PointnavAgent.__init__


def install(agent, *args, **kwargs):
    original_init(agent, *args, **kwargs)
    # Capture the action actually submitted to Habitat, including emergency turns,
    # and the simulator's state on both sides of that action.
    env = agent.habitat_env
    original_step = env.step
    trace_path = Path(agent.save_dir) / "jitter_actual_steps.jsonl"

    def state():
        s = env.sim.get_agent_state()
        q = s.rotation
        return {"position": np.asarray(s.position).tolist(),
                "rotation_xyzw": [float(q.x), float(q.y), float(q.z), float(q.w)]}

    def traced_step(action, *step_args, **step_kwargs):
        before = state()
        result = original_step(action, *step_args, **step_kwargs)
        record = {"navigation_step": agent.navigation_steps, "action": str(action),
                  "before": before, "after": state(), "seed": seed}
        with trace_path.open("a") as out:
            out.write(json.dumps(record) + "\n")
        return result

    env.step = traced_step
    planner = agent.planner
    original_solve = planner.solve
    history = deque(maxlen=6)
    last_goal = None
    recovered = False

    def solve(*args, **kwargs):
        nonlocal last_goal, recovered
        manager = agent.ft_manager
        goal_id = manager.current_goal_ft_id
        frontier = manager.get_frontier(goal_id) if goal_id is not None else None
        goal = planner.goal_pose[:2, 3]
        key_changed = (
            last_goal is None or last_goal[0] != goal_id
            or np.linalg.norm(goal - last_goal[1]) > 0.1
        )
        if key_changed or not frontier or frontier.is_object or agent.emergency_rotation:
            history.clear()
            recovered = False
        last_goal = (goal_id, goal.copy())
        rho, _ = planner.rho_theta(planner.start_pose, planner.goal_pos)
        if len(history) == 6 and rho > 0.5 and not recovered:
            actions, positions, distances = zip(*history)
            flips = sum(a != b for a, b in zip(actions, actions[1:]))
            displacement = max(np.linalg.norm(p - planner.start_pose[:2, 3]) for p in positions)
            if flips >= 2 and displacement < 0.05 and abs(distances[0] - rho) < 0.1:
                print(f"JITTER step={agent.navigation_steps} frontier={goal_id} "
                      f"flips={flips} displacement={displacement:.3f} rho={rho:.3f}", flush=True)
                recovered = True
                if os.environ.get("OF_JITTER_RECOVERY") == "1":
                    planner.pointnav_policy.reset()
                    planner.is_first_step = True
                    print("JITTER_POLICY_RESET", flush=True)
        return original_solve(*args, **kwargs)

    def move():
        action = planner.action
        if action in (2, 3) and planner.start_pose is not None:
            history.append((action, planner.start_pose[:2, 3].copy(), planner.rho))
        else:
            history.clear()
        return original_move(agent)

    planner.solve = solve
    agent.move_simulation = move


PointnavAgent.__init__ = install
runpy.run_path("benchmark.py", run_name="__main__")
