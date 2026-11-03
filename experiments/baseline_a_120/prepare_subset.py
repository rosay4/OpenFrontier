#!/usr/bin/env python3
"""Select 120 fixed validation episodes: 20 per category and all 36 scenes."""
import copy
import gzip
import hashlib
import json
import random
import shlex
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20261102


def select_episodes(manifest):
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for item in manifest["files"]:
        scene = Path(item["source_file"]).name.split(".")[0]
        for episode in item["episodes"]:
            groups[(scene, episode["category"])].append(episode["source_index"])
    scenes = sorted({scene for scene, _ in groups})
    categories = sorted(manifest["category_counts"])
    slots = [(category, i) for category in categories for i in range(20)]
    edges = {scene: [slot for slot in slots if (scene, slot[0]) in groups] for scene in scenes}
    for choices in edges.values():
        rng.shuffle(choices)
    owners = {}

    def match(scene, seen):
        for slot in edges[scene]:
            if slot in seen:
                continue
            seen.add(slot)
            if slot not in owners or match(owners[slot], seen):
                owners[slot] = scene
                return True
        return False

    order = scenes[:]
    rng.shuffle(order)
    for scene in order:
        if not match(scene, set()):
            raise RuntimeError("Cannot cover every scene within the category quotas")
    selected = defaultdict(list)
    counts = Counter()
    for (category, _), scene in sorted(owners.items()):
        index = rng.choice(groups[(scene, category)])
        groups[(scene, category)].remove(index)
        selected[scene].append(index)
        counts[category] += 1
    for category in categories:
        while counts[category] < 20:
            candidates = [scene for scene in scenes if groups[(scene, category)]]
            least = min(len(selected[scene]) for scene in candidates)
            scene = rng.choice([s for s in candidates if len(selected[s]) == least])
            index = rng.choice(groups[(scene, category)])
            groups[(scene, category)].remove(index)
            selected[scene].append(index)
            counts[category] += 1
    assert len(selected) == 36 and sum(map(len, selected.values())) == 120
    assert all(value == 20 for value in counts.values()) and len(counts) == 6
    return {scene: sorted(indices) for scene, indices in sorted(selected.items())}


def main():
    from omegaconf import OmegaConf

    bundle = Path(__file__).resolve().parent
    full = Path.home() / "habitat_data/openfrontier_hm3d_v2"
    source_path = full / "episode_manifest.json"
    source = json.loads(source_path.read_text())
    assert source["validation_episodes"] == 1000 and source["validation_scenes"] == 36
    selected = select_episodes(source)
    target = bundle / "data"
    content = target / "objectnav_hm3d_v2/val/content"
    content.mkdir(parents=True, exist_ok=True)
    scenes_link = target / "scene_datasets"
    if not scenes_link.exists():
        scenes_link.symlink_to(full / "scene_datasets", target_is_directory=True)
    elif scenes_link.resolve() != (full / "scene_datasets").resolve():
        raise RuntimeError("Existing scene link has a different target")
    files, category_counts = [], Counter()
    for item in source["files"]:
        scene = Path(item["source_file"]).name.split(".")[0]
        with gzip.open(item["derived_file"], "rt") as reader:
            data = json.load(reader)
        indices = selected[scene]
        data["episodes"] = [data["episodes"][i] for i in indices]
        destination = content / (scene + ".json.gz")
        destination.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
        identities = []
        for runtime_id, index in enumerate(indices):
            identity = copy.deepcopy(item["episodes"][index])
            identity["habitat_episode_id_after_loading"] = str(runtime_id)
            identities.append(identity)
            category_counts[identity["category"]] += 1
        files.append({**item, "derived_file": str(destination), "episodes": identities})
    manifest = {**source, "view_root": str(target), "selection_seed": SEED,
                "source_manifest": str(source_path),
                "source_manifest_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "source_validation_episodes": 1000, "validation_episodes": 120,
                "validation_scenes": len(files), "category_counts": dict(category_counts),
                "runtime_check_file": str(full / "habitat_runtime_check.json"), "files": files}
    text = json.dumps(manifest, indent=2) + "\n"
    path = target / "episode_manifest.json"
    if path.exists() and path.read_text() != text:
        raise RuntimeError("Existing fixed subset differs; preserve its results before replacing it")
    path.write_text(text)
    (bundle / "selection_120.json").write_text(text)
    config = OmegaConf.load(full / "habitat_hm3d_eval.yaml")
    config.habitat.dataset.scenes_dir = str(target / "scene_datasets") + "/"
    config.habitat.dataset.data_path = str(content / "{split}.json.gz")
    config.habitat.environment.iterator_options.num_episode_sample = -1
    config.habitat.environment.iterator_options.shuffle = False
    config.habitat.environment.iterator_options.cycle = False
    runtime = target / "habitat_hm3d_eval.yaml"
    OmegaConf.save(config, runtime)
    environment = {"OPENFRONTIER_DATA_ROOT": str(target), "HABITAT_HM3D_CONFIG": str(runtime),
                   "HABITAT_LAB_ROOT": str(Path.home() / "projects/habitat-lab-v0.3.2/habitat-lab")}
    (target / "use_hm3d_eval.sh").write_text("".join(
        "export " + key + "=" + shlex.quote(value) + "\n" for key, value in environment.items()))
    print(json.dumps({"episodes": 120, "scenes": len(files), "category_counts": dict(category_counts),
                      "selection_seed": SEED, "view": str(target)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
