"""Score only complete candidate arms, retaining missing strata and arms."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from input_audit import sha
from result_io import save
from rules import outcomes

OUT, DOC = Path('/out'), Path('/docs')
STATES = ['right_only', 'wrong_only', 'both', 'neither']


def csv_write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows: return
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)


def aggregate(d, state, mask):
    total = float(d['area'][mask].sum())
    buildings = np.unique(d['building'][mask])
    result = dict(points=int(mask.sum()), area_m2=total, buildings=len(buildings))
    for label in STATES:
        area = float(d['area'][mask & (state == label)].sum())
        ratios = []
        for building in buildings:
            b = mask & (d['building'] == building)
            ratios.append(float(d['area'][b & (state == label)].sum() / d['area'][b].sum()))
        result[label + '_area_m2'] = area
        result[label + '_area_fraction'] = area / total if total else None
        result[label + '_building_median_fraction'] = float(np.median(ratios)) if ratios else None
    assert not mask.any() or abs(sum(result[k + '_area_fraction'] for k in STATES) - 1) < 1e-10
    return result


def main():
    cfg_path = Path('/config/candpick_v1.json'); cfg = json.loads(cfg_path.read_text()); digest = sha(cfg_path)
    assert digest == json.loads(Path('/config/candpick_v1.lock.json').read_text())['sha256']
    rows, photos, curves, complete, pending, rep_rows = [], [], [], [], [], []
    representatives = json.loads((DOC / 'representatives_v1.json').read_text())['rows']
    for unit in cfg['units']:
        with np.load(OUT / 'places' / (unit + '.npz')) as z: d = {k: z[k] for k in z.files}
        with np.load(OUT / 'occlusion' / unit / 'points.npz') as z:
            assert np.array_equal(z['point_id'], d['point_id']); high = z['over_30pct']
        for spec in cfg['arm_order']:
            arm = f"cp_{spec['start']}_sh{spec['sh_degree']}_{unit}"; root = OUT / 'runs' / arm
            receipt_path = root / 'complete.json'
            if not receipt_path.exists():
                progress = json.loads((root / 'progress.json').read_text()) if (root / 'progress.json').exists() else None
                attempts, failures = sorted(root.glob('attempt_*.json')), sorted(root.glob('failure_*.json'))
                phase = 'RUNNING' if progress else 'PREPARING' if attempts else 'NOT_STARTED'
                if attempts and failures and failures[-1].stat().st_mtime > attempts[-1].stat().st_mtime: phase = 'ERROR'
                pending.append(dict(arm=arm, status=phase,
                    iteration=progress['iteration'] if progress else 0 if attempts else None)); continue
            receipt = json.loads(receipt_path.read_text())
            assert receipt['status'] == 'COMPLETE' and receipt['config_sha256'] == digest
            assert receipt['frozen_unchanged'] and receipt['frozen_before'] == receipt['frozen_after']
            assert receipt['iterations'] == 3000 and not receipt['truth_used_in_loss'] and not receipt['depth_loss_used']
            assert sha(root / 'candidate_3000.npz') == receipt['final_candidate_sha256']
            with np.load(root / 'candidate_3000.npz') as z: pair = z['opacity'].reshape(-1, 2, 4).mean(2)
            ri = (d['right'] == 'image').astype(int); right = pair[np.arange(len(pair)), ri]; wrong = pair[np.arange(len(pair)), 1 - ri]
            state = outcomes(right, wrong); assert not (state == 'unavailable').any()
            dest = OUT / 'scoring'; dest.mkdir(exist_ok=True)
            np.savez_compressed(dest / (arm + '.npz'), point_id=d['point_id'],
                right_opacity=right, wrong_opacity=wrong, outcome=state)
            if spec['start'] == 'wrong':
                for rep in representatives:
                    if rep['unit'] != unit or not rep['selection']: continue
                    mask = np.isin(d['point_id'], rep['selection']['point_ids'])
                    rep_rows.append(dict(representative=rep['id'], arm=arm, unit=unit,
                        sh_degree=spec['sh_degree'], **aggregate(d, state, mask),
                        **{label + '_points': int((mask & (state == label)).sum()) for label in STATES}))
            for subset, sm in [('all', np.ones(len(pair), bool)), ('occlusion_over_30pct', high)]:
                for group in ['a', 'b', 'c']:
                    for side in ['all', 'front', 'back']:
                        mask = sm & (d['group'] == group)
                        if side != 'all': mask &= d['side'] == side
                        rows.append(dict(arm=arm, unit=unit, start=spec['start'], sh_degree=spec['sh_degree'],
                            subset=subset, group=group, side=side, **aggregate(d, state, mask)))
            start = json.loads((root / 'photo_error_0.json').read_text())
            end = json.loads((root / 'photo_error_3000.json').read_text())
            assert start['candidate_pixel_observations'] == end['candidate_pixel_observations']
            photos.append(dict(arm=arm, candidate_pixel_observations=start['candidate_pixel_observations'],
                candidate_l1_start=start['candidate_l1'], candidate_l1_end=end['candidate_l1'],
                candidate_l1_delta=end['candidate_l1'] - start['candidate_l1'],
                candidate_mse_start=start['candidate_mse'], candidate_mse_end=end['candidate_mse'],
                first_five_psnr_start=start['first_five_train_psnr_db'], first_five_psnr_end=end['first_five_train_psnr_db']))
            log = [json.loads(line) for line in (root / 'metrics.jsonl').read_text().splitlines()]
            assert [r['iteration'] for r in log] == list(range(0, 3001, 100)), arm
            for r in log:
                for o in r['opacity']:
                    curves.append(dict(arm=arm, unit=unit, start=spec['start'], sh_degree=spec['sh_degree'],
                        iteration=r['iteration'], **o, candidate_l1=r['photo_error']['candidate_l1'],
                        first_five_psnr=r['photo_error']['first_five_train_psnr_db']))
            complete.append(arm)
    criteria = []
    for unit in cfg['units']:
        for degree in [3, 0]:
            for subset in ['all', 'occlusion_over_30pct']:
                for side in ['all', 'front', 'back']:
                    selected = {r['start']: r for r in rows if r['unit'] == unit and r['sh_degree'] == degree
                                and r['group'] == 'a' and r['subset'] == subset and r['side'] == side}
                    values = {s: selected[s]['right_only_area_fraction'] if s in selected else None for s in ['equal', 'right', 'wrong']}
                    delta = values['wrong'] - values['right'] if values['wrong'] is not None and values['right'] is not None else None
                    c3 = {s: selected[s]['both_area_fraction'] + selected[s]['neither_area_fraction']
                          if s in selected and selected[s]['area_m2'] else None for s in ['equal', 'right', 'wrong']}
                    criteria.append(dict(unit=unit, sh_degree=degree, subset=subset, side=side,
                        equal_right_only=values['equal'], right_right_only=values['right'], wrong_right_only=values['wrong'],
                        wrong_minus_right_pp=100 * delta if delta is not None else None,
                        criterion1_equal_ge70pct=values['equal'] >= .7 if values['equal'] is not None else None,
                        criterion2_wrong_drop_le10pp=delta >= -.1 if delta is not None else None,
                        **{s + '_both_plus_neither': c3[s] for s in c3},
                        **{'criterion3_' + s + '_le20pct': c3[s] <= .2 if c3[s] is not None else None for s in c3},
                        primary=degree == 3 and subset == 'all'))
    tabledir = DOC / 'results'; tabledir.mkdir(exist_ok=True)
    for name, data in [('outcomes', rows), ('criteria', criteria), ('photo_error', photos), ('opacity_curves', curves), ('representative_outcomes', rep_rows)]:
        save(tabledir / (name + '.json'), dict(rows=data, config_sha256=digest, scientific_verdict=None))
        csv_write(tabledir / (name + '.csv'), data)
    report = dict(task_id='PHD-MAIN-CANDPICK-v1', at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        status='SCORING_COMPLETE' if len(complete) == 24 else 'PARTIAL_TRAINING', completed_arms=complete,
        completed_count=len(complete), designed_count=24, pending=pending,
        config_sha256=digest, script_sha256=sha(__file__), scientific_verdict=None)
    save(tabledir / 'status.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
