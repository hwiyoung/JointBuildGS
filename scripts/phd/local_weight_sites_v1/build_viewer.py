"""Export an additive, source-bound viewer of C/W cases using frozen geometry."""
import argparse
import csv
import gc
import json
import shutil
import time
from pathlib import Path

import numpy as np

from analyze_final_surfaces import distances, mesh_arrays, read, sha, write


def crop(xyz, faces, low, high):
    selected = []
    for start in range(0, len(faces), 250000):
        part = faces[start:start + 250000]
        triangles = xyz[part]
        keep = (triangles.max(1) >= low).all(1) & (triangles.min(1) <= high).all(1)
        if keep.any():
            selected.append(part[keep])
    if not selected:
        raise ValueError('No native triangles intersect the requested display crop')
    unique, inverse = np.unique(np.concatenate(selected), return_inverse=True)
    return xyz[unique], inverse.reshape(-1, 3).astype(np.uint32)


def sections(xyz, faces, axis, value):
    triangles = xyz[faces]
    offset = triangles[:, :, axis] - value
    keep = (offset.min(1) < 0) & (offset.max(1) > 0)
    triangles, offset = triangles[keep], offset[keep]
    points = np.full((len(triangles), 3, 3), np.nan)
    for k, (a, b) in enumerate([(0, 1), (1, 2), (2, 0)]):
        good = offset[:, a] * offset[:, b] < 0
        t = offset[good, a] / (offset[good, a] - offset[good, b])
        points[good, k] = triangles[good, a] + t[:, None] * (triangles[good, b] - triangles[good, a])
    valid = np.isfinite(points[:, :, 0])
    keep = valid.sum(1) == 2
    return points[keep][valid[keep]].reshape(-1, 2, 3)


def main(config, output, repository):
    started = time.time()
    cfg = read(config)
    output.mkdir(exist_ok=False)
    assets = output / 'assets'
    assets.mkdir()
    bindings = {}

    def bind(path, expected=None):
        path = Path(path)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError(f'Source hash mismatch: {path}')
        bindings[str(path)] = actual
        return path

    def copy(path, name=None, expected=None):
        path = bind(path, expected)
        target = assets / (name or path.name)
        if target.exists():
            assert sha(target) == sha(path)
        else:
            shutil.copyfile(path, target)
        return 'assets/' + target.name

    def buffer(name, values, dtype='<f4'):
        values = np.asarray(values, dtype=dtype)
        target = assets / (name + '.bin')
        values.tofile(target)
        return dict(url='assets/' + target.name, bytes=target.stat().st_size,
                    shape=list(values.shape), sha256=sha(target), dtype=dtype)

    def packet_array(folder, descriptor, dtype):
        path = bind(folder / descriptor['url'], descriptor['sha256'])
        values = np.fromfile(path, dtype=dtype)
        assert path.stat().st_size == descriptor['bytes']
        return values.reshape(descriptor['shape'])

    art = Path(cfg['artifact_root'])
    root = art / cfg['comparison_relative']
    old = root / cfg['old_sites_folder']
    search = art / cfg['search_relative']
    uas = root / cfg['uas_folder']
    analysis = root / cfg['analysis']
    reconciliation = art / cfg['reconciliation_relative']
    ledger_receipt = read(bind(reconciliation / 'receipt.json'))
    ledger = list(csv.DictReader(bind(reconciliation / 'case_ledger.csv', ledger_receipt['file_sha256']['case_ledger.csv']).open()))
    by_id = {row['case_id']: row for row in ledger}
    assert len(by_id) == len(cfg['ordered_ids']) == 20 and set(by_id) == set(cfg['ordered_ids'])
    old_receipt = read(bind(old / 'receipt.json'))
    old_review = read(bind(old / 'reviewed_sites.json', old_receipt['artifact_sha256']['reviewed_sites.json']))
    c_cases = {row['id']: row for row in old_review['cases']}
    complete = read(bind(search / 'completion_receipt.json'))
    inspection = read(bind(search / 'inspection/receipt.json', complete['artifact_hashes']['inspection/receipt.json']))
    w_cases = {row['case']['id']: row for row in inspection['cases']}
    z07_folder = art / cfg['z07_relative']
    z07 = read(bind(z07_folder / 'receipt.json'))
    assert z07['status'] == 'PASS_FROZEN_REFERENCE_SUBSET_AUDIT'
    z07_rows = list(csv.DictReader(bind(z07_folder / 'samples.csv', z07['output_sha256']['samples.csv']).open()))
    upper_ids = {int(r['reference_row']) for r in z07_rows if r['near_upper_sample'] == 'True'}
    assert len(upper_ids) == 80
    frozen_receipt = read(bind(root / cfg['failure_folder'] / 'receipt.json'))
    census = read(bind(root / cfg['failure_folder'] / 'census.json', frozen_receipt['files']['census.json']))
    theta = np.deg2rad(cfg['object_axis_angle_degrees'])
    basis = np.array([[np.cos(theta), np.sin(theta)], [np.sin(theta), -np.cos(theta)]])

    def transform(xyz):
        uvz = np.column_stack([xyz[:, :2] @ basis.T, xyz[:, 2]])
        uvz[:, 1] *= -1
        return uvz

    def metric(values):
        return dict(n=len(values), median_m=float(np.median(values)), p90_m=float(np.quantile(values, .9)),
                    within_05m_percent=float(np.mean(values <= .5) * 100),
                    sorted_m=np.sort(values).round(6).tolist())

    review = []
    map_regions = []
    checks = []
    roles = ['prior', 'mvs', 'da3', 'local_prior0']
    for region in ['R1', 'R2', 'R3', 'R4', 'R5']:
        for name, digest in census['regions'][region]['inputs_sha256'].items():
            bind(uas / name, digest)
        reference = np.load(uas / f'{region}_reference.npz')['xyz']
        ref_display = transform(reference)
        ud = np.load(uas / f'{region}_uas_distances.npz')
        pd = np.load(uas / f'{region}_uas_to_prior.npy')
        paired = np.load(bind(analysis / f'{region}_paired_samples.npz'))
        input_xyz = paired['xyz'][paired['source'] == 0]
        mvs_display = transform(input_xyz)
        diagnostic = np.load(bind(search / f'result/{region}_sample_diagnostic.npz'))
        np.testing.assert_allclose(diagnostic['xyz'], input_xyz, atol=0, rtol=0)
        uv = mvs_display[:, :2].copy()
        uv[:, 1] *= -1
        _, display_ids = np.unique(np.floor(uv / cfg['map_display_voxel_m']).astype(np.int32), axis=0, return_index=True)
        map_regions.append(dict(id=region, points=uv[display_ids].round(3).tolist(), bounds=[uv.min(0).tolist(), uv.max(0).tolist()]))
        active = []
        for cid in cfg['ordered_ids']:
            row = by_id[cid]
            if row['region'] != region:
                continue
            detail = dict(id=cid, title=row['name'], region=region, zone=row['zone'],
                baseline=row['baseline'], priority=cid in cfg['priority_ids'], group=cfg['review_groups'][cid],
                reason=row['reason'], hypothesis=row['weight_hypothesis'],
                scientific_verdict=None, metric_basis='UAS' if cid.startswith('C') else 'MVS',
                related_case=row['related_case'], models={}, validation=[])
            if cid.startswith('C'):
                case = c_cases[cid]
                folder = old if (old / case['case_file']).exists() else old / 'z07_check'
                packet = read(bind(folder / case['case_file']))
                lo = np.array(case['uvz_min'])
                hi = lo + case['size']
                uvz = ref_display.copy()
                uvz[:, 1] *= -1
                ids = np.flatnonzero(((uvz >= lo) & (uvz < hi)).all(1))
                assert len(ids) == int(row['n'])
                query = ref_display[ids]
                expected = {'prior': pd[ids], **{role: ud[role][ids] for role in roles[1:]}}
                detail.update(center=packet['center'], display_box=packet['display_box'], case_box=packet['case_box'],
                    depth_summary=case['depth_summary'], source_layer_audit=case['reference_layer_audit'],
                    photos=copy(folder / case['photo_file']), photo_count=len(case['photos_selected']),
                    observations=copy(folder / f'{cid}_observations.json'), original_section=copy(folder / case['section_file']),
                    limitation='원영상 투영·상단 UAS 근접성만으로 가시성이나 표면 종류가 확정되지는 않습니다. 입력 depth 차이에 가림이 섞일 수 있습니다.')
                detail['_packet'] = (folder, packet)
            else:
                inspection_case = w_cases[cid]
                case = inspection_case['case']
                ids = np.array(case['sample_indices'])
                query = mvs_display[ids]
                expected = {'prior': diagnostic['prior_surface_distance'][ids],
                            **{role: diagnostic['distance_' + role][ids] for role in roles[1:]}}
                lo, hi = query.min(0), query.max(0)
                center = (lo + hi) / 2
                detail.update(center=center.tolist(), display_box=[(lo - cfg['w_crop_margin_m']).tolist(), (hi + cfg['w_crop_margin_m']).tolist()],
                    case_box=[lo.tolist(), hi.tolist()], support=case,
                    reference=inspection_case['reference'], view_observations=inspection_case['observations'],
                    photos=copy(search / 'inspection' / inspection_case['photo']) if inspection_case['observations'] else None,
                    photo_count=len(inspection_case['observations']),
                    observations=copy(search / 'inspection' / f'{cid}.json'),
                    limitation='MVS 입력 표본과의 일치도이며 독립 정확도가 아닙니다. 주변 UAS 근접성도 같은 표면임을 보증하지 않습니다.')
            if cid == 'C10':
                detail['reason'] = '낮은 지붕 띠에서 UAS→Prior는 약 0.122m, UAS→MVS–GeoGS는 약 1.608m입니다. 상단 대응 80점에서도 이 차이가 유지됩니다.'
                detail['hypothesis'] = '현재 참조에 가까운 Prior 구조를 보존하고, 불확실한 영상 깊이 감독의 영향을 국소적으로 낮출 수 있는지 검토합니다.'
                detail['limitation'] = '상단 대응 80점 모두 Prior≤0.25m·MVS 결과>1m이지만, 실제 가시성·표면 대응과 원인은 미확정입니다. Z08 prior0 결과는 Z07 맞춤 보존 실험이 아닙니다.'
                detail['z07_audit'] = copy(z07_folder / 'receipt.json', 'z07_reassessment.json')
            assert len(query) == int(row['n'])
            for role, key in [('prior', 'prior_m'), ('mvs', 'mvs_geogs_m'), ('da3', 'da3_geogs_m')]:
                np.testing.assert_allclose(np.median(expected[role]), float(row[key]), atol=1e-9, rtol=0)
            low, high = np.array(detail['display_box'])
            for name, points in [('uas', ref_display), ('mvs_input', mvs_display)]:
                keep = ((points >= low) & (points <= high)).all(1)
                detail[name] = buffer(cid + '_' + name, points[keep])
            detail['scored'] = buffer(cid + '_scored', query)
            cohorts = {'all': np.ones(len(ids), dtype=bool)}
            if cid == 'C10':
                cohorts['upper'] = np.array([int(i) in upper_ids for i in ids])
                cohorts['lower'] = ~cohorts['upper']
            detail['cohorts'] = {}
            for name, keep in cohorts.items():
                detail['cohorts'][name] = dict(indices=np.flatnonzero(keep).tolist(), n=int(keep.sum()),
                    metrics={role: metric(expected[role][keep]) for role in roles},
                    prior_near_mvs_far_count=int(((expected['prior'][keep] <= .25) & (expected['mvs'][keep] > 1)).sum()))
            detail['_query'] = query
            detail['_expected'] = expected
            active.append(detail)

        def export_model(detail, role, xyz, faces, provenance):
            cid = detail['id']
            query = detail['_query']
            actual, closest = distances(xyz.astype(np.float32), faces.astype(np.uint32), query.astype(np.float32), cfg['distance_cap_m'])
            error = float(np.max(abs(actual - detail['_expected'][role])))
            assert error < cfg['distance_replay_tolerance_m'], (cid, role, error)
            detail['models'][role] = dict(xyz=buffer(cid + '_' + role + '_xyz', xyz),
                indices=buffer(cid + '_' + role + '_indices', faces, '<u4'),
                closest=buffer(cid + '_' + role + '_closest', closest),
                sections={axis: buffer(cid + '_' + role + '_section_' + axis, sections(xyz, faces, index, detail['center'][index]))
                          for axis, index in [('u', 1), ('v', 0)]},
                source=provenance)
            check = dict(case_id=cid, role=role, n=len(query), max_distance_replay_error_m=error)
            detail['validation'].append(check)
            checks.append(check)

        for detail in [item for item in active if '_packet' in item]:
            folder, packet = detail['_packet']
            for role in roles:
                model = packet['models'][role]
                xyz = packet_array(folder, model['xyz'], '<f4')
                faces = packet_array(folder, model['indices'], '<u4')
                export_model(detail, role, xyz, faces, model['source'])
        w_active = [item for item in active if '_packet' not in item]
        if w_active:
            prior = read(bind(uas / f'{region}_prior_reference.json'))
            models = {'prior': prior, **read(bind(analysis / f'{region}_summary.json'))['metadata']['models']}
            for role in roles:
                model = models[role]
                path = bind(Path(model['source'] if role == 'prior' else model['path']), model['sha256'])
                if role == 'prior':
                    arrays = np.load(path)
                    xyz, faces = transform(arrays['xyz']), arrays['faces']
                else:
                    vertices, raw_faces = mesh_arrays(path)
                    xyz, faces = transform(np.column_stack([vertices[k] for k in 'xyz'])), raw_faces['indices']
                for detail in w_active:
                    local_xyz, local_faces = crop(xyz, faces, *np.array(detail['display_box']))
                    export_model(detail, role, local_xyz, local_faces, model)
                del xyz, faces
                gc.collect()
                print('GEOMETRY', region, role, len(w_active), flush=True)
        for detail in active:
            detail = {k: v for k, v in detail.items() if not k.startswith('_')}
            write(assets / (detail['id'] + '.json'), detail)
            center_uv = [detail['center'][0], -detail['center'][1]]
            review.append({k: detail[k] for k in ['id', 'title', 'region', 'zone', 'baseline', 'priority', 'group', 'metric_basis', 'reason']}
                          | dict(center_uv=center_uv, file='assets/' + detail['id'] + '.json'))
        print('REGION COMPLETE', region, len(active), flush=True)
        del reference, ref_display, paired, diagnostic, ud, pd
        gc.collect()
    order = {cid: i for i, cid in enumerate(cfg['ordered_ids'])}
    review.sort(key=lambda item: order[item['id']])
    write(output / 'catalog.json', dict(task_id=cfg['task_id'], scientific_verdict=None, default_case=cfg['default_case'],
        case_count=len(review), priority_count=sum(item['priority'] for item in review), cases=review,
        frame='x=u, y=-v, z=local source z [m]; no vertical exaggeration', crs=cfg['crs'], map_regions=map_regions,
        limitations=['20 records are not 20 independent sites.', 'Priority is a review status, not a proof of local-weight necessity.',
                      'UAS-scored C cases and MVS-scored W cases use different cohorts and metrics.']))
    app = repository / 'src/apps/local_weight_sites_v1'
    for name in ['index.html', 'style.css', 'viewer.js']:
        shutil.copyfile(bind(app / name), output / name)
    copy(repository / 'docs/experiments/phd/local_weight_sites_v1/CANDIDATE_LEDGER_20260919_ko.md', 'candidate_ledger.md')
    assert len(checks) == 80
    receipt = dict(task_id=cfg['task_id'], status='PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY', scientific_verdict=None,
        case_count=len(review), priority_count=sum(item['priority'] for item in review), geometry_replay_checks=checks,
        z07_upper_reassessment_retained=True, source_bindings=bindings, config_sha256=sha(config),
        script_sha256=sha(__file__), elapsed_seconds=time.time() - started, training_changes=False,
        map_decimation='Display only; exact case and evaluation rows remain unchanged',
        files={str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    write(output.parent / 'build_receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['status', 'case_count', 'priority_count', 'elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', type=Path, default=Path('/repo'))
    args = parser.parse_args()
    try:
        main(args.config, args.output, args.repository)
    except Exception as exc:
        write(args.output.parent / 'build_failure.json', dict(status='FAIL', error=repr(exc), scientific_verdict=None))
        raise
