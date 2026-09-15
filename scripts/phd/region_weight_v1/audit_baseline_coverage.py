"""Read frozen mask manifests and traces; quantify the >0-pixel camera count."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Run in Docker')
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--payload', default='/payload')
    ap.add_argument('--out', default='/out')
    args = ap.parse_args()
    p, out = Path(args.payload), Path(args.out)
    hashes = {}

    def raw(path):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text()

    def read(path):
        return json.loads(raw(path))

    def lines(path):
        return [json.loads(line) for line in raw(path).splitlines()]

    cfg = read(Path(args.config))
    result = dict(scientific_verdict=None, training_changed=False,
                  runtime=cfg['runtime_image'], script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  coverage_definition='R1 valid pixels / original valid MVS pixels at first camera visit; not 3D surface coverage',
                  thresholds='Descriptive bins only; no training mask or view selection changed', regions={}, inputs=hashes)
    for region in ['P1', 'P2', 'P3']:
        run = p/cfg['P1'] if region == 'P1' else p/cfg['P2P3']/region
        config = read(run/'config.json')
        prefix = 'p1_weight' if region == 'P1' else 'region_weight'
        model = run/'train/alpha_1/model'
        visits = Counter(row['camera'] for row in lines(model/(prefix+'_camera_trace.jsonl')))
        suffix = '_target_trace.jsonl' if region == 'P1' else '_trace.jsonl'
        first = {}
        for row in lines(model/(prefix+suffix)):
            first.setdefault(row['camera'], row)
        manifest = None if region == 'P1' else read(run/'mask/manifest.json')
        counts = {config['target_camera']: config['mask_rgb_pixels']} if region == 'P1' else {
            row['camera']: row['r1_pixels'] for row in manifest['views']}
        cameras = []
        for name, n in counts.items():
            row = first[name]
            assert n == row['r1']['count'], name
            valid = row['native_valid_count']
            cameras.append(dict(camera=name, r1_pixels=n, valid_pixels=valid, r1_fraction=n/valid if valid else 0,
                                used_pixels=n+row['other_used']['count'], visits=visits[name]))
        supported = [row for row in cameras if row['r1_pixels'] > 0]
        minimum = min(supported, key=lambda row: row['r1_fraction'])
        bins = []
        for threshold in [0, .01, .05, .1, .2]:
            selected = [row for row in supported if row['r1_fraction'] >= threshold]
            bins.append(dict(min_r1_fraction=threshold, cameras=len(selected),
                             visits=sum(row['visits'] for row in selected)))
        rr = dict(train_cameras=len(visits), steps=sum(visits.values()), r1_cameras=len(supported),
                  minimum=minimum, median_fraction=statistics.median(row['r1_fraction'] for row in supported),
                  maximum_fraction=max(row['r1_fraction'] for row in supported), bins=bins, cameras=cameras,
                  config_policy=config['mask_policy'])
        if region == 'P1':
            old = p/'geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/train/P1/mvs_0.0005/attempt.3iBmJucV'
            receipt = read(old/'receipt.json')
            rr['historical_same_binding'] = receipt['binding_sha256'] == config['binding_sha256']
            rr['historical_same_anchor'] = receipt['restore']['checkpoint_sha256'] == config['anchor_sha256']
            rr['historical_dynamic_declared'] = '--dynamic_depth_weight' in receipt['command']
            rr['historical_logged_mvs_weights'] = sorted({row['mvs_weight'] for row in lines(old/'model/mvs_pgsr_trace.jsonl')})
        result['regions'][region] = rr
    with (out/'audit.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({r: {k: v for k, v in d.items() if k != 'cameras'} for r, d in result['regions'].items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
