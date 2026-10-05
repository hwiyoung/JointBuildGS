"""P2 native-source judgment comparison; isolated, reproducible output only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import time
import traceback

import cv2
import numpy as np
from scipy.spatial import cKDTree

from src.stage2.colmap_io import read_cameras_bin, read_images_bin
from scripts.phd.prior_use_height_probe_v1.photometry import measure_height_sweep
from src.phd.p2_ab_v1.decision import (UNKNOWNS, common_curve, finite_range,
    gaussian_uniform_posterior, posterior_candidate, choose_action, strict_action)

REPO = Path(__file__).resolve().parents[3]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def evenly(length, cap):
    return np.linspace(0, length - 1, min(length, cap), dtype=np.int64)


def normalize(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def candidate_sampling(common, cfg):
    data = np.load(common / 'units.npz', allow_pickle=False)
    units_file = json.loads((common / 'units.json').read_text())
    units = units_file['units'] if isinstance(units_file, dict) else units_file
    spec = cfg['sampling']
    availability, eligible = {}, []
    for unit in units:
        ui = int(unit['unit_index'])
        availability[ui] = {}
        for source in ('mvs', 'als'):
            member = np.flatnonzero((data[f'{source}_unit_index'] == ui)
                                    & (data[f'{source}_patch_type'] == spec['planar_type']))
            ids, counts = np.unique(data[f'{source}_patch_id'][member], return_counts=True)
            if len(ids):
                order = np.lexsort((ids, -counts))
                pi = int(ids[order[0]])
                members = member[data[f'{source}_patch_id'][member] == pi]
                if len(members) >= spec['min_native_points']:
                    availability[ui][source] = (pi, members)
        if availability[ui]:
            eligible.append(unit)
    selected = [units[i] for i in units_file['pilot_unit_indices']]
    xyzs, normals, candidate_ids, mvs_rows, als_rows, records = [], [], [], [], [], []
    selected_records = []

    def add(unit, action, points, point_normals, mr, ar, record):
        ci = len(records)
        start = sum(map(len, xyzs))
        xyzs.append(points)
        normals.append(point_normals)
        candidate_ids.append(np.full(len(points), ci, np.int64))
        mvs_rows.append(mr)
        als_rows.append(ar)
        centre = points.mean(0)
        normal = normalize(np.median(point_normals, axis=0))
        scatter = float(np.sqrt(np.mean(((points - centre) @ normal) ** 2)))
        records.append(dict(candidate_index=ci, unit_index=unit['unit_index'],
            unit_id=unit['unit_id'], source=action, point_start=start, point_stop=start + len(points),
            count=len(points), centroid=centre.tolist(), normal=normal.tolist(),
            source_plane_scatter_m=scatter,
            mvs_tile_rows=np.asarray(mr).astype(int).tolist(),
            als_tile_rows=np.asarray(ar).astype(int).tolist(), **record))
        return ci

    for unit in selected:
        ui = unit['unit_index']
        indices, samples, full = {}, {}, {}
        for source, action in (('mvs', 'IMAGE'), ('als', 'PRIOR')):
            if source not in availability[ui]:
                continue
            patch, rows = availability[ui][source]
            rows = rows[np.argsort(data[f'{source}_tile_rows'][rows], kind='stable')]
            sample = rows[evenly(len(rows), spec['max_points_per_candidate'])]
            full[source], samples[source] = rows, sample
            points = data[f'{source}_xyz'][sample].astype(float)
            pn = data[f'{source}_normals'][sample].astype(float)
            native = data[f'{source}_tile_rows'][sample].astype(np.int64)
            missing = np.full(len(sample), -1, np.int64)
            indices[action] = add(unit, action, points, pn,
                native if source == 'mvs' else missing, native if source == 'als' else missing,
                dict(patch_id=int(patch), native_patch_points_in_unit=len(rows),
                     support_scope='sampled_native_points', generation='native rows; no geometric resampling'))
        if 'mvs' in full and 'als' in samples:
            prior = data['als_xyz'][samples['als']].astype(float)
            mrows = full['mvs']
            distance, near = cKDTree(data['mvs_xyz'][mrows, :2]).query(prior[:, :2])
            valid = distance <= spec['fusion_xy_match_radius_m']
            ar = samples['als'][valid]
            mr = mrows[near[valid]]
            if int(valid.sum()) >= spec['min_native_points']:
                p, m = data['als_xyz'][ar].astype(float), data['mvs_xyz'][mr].astype(float)
                pn, mn = data['als_normals'][ar].astype(float), data['mvs_normals'][mr].astype(float)
                mn = np.where((pn * mn).sum(1)[:, None] < 0, -mn, mn)
                nn = pn + mn
                nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
                angle = np.degrees(np.arccos(np.clip(abs(np.sum(pn * mn, axis=1)), 0, 1)))
                indices['FUSION'] = add(unit, 'FUSION', (p + m) / 2, nn,
                    data['mvs_tile_rows'][mr].astype(np.int64), data['als_tile_rows'][ar].astype(np.int64),
                    dict(patch_id=None, native_patch_points_in_unit=None,
                         support_scope='conditional_matched_point_support',
                         generation='arithmetic mean of explicit native MVS/ALS XY-neighbor pairs; new derived candidate',
                         parent_candidate_indices=[indices['IMAGE'], indices['PRIOR']],
                         parent_max_distance_m=float(np.linalg.norm(p - m, axis=1).max()),
                         parent_max_normal_angle_deg=float(angle.max()),
                         parent_max_xy_match_m=float(distance[valid].max())))
        selected_records.append(dict(unit_id=unit['unit_id'], unit_index=ui,
            bbox_xy=unit['bbox_xy'], candidate_indices=indices,
            source_state={s: 'AVAILABLE_CONDITIONAL_DOMINANT_PLANAR_PATCH' if a in indices else 'NO_ELIGIBLE_PLANAR_PATCH'
                          for s, a in (('mvs', 'IMAGE'), ('als', 'PRIOR'))}))
    arrays = dict(xyz=np.concatenate(xyzs), normals=np.concatenate(normals),
                  candidate_index=np.concatenate(candidate_ids),
                  mvs_tile_rows=np.concatenate(mvs_rows), als_tile_rows=np.concatenate(als_rows))
    denominators = dict(total_fixed_xy_units=len(units), eligible_planar_units=len(eligible),
        excluded_no_eligible_planar_patch=len(units) - len(eligible), selected_units=len(selected),
        eligible_unsampled=len(eligible) - sum(bool(availability[u['unit_index']]) for u in selected),
        selected_without_eligible_planar_patch=sum(not bool(availability[u['unit_index']]) for u in selected),
        candidates=len(records),
        candidate_points=len(arrays['xyz']), unit_measure='2m XY grid units; no certified physical surface area',
        layer_rule='largest planar native patch per source by count, tie smallest patch ID; other layers remain in common inputs')
    return arrays, records, selected_records, denominators


def pair_sigmas(centroid, pairs, cameras, images, scatter, pixel_sigma):
    sigmas = []
    x = np.asarray(centroid)
    for a, b in pairs:
        jacobians = []
        for iid in (a, b):
            im = images[int(iid)]
            k, r = cameras[im.camera_id].K(), im.R()
            cam = r @ x + im.tvec
            if cam[2] <= 0:
                jacobians = []
                break
            j = np.array([[k[0, 0] / cam[2], 0, -k[0, 0] * cam[0] / cam[2] ** 2],
                          [0, k[1, 1] / cam[2], -k[1, 1] * cam[1] / cam[2] ** 2]]) @ r
            jacobians.append(j)
        if not jacobians:
            sigmas.append(np.nan)
            continue
        j = np.concatenate(jacobians)
        if np.linalg.matrix_rank(j) < 3:
            sigmas.append(np.nan)
            continue
        cov = np.linalg.inv(j.T @ j) * pixel_sigma ** 2
        sigmas.append(float(np.sqrt(max(cov[2, 2], 0) + scatter ** 2)))
    return np.asarray(sigmas)


def compare(measurement, candidates, units, cfg):
    comp, mp = cfg['comparison'], cfg['measurement']
    h, pair_ids = measurement['heights'], measurement['pair_view_ids']
    summaries = defaultdict(Counter)
    evidence_cache = {}
    for c in candidates:
        ci = c['candidate_index']
        rho = measurement['rho'][:, :, ci]
        for mode in ('all', 'disjoint', 'limited'):
            curve, keep = common_curve(rho, pair_ids, mp['min_common_pairs'],
                                      disjoint=mode == 'disjoint', limit=1 if mode == 'limited' else None)
            posterior = (gaussian_uniform_posterior(h, rho[:, keep], measurement['sigma_m'][ci, keep],
                         comp['bayes_pi_bins']) if len(keep) >= mp['min_common_pairs'] else None)
            evidence_cache[ci, mode] = (curve, keep, posterior)
    rows, handoff = [], []
    for condition in comp['conditions']:
        for threshold in comp['score_thresholds']:
            for tolerance in comp['tolerances_m']:
                for method in comp['methods']:
                    for ui, unit in enumerate(units):
                        options, offsets = {}, {}
                        for action, ci in unit['candidate_indices'].items():
                            if condition in ('MVS_REMOVED', 'MVS_MARKED_UNUSABLE') and action in ('IMAGE', 'FUSION'):
                                continue
                            c = candidates[ci]
                            prior_shift = condition in ('PRIOR_SHIFT_PLUS_1', 'BOTH_SHIFT_PLUS_1') or (
                                condition == 'LOCAL_PRIOR_SHIFT_PLUS_1' and ui % 2 == 0)
                            image_shift = condition in ('IMAGE_SHIFT_PLUS_1', 'BOTH_SHIFT_PLUS_1')
                            offset = comp['controlled_shift_m'] * (
                                float(image_shift) if action == 'IMAGE' else float(prior_shift) if action == 'PRIOR'
                                else (float(image_shift) + float(prior_shift)) / 2)
                            offsets[action] = offset
                            mode = ('limited' if condition == 'OBSERVATION_LIMIT' else 'disjoint'
                                if method == 'BAYES_GAUSS_UNIFORM' else 'all')
                            curve, keep, post = evidence_cache[ci, mode]
                            score = float(np.interp(offset, h, curve)) if np.isfinite(curve).all() else None
                            shift = comp['shared_shift_radius_m'] if method == 'DISCRETE_RANGE_SHARED_SHIFT' else 0
                            r = finite_range(h, curve, threshold, tolerance, offset, shift)
                            posterior = posterior_candidate(post, h, offset, tolerance)
                            options[action] = dict(candidate_index=ci, offset_z_m=offset, score=score, range=r,
                                posterior=posterior, common_pair_count=len(keep),
                                parent_geometry_compatible=(c.get('parent_max_distance_m', 0)
                                    + abs(float(prior_shift) - float(image_shift)) * comp['controlled_shift_m'] <= tolerance
                                    and c.get('parent_max_normal_angle_deg', 0) <= comp['fusion_max_normal_angle_deg']))
                        selected = choose_action(options, method, threshold, comp['bayes_probability'])
                        selected_evidence = options.get(selected)
                        ci = selected_evidence['candidate_index'] if selected_evidence else None
                        budget = (selected_evidence['range']['conditional_budget_m']
                                  if selected_evidence and method.startswith('DISCRETE_RANGE') else None)
                        row = dict(unit_id=unit['unit_id'], unit_index=unit['unit_index'], method=method,
                            condition=condition, condition_kind='ACTUAL_DEVELOPMENT_INPUT' if condition == 'REAL' else 'CONTROLLED_INPUT_OR_OBSERVATION',
                            threshold=threshold, tolerance_m=tolerance,
                            score_threshold=threshold, epsilon_m=tolerance,
                            shared_shift_m=comp['shared_shift_radius_m'] if method == 'DISCRETE_RANGE_SHARED_SHIFT' else 0.0,
                            posterior_required_mass=comp['bayes_probability'],
                            posterior_acceptance_probability=comp['bayes_probability'], action=selected,
                            conditional_action=selected, strict_current_use_action=strict_action(selected),
                            candidate_source=selected if selected != 'ABSTAIN' else None,
                            selected_candidate=ci, candidate_index=ci,
                            selected_xyz_path='candidates.npz', selected_offset_z_m=offsets.get(selected),
                            selected_native_tile_rows=(candidates[ci]['mvs_tile_rows'] if selected == 'IMAGE'
                                else candidates[ci]['als_tile_rows'] if selected == 'PRIOR' else None) if ci is not None else None,
                            selected_xyz_key='xyz', selected_xyz_index_key='candidate_index', selected_xyz_index=ci,
                            selected_geometry=dict(path='candidates.npz', index_key='candidate_index', index=ci,
                                xyz_key='xyz', normals_key='normals', offset_z_m=offsets.get(selected)) if ci is not None else None,
                            candidate_states=options,
                            source_input_state=unit['source_state'],
                            support_scope=candidates[ci]['support_scope'] if ci is not None else 'none',
                            conditional_displacement_budget_m=budget,
                            budget_scope='finite height-translation diagnostic only; continuous surface unverified' if budget is not None else None,
                            remaining_unknowns=UNKNOWNS, decision_version=cfg['task_id'], camera_version='exact937 supplied common manifest',
                            scientific_verdict=None)
                        rows.append(row)
                        key = (condition, threshold, tolerance, method)
                        summaries[key][selected] += 1
                        if threshold == comp['default_score_threshold'] and tolerance == comp['default_tolerance_m']:
                            handoff.append(row)
    aggregate = [dict(condition=k[0], threshold=k[1], tolerance_m=k[2], method=k[3],
                      conditional_actions=dict(v), strict_current_use_action_counts={'ABSTAIN': len(units)})
                 for k, v in summaries.items()]
    return rows, handoff, aggregate, evidence_cache


def main(config_path):
    started = time.monotonic()
    cfg = json.loads(config_path.read_text())
    root, output = Path(cfg['artifact_root']), Path(cfg['output_root'])
    common = root / cfg['common_root']
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError('output must be a new separately mounted empty directory')
    write_json(output / 'STARTED.json', dict(started=now(), task_id=cfg['task_id'], scientific_verdict=None))
    try:
        cv2.setNumThreads(1)
        arrays, candidates, units, denominators = candidate_sampling(common, cfg)
        views_file = json.loads((common / 'views.json').read_text())
        views = views_file['views'] if isinstance(views_file, dict) else views_file
        decision = [v for v in views if v['role'] == 'decision']
        camera_root = root / cfg['camera_root']
        cameras = read_cameras_bin(camera_root / 'sparse/cameras.bin')
        images = read_images_bin(camera_root / 'sparse/images.bin')
        view_ids = [int(v.get('image_id', v.get('colmap_image_id'))) for v in decision]
        inputs = {str(p): sha(p) for p in (common / 'sample_manifest.json', common / 'units.json',
            common / 'units.npz', common / 'views.json', camera_root / 'sparse/cameras.bin', camera_root / 'sparse/images.bin')}
        for iid in view_ids:
            p = camera_root / 'images' / images[iid].name
            inputs[str(p)] = sha(p)
        sources = [Path(__file__), config_path, REPO / 'src/phd/p2_ab_v1/decision.py',
            REPO / 'scripts/phd/prior_use_height_probe_v1/photometry.py', REPO / 'scripts/phd/warp_ncc_v1/run.py',
            REPO / 'src/stage2/colmap_io.py', REPO / 'docs/experiments/phd/p2_ab_v1/A_DESIGN_ko_v1.md']
        source_hashes = {str(p.relative_to(REPO)): sha(p) for p in sources}
        for p in sources:
            dest = output / 'source_snapshot' / p.relative_to(REPO)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
        write_json(output / 'PREMEASUREMENT.json', dict(frozen_utc=now(), config=cfg, input_sha256=inputs,
            source_sha256=source_hashes, git_head=os.getenv('JBGS_SOURCE_GIT_HEAD'),
            container_image_id=os.getenv('JBGS_CONTAINER_IMAGE_ID'), denominators=denominators,
            decision_view_ids=view_ids, versions=dict(python=platform.python_version(), numpy=np.__version__, opencv=cv2.__version__),
            reference_consumed=False, scientific_verdict=None))
        np.savez_compressed(output / 'candidates.npz', **arrays)
        write_json(output / 'candidates.json', candidates)
        write_json(output / 'selected_units.json', units)
        print(json.dumps(dict(premeasurement='PASS', denominators=denominators, decision_views=view_ids)), flush=True)
        params = cfg['measurement']
        heights = np.arange(params['height_min_m'], params['height_max_m'] + params['height_step_m'] / 2,
                            params['height_step_m'])
        def load(iid):
            p = camera_root / 'images' / images[iid].name
            im = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if im is None:
                raise ValueError(f'Image decode failed {p}')
            return im.astype(np.float32)
        measured = measure_height_sweep(arrays['xyz'], arrays['candidate_index'], heights,
            cameras, images, view_ids, load, params,
            progress=lambda a, b: print(f'Projection {a}/{b}', flush=True))
        measured['sigma_m'] = np.stack([pair_sigmas(c['centroid'], measured['pair_view_ids'], cameras, images,
            c['source_plane_scatter_m'], cfg['comparison']['bayes_pixel_sigma']) for c in candidates])
        measured['metadata'].update(scope='native IMAGE/PRIOR and explicitly derived FUSION candidate height translation',
            prior_only_original_function_reused=True, strict_current_use_certified=False)
        np.savez_compressed(output / 'measurements.npz', **{k: v for k, v in measured.items() if isinstance(v, np.ndarray)})
        write_json(output / 'measurement_metadata.json', measured['metadata'])
        rows, handoff, summary, cache = compare(measured, candidates, units, cfg)
        for name, contents in [('decision_rows.jsonl', rows), ('handoff.jsonl', handoff)]:
            with (output / name).open('w') as stream:
                for row in contents:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        write_json(output / 'decision_summary.json', summary)
        np.savez_compressed(output / 'curves.npz', heights=heights,
            all_pair_curves=np.stack([cache[c['candidate_index'], 'all'][0] for c in candidates]),
            disjoint_pair_curves=np.stack([cache[c['candidate_index'], 'disjoint'][0] for c in candidates]))
        assert all(r['strict_current_use_action'] == 'ABSTAIN' for r in rows)
        assert all(sha(path) == digest for path, digest in inputs.items())
        assert all(sha(REPO / path) == digest for path, digest in source_hashes.items())
        defaults = [s for s in summary if s['threshold'] == cfg['comparison']['default_score_threshold']
                    and s['tolerance_m'] == cfg['comparison']['default_tolerance_m'] and s['condition'] == 'REAL']
        write_json(output / 'TECHNICAL_RETURN.json', dict(task_id=cfg['task_id'], status='TECHNICAL_COMPLETE_NON_CONFIRMATORY',
            completed_utc=now(), elapsed_seconds=time.monotonic() - started, denominators=denominators,
            default_real_results=defaults, pair_count=len(measured['pair_view_ids']), decision_rows=len(rows), handoff_rows=len(handoff),
            scientific_verdict=None, input_and_source_hashes_unchanged=True,
            output_sha256={str(p.relative_to(output)): sha(p) for p in output.rglob('*') if p.is_file()}))
        print(json.dumps(dict(status='TECHNICAL_COMPLETE', default_real_results=defaults)), flush=True)
    except Exception as exc:
        write_json(output / 'FAILED.json', dict(failed_utc=now(), error=repr(exc), traceback=traceback.format_exc(), scientific_verdict=None))
        raise


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=Path, required=True)
    main(ap.parse_args().config.resolve())
