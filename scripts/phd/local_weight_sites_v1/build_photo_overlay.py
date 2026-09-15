"""Add exact point-to-image projections to a hash-verified frozen viewer export."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(config, art, output, repository):
    started = time.time()
    cfg = read(config)
    base = read(repository / 'viewer_v1.json')
    parent = art / cfg['parent_viewer_relative']
    prior_receipt = read(parent / 'build_receipt.json')
    assert prior_receipt['status'] == 'PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY'
    for name, digest in prior_receipt['files'].items():
        assert sha(parent / 'site' / name) == digest, name
    shutil.copytree(parent / 'site', output)
    root = art / base['comparison_relative']
    run = read(root / 'config.json')
    search = art / base['search_relative']
    search_cfg = read(search / 'config.json')
    catalog = read(output / 'catalog.json')
    theta = np.deg2rad(base['object_axis_angle_degrees'])
    basis = np.array([[np.cos(theta), np.sin(theta)], [np.sin(theta), -np.cos(theta)]])
    bindings, checks, regions = {}, [], {}

    def bind(path):
        bindings[str(path)] = sha(path)
        return path

    for entry in catalog['cases']:
        cid, region = entry['id'], entry['region']
        detail = read(output / entry['file'])
        if region not in regions:
            inp = art / run['r1_prep_relative'] / 'result/input' if region == 'R1' else root / region / 'preparation/input'
            split = read(bind(inp / 'scene/split_manifest.json'))
            ref = np.load(bind(root / base['uas_folder'] / (region + '_reference.npz')))['xyz']
            diagnostic = np.load(bind(search / 'result' / (region + '_sample_diagnostic.npz')))
            audit = art / search_cfg['r1_audit_relative'] if region == 'R1' else root / region / 'audit/result'
            pv = np.load(bind(audit / 'per_view_relations.npz'))
            regions[region] = (inp, {v['name']: v for v in split['train']}, ref, diagnostic, pv)
        inp, cameras, ref, diagnostic, pv = regions[region]
        if detail['metric_basis'] == 'UAS':
            display = np.column_stack([ref[:, :2] @ basis.T, ref[:, 2]])
            display[:, 1] *= -1
            low, high = np.array(detail['case_box'])
            # Display y=-v reverses the half-open membership boundary.
            ids = np.flatnonzero((display[:, 0] >= low[0]) & (display[:, 0] < high[0]) &
                                (display[:, 1] > low[1]) & (display[:, 1] <= high[1]) &
                                (display[:, 2] >= low[2]) & (display[:, 2] < high[2]))
            xyz = ref[ids]
            observations = read(output / detail['observations'])
            view_names = observations['selected']
            old_views = {v['name']: v for v in observations['views']}
        else:
            ids = np.array(detail['support']['sample_indices'])
            xyz = diagnostic['xyz'][ids]
            old_views = {v['name']: v for v in detail['view_observations']}
            view_names = list(old_views)
        display = np.column_stack([xyz[:, :2] @ basis.T, xyz[:, 2]])
        display[:, 1] *= -1
        exact = np.fromfile(output / detail['scored']['url'], dtype='<f4').reshape(-1, 3)
        assert len(ids) == detail['cohorts']['all']['n']
        error = float(np.max(abs(display - exact)))
        assert error < cfg['display_point_replay_tolerance_m'], (cid, error)
        photo_views = []
        for name in view_names:
            camera = cameras[name]
            R, t, K = [np.array(camera[k]) for k in ['R', 't', 'K']]
            cam = xyz @ R.T + t
            q = cam @ K.T
            uv = q[:, :2] / q[:, 2, None]
            width, height = camera['width'], camera['height']
            xy = np.rint(uv).astype(int)
            in_frame = (cam[:, 2] > 0) & (xy[:, 0] >= 0) & (xy[:, 0] < width) & (xy[:, 1] >= 0) & (xy[:, 1] < height)
            supported = np.zeros(len(ids), dtype=bool)
            old = old_views[name]
            if detail['metric_basis'] == 'UAS':
                bbox_error = float(np.max(abs(np.array([uv.min(0), uv.max(0)]) -
                                             np.array([old['projection_uv_min'], old['projection_uv_max']]))))
                assert bbox_error < cfg['projection_replay_tolerance_px'], (cid, name, bbox_error)
            else:
                ri = list(map(str, pv['names'])).index(name)
                supported = (pv['mvs'][ri, ids] > 0) & in_frame
                assert int(supported.sum()) == old['supported_points'], (cid, name)
                bbox_error = None
            source = inp / 'scene/images' / name
            assert sha(bind(source)) == camera['sha256']
            with Image.open(source) as im:
                assert im.size == (width, height)
            relative = 'assets/photo_' + region + '_' + name
            target = output / relative
            if target.exists():
                assert sha(target) == camera['sha256']
            else:
                shutil.copyfile(source, target)
            shown = uv[in_frame]
            assert len(shown)
            lo, hi = shown.min(0), shown.max(0)
            center = (lo + hi) / 2
            half = max(cfg['crop_min_half_width_px'], float(max(hi - lo)) * cfg['crop_patch_margin_factor'])
            crop = [max(0, float(center[0] - half)), max(0, float(center[1] - half)),
                    min(width, float(center[0] + half)), min(height, float(center[1] + half))]
            points = [dict(id=i + 1, source_row=int(ids[i]), xy=uv[i].tolist(), camera_z_m=float(cam[i, 2]),
                           in_frame=bool(in_frame[i]), mvs_supported=bool(supported[i])) for i in range(len(ids))]
            photo_views.append(dict(name=name, image=relative, width=width, height=height, crop=crop,
                                    points=points, in_frame_count=int(in_frame.sum()),
                                    supported_count=int(supported.sum()) if cid.startswith('W') else None,
                                    source_sha256=camera['sha256'], camera={k:camera[k] for k in ['R','t','K']},
                                    visibility='NOT_CERTIFIED_BY_PROJECTION'))
            checks.append(dict(case=cid, camera=name, points=len(ids), projected=int(in_frame.sum()),
                               supported=int(supported.sum()) if cid.startswith('W') else None,
                               historical_projection_max_error_px=bbox_error, display_max_error_m=error,
                               source_image_sha256=camera['sha256']))
        detail['photo_views'] = photo_views
        detail['photo_projection_policy'] = cfg['visibility_policy']
        detail['priority'] = cid in cfg['priority_ids']
        if cid == 'W019':
            detail.update(group='held',
                reason='외벽 하단의 작은 부속 구조 주변 MVS 10점에서 출력과 약 2m 차이가 남습니다. 옆면·부속물·가림의 대응이 불분명해, 지붕 개선 사례와 구분하여 보류합니다.',
                hypothesis='먼저 투영점이 실제 어느 옆면·부속물에 대응하는지 확인합니다. image depth 증량은 대응 확인 뒤의 조건부 가설이며 현재 우선 학습 대상은 아닙니다.',
                limitation='사용자 시각 검토(2026-09-21)를 반영해 우선 개선에서 옆면 대응 진단으로 변경했습니다. 2m MVS 잔차는 유지되지만 가중치 원인이나 정확도 저하의 확정은 아닙니다.')
        if cid in cfg['da3_primary_review']:
            detail['baseline_note'] = 'DA3 개선 검토 · MVS는 이 패치에서 잘 맞는 비교 결과'
        elif cid == 'C10':
            detail['baseline_note'] = 'MVS 우선 개선 검토 · 국소 가중치 효과는 미검증'
        elif cid == 'W019':
            detail['baseline_note'] = 'MVS 옆면 대응 보류 · 우선 가중치 실험에서 제외'
        write(output / entry['file'], detail)
        for key in ['priority', 'group', 'reason']:
            entry[key] = detail[key]
        print(cid, len(photo_views), 'views;', len(ids), 'exact points', flush=True)
    catalog.update(task_id=cfg['task_id'], priority_count=len(cfg['priority_ids']),
                   review_revision=cfg['review_revision'], mvs_primary_review=cfg['mvs_primary_review'],
                   da3_primary_review=cfg['da3_primary_review'])
    write(output / 'catalog.json', catalog)
    for name in ['index.html','viewer.js','style.css']:
        shutil.copyfile(repository / 'src/apps/local_weight_sites_v1' / name, output / name)
    shutil.copyfile(repository / 'candidate_ledger.md', output / 'assets/candidate_ledger.md')
    # Geometry and all frozen numerical cohorts stay byte-identical to the parent.
    for entry in catalog['cases']:
        before, after = read(parent / 'site' / entry['file']), read(output / entry['file'])
        for key in ['models','scored','uas','mvs_input','cohorts','validation']:
            assert before[key] == after[key], (entry['id'], key)
    for name, digest in prior_receipt['files'].items():
        if name.endswith('.bin'):
            assert sha(output / name) == digest, name
    write(output.parent / 'build_receipt.json', dict(
        status='PASS_VIEWER_DATA_AND_NATIVE_GEOMETRY', task_id=cfg['task_id'], scientific_verdict=None,
        parent_build_receipt_sha256=sha(parent / 'build_receipt.json'),
        geometry_validation='Inherited 80 native-distance checks; exact geometry bytes and metric cohorts verified unchanged',
        geometry_replay_checks=prior_receipt['geometry_replay_checks'], case_count=20, priority_count=6,
        photo_projection_checks=checks, source_bindings=bindings, config_sha256=sha(config), script_sha256=sha(__file__),
        training_changes=False, elapsed_seconds=time.time()-started,
        files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for arg in ['config','art','output','repository']:
        parser.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.art, args.output, args.repository)
