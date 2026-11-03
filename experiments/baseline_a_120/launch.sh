#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$HOME/projects/openfrontier"
python_bin="$HOME/.conda/envs/habitat-headless/bin/python"
source "$bundle_dir/data/use_hm3d_eval.sh"
mkdir -p "$project_dir/output"
exec 9>"$project_dir/output/.openfrontier_benchmark.lock"
if ! flock -n 9; then
  echo "Another benchmark launched by this bundle is still running."
  exit 1
fi
run_dir="${OF_RUN_DIR:-$project_dir/output/baseline_a_120_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S)}"
mkdir -p "$run_dir"
printf '%s\n' "$run_dir" > "$project_dir/output/baseline_a_120_run_dir.txt"
echo "RUN_DIR=$run_dir"
cd "$project_dir"
export CUDA_VISIBLE_DEVICES="${OPENFRONTIER_BENCHMARK_GPU:-3}"
export MPLBACKEND=Agg

"$python_bin" -u "$bundle_dir/run_with_metrics.py" \
  --benchmark hm3d \
  --nickname baseline_a_120 \
  --config "$bundle_dir/navigation_baseline_a.yaml" \
  --output-path "$run_dir" \
  --eval_episodes -1 \
  --max_steps 500 \
  2>&1 | tee -a "$run_dir/run.log"
