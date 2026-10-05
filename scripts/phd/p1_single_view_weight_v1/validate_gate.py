"""Require matched actual preflights before releasing the three full runs."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def validate(root):
    root = Path(root)
    cfg = read(root / 'config.json')
    rows, schedules, first_steps = [], [], []
    for alpha in cfg['alphas']:
        output = root / 'preflight' / f'alpha_{alpha}'
        model = output / 'model'
        receipt = read(output / 'receipt.json')
        if (receipt['status'] != 'PASS' or not receipt['completed']
                or receipt['final_iteration'] != cfg['preflight_stop']
                or receipt['config_sha256'] != sha(root / 'config.json')
                or receipt['source_provenance_sha256'] != sha(root / 'source/p1_single_view_weight_source_provenance.json')):
            raise ValueError('Incomplete or mismatched preflight')
        for record in receipt['verified_outputs']:
            if sha(output / record['path']) != record['sha256']:
                raise ValueError('Preflight output changed')
        binding = read(model / 'p1_weight_binding.json')
        if (binding['alpha'] != alpha or binding['mask_sha256'] != cfg['mask_sha256']
                or binding['target_camera'] != cfg['target_camera']
                or binding['other_used_multiplier'] != 1
                or binding['excluded_multiplier'] != 0
                or binding['normalization'] != 'original_per_view_valid_pixel_count_with_frozen_support'
                or binding['fixed_mvs_weight'] != .05 or binding['fixed_prior_weight'] != .005
                or binding['dynamic_depth_weight'] is not False or not binding['native_protection']
                or binding['schema'] != 'JBGS_P1_SINGLE_VIEW_WEIGHT_BINDING_v2'
                or binding['used_pixels'] != cfg['used_rgb_pixels']
                or binding['r1_pixels'] != cfg['mask_rgb_pixels']):
            raise ValueError('Realized intervention controls differ')
        restore = read(model / 'jbgs_restore.json')
        if restore['declared_dynamic_depth_weight_change'] != [True, False]:
            raise ValueError('Fixed-controller override not explicitly recorded')
        algebra = read(model / 'p1_weight_first_target_algebra.json')
        if algebra['status'] != 'PASS' or not all(algebra['checks'].values()):
            raise ValueError('First target algebra failed')
        cameras = lines(model / 'p1_weight_camera_trace.jsonl')
        if [row['iteration'] for row in cameras] != list(range(8001, cfg['preflight_stop'] + 1)):
            raise ValueError('Incomplete per-iteration camera trace')
        targets = lines(model / 'p1_weight_target_trace.jsonl')
        if len(targets) != sum(row['target'] for row in cameras) or not targets:
            raise ValueError('Target-camera trace membership differs')
        for row in targets:
            if (row['alpha'] != alpha or row['camera'] != cfg['target_camera']
                    or row['mvs_weight'] != .05 or row['prior_weight'] != .005
                    or row['r1']['count'] <= 0 or row['other_used']['count'] <= 0):
                raise ValueError('Target supervision not actually exercised')
            expected = row['r1']['weighted_loss_contribution'] + row['other_used']['weighted_loss_contribution']
            if row['excluded']['weighted_loss_contribution'] != 0:
                raise ValueError('Excluded pixels still contribute depth supervision')
            if not math.isclose(expected, row['applied_loss'], rel_tol=2e-6, abs_tol=2e-6):
                raise ValueError('Regional contributions do not explain actual weighted loss')
        schedules.append(cameras)
        first_steps.append(read(model / 'p1_weight_first_step.json'))
        rows.append(dict(alpha=alpha, receipt_sha256=sha(output / 'receipt.json'),
                         target_visits=len(targets), first_target_iteration=targets[0]['iteration'],
                         target_pixels=targets[0]['r1']['count'], algebra=algebra['checks']))
    if not all(schedule == schedules[0] for schedule in schedules):
        raise ValueError('Camera schedules differ between conditions')
    if not all(row['pred_depth_sha256'] == first_steps[0]['pred_depth_sha256']
               and row['camera'] == first_steps[0]['camera']
               and row['native_mvs_loss'] == first_steps[0]['native_mvs_loss'] for row in first_steps):
        raise ValueError('First pre-update rendered prediction differs between conditions')
    return dict(status='PASS', scientific_verdict=None, task_id=cfg['task_id'],
                config_sha256=sha(root / 'config.json'),
                source_provenance_sha256=sha(root / 'source/p1_single_view_weight_source_provenance.json'),
                matched_camera_schedule=True, matched_first_render=True, preflights=rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = validate(args.root)
    except Exception as exc:
        with (args.root / 'gate_failure.json').open('x') as stream:
            json.dump(dict(status='FAIL', error=repr(exc), scientific_verdict=None), stream, indent=2)
        raise
    with (args.root / 'gate.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
