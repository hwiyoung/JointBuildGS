"""Exact photo-point/patch join, eligibility census and pre-training place lock."""
import csv
import itertools
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from input_audit import sha, bind, PH, PC
from rules import classify_places

OUT, DOC, CFG = Path('/out'), Path('/docs'), Path('/config')
W = PH / 'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
SITES = {'B173': 'B173nb_b10', 'R1': 'R1rep_b10'}
TAU = {'ALS': .1266, 'LoD2': .2}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), f'refuse replacement: {path}'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def array_json(value):
    if isinstance(value, dict):
        return {k: array_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [array_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return array_json(value.tolist())
    if isinstance(value, np.generic):
        return array_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def table(name, rows):
    save(DOC / 'tables' / (name + '.json'), dict(rows=rows, scientific_verdict=None))
    with (DOC / 'tables' / (name + '.csv')).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def membership(centre, limits, angle):
    a = np.deg2rad(angle)
    uv = centre[:, :2] @ np.array([[np.cos(a), np.sin(a)], [np.sin(a), -np.cos(a)]]).T
    return ((uv[:, 0] >= limits['eval_u'][0]) & (uv[:, 0] < limits['eval_u'][1]) &
            (uv[:, 1] >= limits['eval_v'][0]) & (uv[:, 1] < limits['eval_v'][1]))


def load_points(prior, sources):
    pieces = []
    keys = ['point_id', 'centre', 'normal', 'tangent1', 'tangent2', 'mvs_p',
            'area', 'building', 'kind', 'surf', 'geometry_valid', 'judgment', 'patch_count']
    for p in sorted((PC / 'points').glob(f'*__{prior}.npz')):
        tile = p.stem.split('__')[0]
        mpath = PC / 'geometry' / f'{tile}__{prior}__mapping.npz'
        rawpath = W / 'patch_values' / f'{tile}__{prior}__R1.5.npz'
        with np.load(p) as z, np.load(mpath) as mapping, np.load(rawpath) as raw:
            assert not z['holdout'].any()
            d = {k: z[k] for k in keys}
            n = len(d['point_id'])
            lookup = np.full(int(mapping['point_index'].max()) + 1, -1, int)
            lookup[z['geometry_index']] = np.arange(n)
            pos = lookup[mapping['point_index']]
            valid = pos >= 0
            source = mapping['source_index'][valid]; owner = pos[valid]
            assert np.array_equal(raw['patch_id'][source], mapping['patch_id'][valid])
            assert not raw['holdout'][source].any()
            weights = raw['area'][source]
            area = np.bincount(owner, weights=weights, minlength=n)
            assert np.allclose(area, d['area'], rtol=1e-12, atol=1e-10)
            assert np.array_equal(np.bincount(owner, minlength=n), d['patch_count'])
            d['raw_centre'] = np.column_stack([
                np.bincount(owner, weights=weights * raw['raw_centre'][source, k], minlength=n) / area
                for k in range(3)])
            g = raw['gt_p'][source]
            has = (raw['gt_status'][source] == 0) & np.isfinite(g)
            counts = np.bincount(owner[has], minlength=n)
            d['gt_p'] = np.full(n, np.nan)
            ix = np.flatnonzero(counts)
            if len(ix):
                d['gt_p'][ix] = ndimage.median(g[has], labels=owner[has] + 1, index=ix + 1)
            d['gt_patch_count'] = counts
            d['gt_coverage_area'] = np.bincount(owner[has], weights=weights[has], minlength=n)
            m = raw['mvs_p'][source]; finite = np.isfinite(m)
            check_m = ndimage.median(m[finite], labels=owner[finite] + 1,
                                    index=np.flatnonzero(np.bincount(owner[finite], minlength=n)) + 1)
            assert np.allclose(check_m, d['mvs_p'][np.isfinite(d['mvs_p'])], rtol=0, atol=1e-10)
            d['tile'] = np.full(n, tile)
            pieces.append(d)
        sources.extend(bind(f) for f in [p, mpath, rawpath])
    return {k: np.concatenate([d[k] for d in pieces]) for k in pieces[0]}


def representative(d, mask):
    """Densest 1.5m tangent square on one prior surface/building; 1..3m2.

    Point IDs break every tie; no model output is used. Every selected point is
    within 0.75m in both tangents of its seed and within 0.15m of its prior plane.
    """
    ids = np.flatnonzero(mask)
    if not len(ids):
        return None
    xyz = d['centre'][ids]; tree = cKDTree(xyz)
    best = None
    for seed in ids[np.argsort(d['point_id'][ids])]:
        cand = ids[tree.query_ball_point(d['centre'][seed], 1.1)]
        delta = d['centre'][cand] - d['centre'][seed]
        keep = ((d['building'][cand] == d['building'][seed]) & (d['surf'][cand] == d['surf'][seed]) &
                (d['tile'][cand] == d['tile'][seed]) &
                (np.abs(delta @ d['tangent1'][seed]) <= .75000001) &
                (np.abs(delta @ d['tangent2'][seed]) <= .75000001) &
                (np.abs(delta @ d['normal'][seed]) <= .15))
        cand = cand[keep]
        # Keep only the connected component containing the seed, radius 0.76m.
        local = cKDTree(d['centre'][cand])
        reached = {int(np.flatnonzero(cand == seed)[0])}; todo = list(reached)
        while todo:
            i = todo.pop()
            new = set(local.query_ball_point(d['centre'][cand[i]], .76)) - reached
            reached.update(new); todo.extend(new)
        cand = cand[sorted(reached)]
        area = float(d['area'][cand].sum())
        if not 1. <= area <= 3.:
            continue
        rank = (-len(cand), -area, str(d['point_id'][seed]))
        if best is None or rank < best[0]:
            best = (rank, dict(seed_point_id=str(d['point_id'][seed]),
                     point_ids=sorted(d['point_id'][cand].tolist()), points=len(cand), area_m2=area,
                     centre=d['centre'][seed].tolist(), building=str(d['building'][seed]),
                     right=sorted(set(d['right'][cand])), side=sorted(set(d['side'][cand]))))
    return best[1] if best else None


def main():
    assert not (CFG / 'places_v1.json').exists()
    config_path = Path('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json')
    pc = json.loads(config_path.read_text())
    combos = pc['judgments']['candidates']
    assert combos[4] == dict(delta=.10, s_min=.3)
    assert combos[0] == dict(delta=.05, s_min=0)
    guide = Path('/repo/docs/experiments/phd/main_photocheck_v1/데이터_읽기.md')
    assert '4번 열' in guide.read_text()
    ranges_path = PH / 'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/box_ranges.json'
    ranges = json.loads(ranges_path.read_text())
    framepath = Path('/repo/configs/phd/main_widen0_v2/widen0_v2.json')
    frame = json.loads(framepath.read_text())['frame']
    rules = dict(task_id='PHD-MAIN-CANDPICK-v1', scientific_verdict=None,
        source_correction='Direct user: photo-check v2 was a mistaken name for PHOTOCHECK-v1 final points/patches.',
        main_judgment=dict(column_zero_based=4, column_one_based=5, delta=.10, s_min=.3),
        supplemental_judgment=dict(column_zero_based=0, column_one_based=1, delta=.05, s_min=0.,
                                   use='place counts and areas only; never training/scoring'),
        tau_m=TAU, crs='EPSG:25832', world_shift_xyz_m=[690953, 5336071, 604],
        region='Inherited B173nb_b10 / R1rep_b10 evaluation UV limits, area-weighted raw prior point centre, lower inclusive upper exclusive.',
        point_gt='Median finite gt_p of original owned patches with gt_status==0, matching PHOTOCHECK point figure convention. Coverage retained.',
        point_mvs='Existing final point mvs_p; checked against median finite owned source patch values.',
        point_area='Sum of original owned patch surface areas, not forced 0.25m2; one primary building per point (inherited largest-area contributor).',
        representative='Densest connected eligible points in 1.5m tangent square on one surface/building; area 1..3m2; plane tolerance .15m; adjacency .76m; maximize point count then area then lexicographic seed point ID.',
        exclusions='missing_mvs, gap_below_2tau, missing_gt, both_right, both_wrong in order; geometry failure is separate and prevents scene execution.',
        sources=[bind(config_path), bind(guide), bind(ranges_path), bind(framepath)],
        rules_sha256=sha(Path(__file__).with_name('rules.py')), generator_sha256=sha(__file__),
        optimizer_steps_before_lock=0)
    table_rows, exclusions, execution, selected, reps = [], [], [], {}, []
    all_inputs = []
    for prior in ['ALS', 'LoD2']:
        d = load_points(prior, all_inputs)
        assert len(np.unique(d['point_id'])) == len(d['point_id'])
        for site, legacy in SITES.items():
            scope = membership(d['raw_centre'], ranges[legacy], frame['u_axis_angle_degrees_ccw_from_easting']) & (d['kind'] == 1)
            unit = {k: v[scope] for k, v in d.items()}
            for column, label in [(4, 'main_display'), (0, 'supplement_stage1')]:
                c = classify_places(unit['mvs_p'], unit['gt_p'], TAU[prior], unit['judgment'][:, column])
                for right, group, side in itertools.product(['image', 'prior'], ['a', 'b', 'c'], ['front', 'back']):
                    m = c['eligible'] & (c['right'] == right) & (c['group'] == group) & (c['side'] == side)
                    table_rows.append(dict(site=site, prior=prior, judgment=label, column_zero_based=column,
                        right=right, group=group, side=side, points=int(m.sum()), area_m2=float(unit['area'][m].sum()),
                        buildings=int(len(np.unique(unit['building'][m])))))
                if column == 4:
                    for reason in ['missing_mvs', 'gap_below_2tau', 'missing_gt', 'both_right', 'both_wrong', 'eligible']:
                        m = c['reason'] == reason
                        exclusions.append(dict(site=site, prior=prior, reason=reason, points=int(m.sum()),
                            area_m2=float(unit['area'][m].sum()), buildings=int(len(np.unique(unit['building'][m])))))
                    assert sum(r['points'] for r in exclusions if r['site'] == site and r['prior'] == prior) == len(unit['point_id'])
                    mask = c['eligible']
                    kept = {k: v[mask] for k, v in unit.items() if k != 'judgment'}
                    kept.update({k: v[mask] for k, v in c.items() if k != 'eligible'})
                    kept['judgment'] = unit['judgment'][mask, 4]
                    selected[f'{site}_{prior}'] = kept
                    bad = ~kept['geometry_valid']
                    execution.append(dict(site=site, prior=prior, selected_points=int(mask.sum()),
                        invalid_frame_points=int(bad.sum()), status='PASS' if not bad.any() else 'STOP_INVALID_FRAME'))
    specs = [('B173_wing', 'B173_ALS', 'DEBY_LOD2_4959326', 'image', 'back'),
             ('R1_stairs', 'R1_LoD2', 'DEBY_LOD2_4906975', 'image', 'front'),
             ('leaf_flat_roof', 'R1_LoD2', 'DEBY_LOD2_4907519', 'prior', None),
             ('B173_deceptive_photo', 'B173_ALS', 'DEBY_LOD2_4959326', None, None)]
    for name, key, building, right, side in specs:
        d = selected[key]
        condition = d['geometry_valid'].copy()
        if right: condition &= d['right'] == right
        if side: condition &= d['side'] == side
        if name == 'B173_deceptive_photo': condition &= d['group'] == 'c'
        named = condition & (d['building'] == building)
        if name == 'B173_wing':
            x, y = d['centre'][:, :2].T
            named &= (x >= 136.63) & (x <= 146.68) & (y >= 96.32) & (y <= 99.34)
        result = representative(d, named)
        fallback = result is None
        if fallback: result = representative(d, condition)
        reps.append(dict(id=name, unit=key, requested_building=building, replacement=fallback,
            selection=result, status='AVAILABLE' if result else 'UNAVAILABLE_NO_1_TO_3M2_COMPONENT',
            qualification=('Photo-deception stratum; exact glass material unverified before visual inspection. Never label glass solely from this stratum.'
                           if name == 'B173_deceptive_photo' else None)))
    for key, d in selected.items():
        path = OUT / 'places' / (key + '.npz'); path.parent.mkdir(parents=True, exist_ok=True)
        assert not path.exists()
        np.savez_compressed(path, **d)
        rules.setdefault('units', {})[key] = dict(points=len(d['point_id']),
            area_m2=float(d['area'].sum()), payload=bind(path), point_ids=d['point_id'].tolist())
    rules.update(representatives=reps, input_sources=all_inputs, geometry_checks=execution,
                 locked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
    save(CFG / 'places_v1.json', array_json(rules))
    save(CFG / 'places_v1.lock.json', dict(sha256=sha(CFG / 'places_v1.json'), locked_at=rules['locked_at'],
                                        optimizer_steps=0, scientific_verdict=None))
    table('places', table_rows); table('exclusions', exclusions); table('geometry', execution)
    save(DOC / 'representatives_v1.json', array_json(dict(rows=reps, scientific_verdict=None)))
    print(json.dumps(rules['units'], ensure_ascii=False, default=str)[:1200], flush=True)


if __name__ == '__main__':
    main()
