#!/usr/bin/env bash
set -euo pipefail
cd /home/chenhongyuan/projects/openfrontier
exec 9>output/.openfrontier_benchmark.lock
flock -n 9 || { echo 'Benchmark lock is held'; exit 1; }
export OPENFRONTIER_DATA_ROOT="$PWD/experiments/jitter_sofa/data"
export HABITAT_HM3D_CONFIG="$OPENFRONTIER_DATA_ROOT/habitat_hm3d_eval.yaml"
export HABITAT_LAB_ROOT=/home/chenhongyuan/projects/habitat-lab-v0.3.2/habitat-lab
export CUDA_VISIBLE_DEVICES=3 MPLBACKEND=Agg OF_JITTER_SEED=20261103
root="$PWD/output/jitter_compare_20261103_seed20261103"
mkdir -p "$root"
for mode in 0 1; do
  export OF_JITTER_RECOVERY="$mode"
  /home/chenhongyuan/.conda/envs/habitat-headless/bin/python -u experiments/jitter_sofa/run.py \
    --benchmark hm3d --nickname jitter_compare \
    --config experiments/baseline_a_120/navigation_baseline_a.yaml \
    --output-path "$root/recovery_$mode" --eval_episodes -1 --max_steps 500 \
    > "$root/recovery_$mode.log" 2>&1
done
