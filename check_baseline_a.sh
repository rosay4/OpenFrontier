#!/usr/bin/env bash
# Run on the Ubuntu experiment server. This script only reads local state.

repo="$HOME/projects/openfrontier"
printf '\n=== Host and GPU ===\n'
date -Is
hostname
whoami
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv

printf '\n=== Conda environments ===\n'
if command -v conda >/dev/null 2>&1; then
    conda env list
fi
for env_root in "$HOME/.conda/envs" "$HOME/miniconda3/envs" "$HOME/anaconda3/envs"; do
    for env_name in habitat-headless habitat openfrontier sam3 openfrontier-vlm; do
        py="$env_root/$env_name/bin/python"
        [ -x "$py" ] || continue
        "$py" - <<'PY'
import importlib.metadata as md
import importlib.util
import sys

print("\nPython:", sys.executable, sys.version.split()[0])
for name in ("habitat-sim", "habitat-lab", "habitat-baselines", "torch",
             "torchvision", "numpy", "transformers", "open3d", "pywavemap",
             "ompl", "vlfm", "google-genai"):
    try:
        print(f"{name}: {md.version(name)}")
    except md.PackageNotFoundError:
        print(f"{name}: no distribution metadata")
for module in ("habitat", "habitat_sim", "habitat_baselines", "vlfm"):
    spec = importlib.util.find_spec(module)
    print(f"{module} location:", spec.origin if spec else "not found")
PY
    done
done

printf '\n=== OpenFrontier source and current settings ===\n'
if [ -d "$repo/.git" ]; then
    git -C "$repo" rev-parse HEAD
    git -C "$repo" status --short
    git -C "$repo" submodule status
    grep -nE 'generation_config|max_new_tokens|do_sample|use_flash_attn|local_files_only' \
        "$repo/vlm/inference_internvl.py"
    for cfg in "$repo/config/navigation.yaml" "$repo/config/navigation_local.yaml"; do
        [ -f "$cfg" ] || continue
        printf '\n%s\n' "$cfg"
        grep -nE '^(segmentation_source|probabilities_source|detection_source|pointnav_weights_path|predict_interval|termination_threshold|success_threshold):' "$cfg"
    done
fi

printf '\n=== Weights and dataset roots ===\n'
for path in "$repo/model_weights/rgbd_11cls.pth" \
            "$repo/model_weights/pointnav_weights.pth" \
            "$HOME/models/sam3/sam3.pt" \
            "$HOME/models/InternVL3_5-4B/config.json"; do
    if [ -f "$path" ]; then
        ls -lh "$path"
    else
        printf 'MISSING: %s\n' "$path"
    fi
done
for root in "$HOME/habitat_data" "$repo/data"; do
    if [ -d "$root" ]; then
        printf '\nDataset root: %s -> %s\n' "$root" "$(readlink -f "$root")"
        find -L "$root" -maxdepth 5 -type f \
            \( -name '*.scene_dataset_config.json' -o -name '*.json.gz' \
               -o -name '*.glb' -o -name '*.navmesh' \) -print | head -n 35
    else
        printf 'MISSING: %s\n' "$root"
    fi
done

printf '\n=== Service listeners ===\n'
ss -lntp | grep -E ':(12184|12185)[[:space:]]' || true
printf '\nInventory finished. No models loaded or packages installed.\n'
