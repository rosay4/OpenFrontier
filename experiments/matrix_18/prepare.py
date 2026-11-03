#!/usr/bin/env python3
"""Freeze a success-blind, scene-diverse sample of the existing A view."""
import csv, gzip, hashlib, json, random, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = Path(__file__).resolve().parent
SOURCE = ROOT / 'experiments/baseline_a_120/data'
RUN = ROOT / 'output/baseline_a_120_20261102_235157'
SEED = 20261103

def main():
    manifest = json.loads((SOURCE / 'episode_manifest.json').read_text())
    groups = defaultdict(list)
    for f in manifest['files']:
        scene = Path(f['source_file']).name.split('.')[0]
        for i, ep in enumerate(f['episodes']):
            assert int(ep['habitat_episode_id_after_loading']) == i
            groups[ep['category']].append((scene, i, ep, f))
    rng = random.Random(SEED)
    used, selected = set(), []
    for category in sorted(groups):
        options = sorted(groups[category], key=lambda x: (x[0], x[1]))
        rng.shuffle(options)
        for _ in range(3):
            candidates = [x for x in options if x[0] not in used] or options
            choice = candidates[0]
            options.remove(choice); used.add(choice[0]); selected.append(choice)
    assert len(selected) == 18
    by_scene = defaultdict(list)
    for x in selected: by_scene[x[0]].append(x)
    target = BUNDLE / 'data'
    content = target / 'objectnav_hm3d_v2/val/content'
    content.mkdir(parents=True, exist_ok=True)
    link = target / 'scene_datasets'
    if not link.exists(): link.symlink_to((SOURCE / 'scene_datasets').resolve(), target_is_directory=True)
    files, identities, rows, times = [], [], [], []
    for scene, choices in sorted(by_scene.items()):
        choices.sort(key=lambda x: x[1])
        f = choices[0][3]
        with gzip.open(f['derived_file'], 'rt') as stream: data = json.load(stream)
        with gzip.open(Path.home() / 'habitat_data/openfrontier_hm3d_v2/objectnav_hm3d_v2/val/content' / (scene + '.json.gz'), 'rt') as stream: full = json.load(stream)
        originals = data['episodes']
        data['episodes'] = [originals[x[1]] for x in choices]
        eps = []
        for new_id, (_, old_id, ep, _) in enumerate(choices):
            assert originals[old_id] == full['episodes'][ep['source_index']], (scene, ep)
            ident = dict(ep, a_runtime_id=str(old_id), habitat_episode_id_after_loading=str(new_id), scene=scene)
            eps.append(ident); identities.append(ident)
        dest = content / (scene + '.json.gz')
        dest.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
        files.append(dict(f, derived_file=str(dest), episodes=eps))
    subset = dict(manifest, view_root=str(target), selection_seed=SEED, validation_episodes=18,
                  validation_scenes=len(files), category_counts={c: 3 for c in sorted(groups)}, files=files,
                  source_manifest_sha256=hashlib.sha256((SOURCE / 'episode_manifest.json').read_bytes()).hexdigest())
    (target / 'episode_manifest.json').write_text(json.dumps(subset, indent=2)+'\n')
    (BUNDLE / 'selection_18.json').write_text(json.dumps(identities, indent=2)+'\n')
    from omegaconf import OmegaConf
    config = OmegaConf.load(SOURCE / 'habitat_hm3d_eval.yaml')
    config.habitat.dataset.scenes_dir = str(link) + '/'
    config.habitat.dataset.data_path = str(content / '{split}.json.gz')
    OmegaConf.save(config, target / 'habitat_hm3d_eval.yaml')
    for ep in identities:
        scene, old = ep['scene'], int(ep['a_runtime_id'])
        metrics = list(RUN.glob('*/metrics/' + scene + '.csv'))
        assert len(metrics) == 1
        with metrics[0].open() as stream: matches = [r for r in csv.DictReader(stream) if int(r['episode']) == old]
        paths = list(RUN.glob(f'*/{scene}/*/episode-{old}-*/episode_telemetry.json'))
        assert len(matches) == len(paths) == 1
        t = json.loads(paths[0].read_text()); row = matches[0]
        assert row['object_goal'] == t['object_category'] == ep['category'] and t['original_episode_id'] == ep['original_episode_id']
        rows.append(dict(identity=ep, metrics=row, telemetry=t, telemetry_path=str(paths[0])))
        times.append(t['agent_seconds_before_video_export'])
    (BUNDLE / 'a_18_results.json').write_text(json.dumps(rows, indent=2)+'\n')
    calls = sum(x['telemetry']['vlm']['frontier']['calls'] for x in rows)
    summary = dict(completed=len(rows), successes=sum(int(float(x['metrics']['success'])) for x in rows),
        spl=statistics.mean(float(x['metrics']['spl']) for x in rows), mean_seconds=statistics.mean(times), median_seconds=statistics.median(times),
        frontier_calls=calls, frontier_parse_failures=sum(x['telemetry']['vlm']['frontier']['parse_failures'] for x in rows),
        frontier_retries=sum(sum(max(n-1,0) for n in x['telemetry']['vlm']['frontier']['calls_by_step'].values()) for x in rows),
        frontier_seconds=sum(x['telemetry']['vlm']['frontier']['seconds'] for x in rows))
    (BUNDLE / 'a_18_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__': main()
