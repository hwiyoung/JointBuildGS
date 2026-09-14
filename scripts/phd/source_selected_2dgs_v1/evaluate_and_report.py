"""Sealed-result comparisons and mobile evidence for source-selected 2DGS.

This program reads UAS only after all requested training receipts are verified.
Reference cohorts depend on fixed source masks/cameras and original UAS IDs,
never on a rendered result. Metrics are descriptive technical diagnostics.
"""
import argparse
import hashlib
import json
import math
import platform
import shutil
import textwrap
import time
from pathlib import Path
from scipy.spatial import cKDTree

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


ARMS = ('prior_only', 'source_selected')
DOMAINS = ('target', 'surrounding', 'outside')
REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81',
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): h.update(block)
    return h.hexdigest()


def clean(v):
    if isinstance(v, dict): return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [clean(x) for x in v]
    if isinstance(v, np.ndarray): return clean(v.tolist())
    if isinstance(v, (np.bool_,)): return bool(v)
    if isinstance(v, np.integer): return int(v)
    if isinstance(v, (float, np.floating)): return float(v) if np.isfinite(v) else None
    if isinstance(v, Path): return str(v)
    return v


def read(path): return json.loads(Path(path).read_text())
def write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x') as stream:
        json.dump(clean(data), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def load_npz(path):
    with np.load(path, allow_pickle=False) as f: return {k: f[k] for k in f.files}


def stats(values):
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    if not len(x): return dict(count=0, mean=None, median=None, p95=None, maximum=None, rmse=None)
    return clean(dict(count=len(x), mean=x.mean(), median=np.median(x), p95=np.quantile(x, .95),
                      maximum=x.max(), rmse=np.sqrt(np.mean(x*x))))


def domains(masks):
    target = np.asarray(masks['target_mask'], dtype=bool)
    surrounding = np.asarray(masks['surrounding_mask'], dtype=bool)
    outside = np.asarray(masks.get('outside_mask', ~(target | surrounding)), dtype=bool)
    if target.ndim != 2 or surrounding.shape != target.shape or outside.shape != target.shape:
        raise ValueError('Fixed masks must have identical HxW dimensions')
    if np.any(target & surrounding) or np.any(target & outside) or np.any(surrounding & outside):
        raise ValueError('Fixed domains overlap')
    if 'photo_mask' in masks and not np.array_equal(target | surrounding | outside, masks['photo_mask'].astype(bool)):
        raise ValueError('Fixed domains must partition the declared regional photo mask')
    return dict(target=target, surrounding=surrounding, outside=outside)


def valid_depth(arrays, threshold=.5):
    d, a = np.asarray(arrays['depth']), np.asarray(arrays['alpha'])
    return np.isfinite(d) & (d > 0) & np.isfinite(a) & (a >= threshold)


def angle_degrees(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    na, nb = np.linalg.norm(a, axis=-1), np.linalg.norm(b, axis=-1)
    valid = np.isfinite(a).all(-1) & np.isfinite(b).all(-1) & (na > 1e-8) & (nb > 1e-8)
    dots = np.sum(a*b, axis=-1) / np.maximum(na*nb, 1e-12)
    return np.where(valid, np.degrees(np.arccos(np.clip(np.abs(dots), 0, 1))), np.nan)


def compare_renders(before, after, photo, masks):
    """Photo metrics use every fixed pixel; geometry uses paired valid coverage."""
    photo = np.asarray(photo, np.float64)
    if photo.ndim != 3 or photo.shape[-1] != 3 or not np.isfinite(photo).all():
        raise ValueError('Finite HxWx3 source RGB required')
    if photo.min() < 0 or photo.max() > 1: raise ValueError('RGB must use [0,1]')
    ds = domains(masks)
    for arrays in (before, after):
        if np.asarray(arrays['rgb']).shape != photo.shape: raise ValueError('RGB shape differs')
        if not np.isfinite(arrays['rgb']).all(): raise ValueError('Nonfinite rendered RGB')
        for k in ('depth', 'alpha'):
            if np.asarray(arrays[k]).shape != photo.shape[:2]: raise ValueError(k+' shape differs')
    e0 = np.mean(np.abs(np.asarray(before['rgb'])-photo), axis=-1)
    e1 = np.mean(np.abs(np.asarray(after['rgb'])-photo), axis=-1)
    v0, v1 = valid_depth(before), valid_depth(after)
    da = np.asarray(after['alpha'])-np.asarray(before['alpha'])
    dz = np.asarray(after['depth'])-np.asarray(before['depth'])
    normal = angle_degrees(before['normal'], after['normal'])
    result = {}
    for label, mask in ds.items():
        n, paired = int(mask.sum()), mask & v0 & v1
        row = dict(fixed_pixels=n, paired_depth_pixels=int(paired.sum()),
                   valid_before_pixels=int((mask & v0).sum()), valid_after_pixels=int((mask & v1).sum()),
                   coverage_lost_pixels=int((mask & v0 & ~v1).sum()), coverage_gained_pixels=int((mask & ~v0 & v1).sum()),
                   alpha_change=stats(da[mask]), depth_signed_change_m=stats(dz[paired]),
                   depth_absolute_change_m=stats(np.abs(dz[paired])), unoriented_normal_change_degrees=stats(normal[paired]))
        for prefix, arr, err in [('before', before, e0), ('after', after, e1)]:
            mse = np.mean((np.asarray(arr['rgb'])[mask]-photo[mask])**2) if n else None
            row['photo_mae_'+prefix] = float(err[mask].mean()) if n else None
            row['photo_rmse_'+prefix] = float(np.sqrt(mse)) if n else None
            # Perfect equality is explicit rather than serializing Infinity as 0.
            row['photo_psnr_'+prefix] = float(-10*np.log10(mse)) if mse is not None and mse > 0 else None
            row['photo_exact_'+prefix] = bool(mse == 0) if n else None
        row['photo_mae_delta'] = float((e1-e0)[mask].mean()) if n else None
        row['photo_improved_pixels_gt_1over255'] = int((mask & (e1-e0 < -1/255)).sum())
        row['photo_damaged_pixels_gt_1over255'] = int((mask & (e1-e0 > 1/255)).sum())
        result[label] = row
    return clean(result)


def compare_parameters(before, after):
    """Only equal stable IDs are compared as point-wise parameter changes."""
    ids0, ids1 = before['stable_source_id'], after['stable_source_id']
    if len(np.unique(ids0)) != len(ids0) or len(np.unique(ids1)) != len(ids1): raise ValueError('Duplicate stable source ID')
    if not np.array_equal(ids0, ids1): raise ValueError('Training changed ordered source IDs')
    fixed = ~before['trainable_geometry'].astype(bool)
    if not np.array_equal(fixed, ~after['trainable_geometry'].astype(bool)): raise ValueError('Geometry mask changed')
    delta = np.linalg.norm(after['xyz'].astype(float)-before['xyz'].astype(float), axis=1)
    row = dict(total_gaussians=len(ids0), trainable_geometry=int((~fixed).sum()), frozen_geometry=int(fixed.sum()),
               moved_gaussians=int((delta > 0).sum()), xyz_displacement_m=stats(delta),
               trained_xyz_displacement_m=stats(delta[~fixed]), frozen_xyz_displacement_m=stats(delta[fixed]),
               normal_change_degrees=stats(angle_degrees(before['normal'], after['normal'])),
               trained_normal_change_degrees=stats(angle_degrees(before['normal'][~fixed],after['normal'][~fixed])),
               scale_absolute_change_m=stats(np.abs(after['scale_xy']-before['scale_xy']).ravel()),
               opacity_absolute_change=stats(np.abs(after['opacity']-before['opacity']).ravel()),
               rgb_absolute_change=stats(np.abs(after['rgb']-before['rgb']).ravel()),
               frozen_exact={k: bool(np.array_equal(before[k][fixed], after[k][fixed]))
                             for k in ('xyz', 'normal', 'quat_wxyz', 'scale_xy', 'opacity')},
               stable_ids_exact=True)
    row['frozen_geometry_exact'] = all(row['frozen_exact'].values())
    return clean(row), dict(stable_source_id=ids0, trainable_geometry=~fixed, xyz_before=before['xyz'],
                           xyz_after=after['xyz'], displacement_m=delta,
                           normal_change_degrees=angle_degrees(before['normal'], after['normal']))


def front_return_cohort(points, camera, masks):
    """Freeze original IDs of measured frontmost returns per fixed image pixel."""
    ds = domains(masks); h, w = ds['target'].shape
    r, t, k = [np.asarray(camera[x], np.float64) for x in ('R', 't', 'K')]
    accum = []
    for start in range(0, len(points), 250000):
        xyz = np.asarray(points[start:start+250000], np.float64)
        cam = xyz@r.T+t
        local = np.flatnonzero(np.isfinite(cam).all(1) & (cam[:, 2] > 0))
        cam = cam[local]; p = cam@k.T; uv = p[:, :2]/p[:, 2:3]
        keep = (uv[:, 0] >= -.5) & (uv[:, 0] < w-.5) & (uv[:, 1] >= -.5) & (uv[:, 1] < h-.5)
        ij = np.floor(uv[keep]+.5).astype(np.int64)
        union = ds['target'] | ds['surrounding'] | ds['outside']
        inside = union[ij[:, 1], ij[:, 0]]
        accum.append(((start+local[keep])[inside], uv[keep][inside], cam[keep, 2][inside], (ij[:, 1]*w+ij[:, 0])[inside]))
    if accum:
        ids, uv, z, pix = [np.concatenate([x[j] for x in accum]) for j in range(4)]
    else:
        ids, uv, z, pix = np.empty(0, np.int64), np.empty((0, 2)), np.empty(0), np.empty(0, np.int64)
    order = np.lexsort((ids, z, pix)); ps = pix[order]
    first = np.r_[True, ps[1:] != ps[:-1]] if len(order) else np.empty(0, bool)
    choose = order[first]; ij = np.column_stack((pix[choose] % w, pix[choose]//w)).astype(np.int64)
    code = np.full(len(ij), 3, dtype=np.int8)
    for n, label in [(1, 'target'), (2, 'surrounding')]: code[ds[label][ij[:, 1], ij[:, 0]]] = n
    return dict(reference_original_indices=ids[choose], reference_points=np.asarray(points)[ids[choose]],
                reference_projected_uv=uv[choose], reference_camera_z=z[choose], reference_pixel_xy=ij, domain_code=code,
                projected_returns_in_frame=np.array(len(ids)), excluded_rear_or_duplicate_returns=np.array(len(ids)-len(choose)),
                projection_rounding_error_px=np.linalg.norm(uv[choose]-ij, axis=1))


def score_reference(cohort, camera, before, after):
    """Paired same-return diagnostics; missing coverage never counts as success."""
    ij = cohort['reference_pixel_xy']; x, y = ij[:, 0], ij[:, 1]
    ray = np.column_stack((ij, np.ones(len(ij))))@np.linalg.inv(camera['K']).T
    r, t = np.asarray(camera['R']), np.asarray(camera['t'])
    raw = {'reference_original_indices': cohort['reference_original_indices'], 'domain_code': cohort['domain_code']}
    for label, arr in [('before', before), ('after', after)]:
        d, a = arr['depth'][y, x].astype(float), arr['alpha'][y, x].astype(float)
        valid = np.isfinite(d) & (d > 0) & np.isfinite(a) & (a >= .5)
        xyz = (ray*d[:, None]-t)@r
        signed = np.where(valid, d-cohort['reference_camera_z'], np.nan)
        raw.update({label+'_valid': valid, label+'_signed_camera_z_error_m': signed,
                    label+'_absolute_camera_z_error_m': np.abs(signed),
                    label+'_same_return_distance_m': np.where(valid, np.linalg.norm(xyz-cohort['reference_points'], axis=1), np.nan)})
    paired = raw['before_valid'] & raw['after_valid']; raw['paired_valid'] = paired
    change = raw['after_absolute_camera_z_error_m']-raw['before_absolute_camera_z_error_m']
    raw['paired_absolute_error_delta_m'] = change
    summary = {}
    for code, label in enumerate(DOMAINS, 1):
        members = cohort['domain_code'] == code; p = members & paired
        n = int(members.sum()); b, a = members & raw['before_valid'], members & raw['after_valid']
        row = dict(status='PAIRED_REFERENCE_RETURN_DIAGNOSTIC' if n else 'NOT_ASSESSED_REFERENCE_ABSENT',
                   fixed_reference_count=n, paired_valid=int(p.sum()), before_valid=int(b.sum()), after_valid=int(a.sum()),
                   coverage_lost=int((b & ~raw['after_valid']).sum()), coverage_gained=int((a & ~raw['before_valid']).sum()),
                   missing_both=int((members & ~raw['before_valid'] & ~raw['after_valid']).sum()),
                   coverage_before=float(b.sum()/n) if n else None, coverage_after=float(a.sum()/n) if n else None,
                   projection_rounding_error_px=stats(cohort['projection_rounding_error_px'][members]),
                   paired_absolute_error_delta_m=stats(change[p]),
                   transitions=[dict(threshold_m=tau, improved=int((change[p] < -tau).sum()), damaged=int((change[p] > tau).sum()),
                                     within_threshold=int((np.abs(change[p]) <= tau).sum())) for tau in (.01, .05)])
        for moment in ('before', 'after'):
            for metric in ('absolute_camera_z_error_m', 'signed_camera_z_error_m', 'same_return_distance_m'):
                row['paired_'+moment+'_'+metric] = stats(raw[moment+'_'+metric][p])
        summary[label] = row
    return raw, clean(summary)


def self_test():
    """Meaningful invariant checks runnable in the existing CPU container."""
    h, w = 4, 5
    masks = dict(target_mask=np.zeros((h, w), bool), surrounding_mask=np.zeros((h, w), bool))
    masks['target_mask'][1, 2] = True; masks['surrounding_mask'][1, 3] = True
    a = dict(rgb=np.full((h, w, 3), .5), depth=np.full((h, w), 3.), alpha=np.ones((h, w)), normal=np.tile([0., 0., 1.], (h, w, 1)))
    b = {k: v.copy() for k, v in a.items()}; b['rgb'][1, 2] = .7; b['alpha'][1, 3] = 0
    out = compare_renders(a, b, np.full((h, w, 3), .6), masks)
    assert out['surrounding']['coverage_lost_pixels'] == 1 and out['surrounding']['paired_depth_pixels'] == 0
    assert out['surrounding']['depth_absolute_change_m']['mean'] is None
    assert out['outside']['photo_mae_delta'] == 0
    assert len(domains(masks)) == 3
    camera = dict(R=np.eye(3), t=np.zeros(3), K=np.eye(3))
    points = np.array([[6., 3., 3.], [8., 4., 4.], [9., 3., 3.]])
    cohort = front_return_cohort(points, camera, masks)
    assert cohort['reference_original_indices'].tolist() == [0, 2]
    assert int(cohort['excluded_rear_or_duplicate_returns']) == 1
    raw, ref = score_reference(cohort, camera, a, b)
    assert ref['surrounding']['coverage_lost'] == 1 and ref['target']['paired_before_absolute_camera_z_error_m']['mean'] == 0
    assert not ref['outside']['fixed_reference_count'] and ref['outside']['paired_absolute_error_delta_m']['mean'] is None
    assert angle_degrees(np.array([[0,0,1]]), np.array([[0,0,-1]])).item() == 0
    p=dict(stable_source_id=np.array([1,2]),trainable_geometry=np.array([True,False]),xyz=np.zeros((2,3)),
           normal=np.array([[0.,0.,1.],[0.,0.,1.]]),quat_wxyz=np.tile([1.,0.,0.,0.],(2,1)),
           scale_xy=np.ones((2,2)),opacity=np.ones(2),rgb=np.zeros((2,3)))
    q={k:v.copy() for k,v in p.items()};q['xyz'][0,0]=.1;q['rgb'][1]=.3
    param,_=compare_parameters(p,q)
    assert param['moved_gaussians']==1 and param['frozen_geometry_exact'] and param['trained_normal_change_degrees']['count']==1
    empty=front_return_cohort(np.empty((0,3)),camera,masks)
    assert len(empty['reference_original_indices'])==0
    print(json.dumps(dict(status='PASS_REPORT_INVARIANTS', checks=['paired coverage loss', 'empty metric null', 'fixed mask partition', 'frontmost original ID', 'same cohort before and after', 'unoriented normals', 'actual center changes with frozen geometry and learned appearance', 'empty reference cohort'])))


STAGES = [
    ('원영상·Prior/MVS 깊이', '같은 원영상 좌표에서 두 원자료의 깊이를 비교합니다. 깊이 결손을 채우지 않습니다.', '01_inputs.png'),
    ('불일치 후보', '깊이 차이는 수정 후보입니다. 현재 영상의 기하가 더 정확하다는 판정은 아닙니다.', '02_conflict.png'),
    ('가시성·다중 시점·모호성', '이전 실험에서 같은 이웃 관측을 묶어 검증한 결과를 사용합니다. 낮은 비용 구간 폭 0은 한 깊이 격자점만 포함될 수 있다는 뜻이며 불확실성 0이 아닙니다. 원 관측 기록의 격자 간격을 함께 확인합니다. 후보 선택에 현재 UAS를 사용하지 않습니다.', '03_evidence.png'),
    ('고정 소스 판정·유보 영역', '이전 관측 판정에서 채택된 원래 7×7 영역만 MVS 소스로 선택합니다. 다른 시점에 투영된 지지는 새 선택 권한이 아닙니다. 학습 중 판정은 바뀌지 않습니다.', '04_masks.png'),
    ('직접 소스 결합·새 2D Gaussian', 'Prior 유지 대조와 선택한 Prior/MVS 조립을 구분합니다. 기존 GeoGS Gaussian ID를 수정하는 실험이 아니며 두 조립에서 새 gsplat 2DGS를 초기화합니다.', '05_assembly.png'),
    ('2DGS 최적화 과정', '동일한 설정과 카메라 순서로 0/50/200/500/2000 iteration을 비교합니다. 선택 영역 밖의 형상 파라미터는 고정하고 RGB 외관은 학습합니다.', None),
    ('형상·영상의 전후 변화', '소스 선택 효과(두 arm의 iteration 0)와 GS 최적화 효과(각 arm의 0→2000)를 따로 비교합니다. 모든 영상 측정 창은 사전에 고정됩니다.', None),
    ('주변 손상·독립 UAS 진단', '완료된 학습 결과를 고정한 후 같은 원본 UAS ID로 전후를 평가합니다. 주변 렌더링 변화와 형상 파라미터 보존은 별도 결과입니다. 결손·피복 손실을 함께 표시합니다.', None),
]


def relative(path, output):
    import os
    return os.path.relpath(path, output)


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def metric(label, value, unit=''): return dict(label=label, value=clean(value), unit=unit)


def find_prepared(args):
    if args.prepared: return args.prepared
    candidates = [args.attempt/'prepared', args.attempt/'prepare', args.attempt/'inputs']
    found = [p for p in candidates if (p/'P1/manifest.json').exists()]
    if len(found) != 1: raise ValueError('Supply --prepared: expected exactly one prepared regional manifest directory')
    return found[0]


def verify_file(path, digest):
    if not path.is_file() or sha(path) != digest: raise ValueError('Artifact integrity mismatch: '+str(path))


def verify_training(prepared, training, regions, config, config_path):
    """Verify all seals before reference data can be opened by caller."""
    receipts = {}; final = int(config['training']['iterations'])
    for rid in regions:
        manifest_path = prepared/rid/'manifest.json'; manifest = read(manifest_path)
        for arm in ARMS:
            folder = training/rid/arm; receipt_path = folder/'receipt.json'; receipt = read(receipt_path)
            if receipt.get('status') != 'PASS_SOURCE_SELECTED_2DGS_TRAIN' or receipt.get('scientific_verdict', 'missing') is not None:
                raise ValueError('Completed null-verdict training seal required: '+str(receipt_path))
            if receipt['region'] != rid or receipt['arm'] != arm or int(receipt['iterations']) != final:
                raise ValueError('Training identity or completion differs: '+str(receipt_path))
            if receipt['manifest_sha256'] != sha(manifest_path) or receipt['config_sha256'] != sha(config_path):
                raise ValueError('Frozen training inputs changed: '+str(receipt_path))
            for rel, digest in receipt['outputs'].items(): verify_file(folder/rel, digest)
            for step in config['training']['checkpoints']:
                cp = f'checkpoint_{int(step):06d}.npz'
                if cp not in receipt['outputs']: raise ValueError('Unsealed checkpoint: '+cp)
                for view in manifest['views']:
                    rel = f'renders/iteration_{int(step):06d}/{view["id"]}/raw.npz'
                    if rel not in receipt['outputs']: raise ValueError('Unsealed render: '+rel)
            receipts[(rid, arm)] = dict(receipt=receipt, path=receipt_path, sha256=sha(receipt_path))
    return receipts


def verify_prepared(prepared, regions):
    seal=read(prepared/'receipt.json')
    if seal.get('status')!='PASS_PREPARED_SOURCES' or seal.get('scientific_verdict','missing') is not None:
        raise ValueError('Completed null-verdict source preparation receipt required')
    for item in seal['outputs']: verify_file(prepared/item['path'],item['sha256'])
    result = {}
    for rid in regions:
        folder = prepared/rid; manifest = read(folder/'manifest.json')
        for arm in ARMS: verify_file(folder/manifest['arms'][arm], manifest['arm_sha256'][arm])
        for view in manifest['views']: verify_file(folder/view['arrays_path'], view['arrays_sha256'])
        result[rid] = manifest
    return result


def stage_document(args, prepared, manifests, state='PENDING_TRAINING'):
    report = dict(schema='jbgs.source_selected_2dgs.report.v1', task_id='PHD-SOURCE-SELECTED-2DGS-v1',
                  status=state, scientific_verdict=None, generated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  summary='이전 실험의 소스 판정 → 직접 소스 조립 → 제한된 2DGS 최적화 → 형상·영상·주변 손상 비교',
                  limitations=['P1은 이전 관측 판정 통과 표본이 없어 소스 교체와 형상 갱신의 유보 대조입니다.',
                               'P2의 11개, P3의 2개는 관측 표본 수이며 건물 수·고유 표면 수·변화 면적이 아닙니다.',
                               '2000-step 제한된 기술 비교이며, 일반적인 2DGS 수렴이나 전체 건물 변화 대응의 성공을 뜻하지 않습니다.',
                               '깊이는 alpha 가중 Gaussian 중심 camera-Z입니다. 표면 광선 교차 깊이나 독립 기하 정확도와 다릅니다.',
                               '현재 RGB/MVS 생성 계보를 공유한 개발 관측입니다. 독립 held-out 성능으로 해석하지 않습니다.',
                               'UAS는 평가 전용입니다. 점 결손·전면점 가림·픽셀 반올림 및 상속된 수직 기준/좌표계 한계가 남습니다.'],
                  regions=[], links=[])
    for rid, manifest in manifests.items():
        row = dict(id=rid, status=state, stages=[], metrics=[], links=[])
        for index, (title, description, filename) in enumerate(STAGES, 1):
            img = prepared/rid/filename if filename else None
            images = [dict(src=relative(img, args.output), label=title)] if img is not None and img.exists() else []
            row['stages'].append(dict(number=index, title=title, description=description, images=images,
                                      status='PREPARED' if images else 'PENDING', metrics=[], links=[]))
        row['links'].append(dict(label='고정 소스·카메라 입력', href=relative(prepared/rid/'manifest.json', args.output)))
        if manifest.get('observations_path'):
            row['stages'][2]['links']=[dict(label='이웃별 근거·깊이 비용곡선 통계·격자 간격',href=relative(prepared/rid/manifest['observations_path'],args.output))]
        counts=manifest.get('counts',{})
        if counts.get('frozen_admitted_patches')==0:
            row['stages'][3]['description']+=' 이 지역은 판정 통과 영역이 없습니다. 그림의 빈 확대 창은 해당 시점에 지정된 예시 패치가 없다는 뜻이며 원 관측자료의 부재를 뜻하지 않습니다.'
        row['stages'][3]['metrics']=[metric('이전 관측 판정 통과 패치',counts.get('frozen_admitted_patches')),
                                   metric('결박 카메라',len(manifest['views']))]
        row['stages'][4]['metrics']=[metric('Prior 대조 원표본',counts.get('prior_points')),metric('선택 조립 원표본',counts.get('selected_points')),
              metric('제거된 Prior 표본',counts.get('removed_prior_points')),metric('추가된 MVS 표본',counts.get('added_mvs_points'))]
        report['regions'].append(row)
    return report


def publish_document(args, document):
    args.output.mkdir(parents=True, exist_ok=True)
    viewer = Path(__file__).resolve().parents[3]/'src/apps/source_selected_2dgs_v1/index.html'
    shutil.copyfile(viewer, args.output/'index.html')
    atomic_json(args.output/'data.json', document)


def compare_assemblies(first, second):
    common, i0, i1 = np.intersect1d(first['stable_source_id'], second['stable_source_id'], return_indices=True)
    fields = ('xyz', 'normal', 'scale', 'source_kind', 'rgb')
    row = dict(prior_only_points=len(first['xyz']), source_selected_points=len(second['xyz']),
               common_original_ids=len(common), removed_prior_ids=len(first['xyz'])-len(common),
               inserted_source_ids=len(second['xyz'])-len(common),
               unchanged_common_fields={k: bool(np.array_equal(first[k][i0], second[k][i1])) for k in fields},
               prior_only_trainable_geometry=int(first['trainable_geometry'].sum()),
               source_selected_trainable_geometry=int(second['trainable_geometry'].sum()),
               point_count_control='Actual point count differs when replacement yields a different number of valid raw samples; counts are reported, not resampled to hide this.')
    row['preserved_context_exact'] = all(row['unchanged_common_fields'].values())
    return row


def raw_render(training, rid, arm, step, view_id):
    return load_npz(training/rid/arm/f'renders/iteration_{int(step):06d}'/view_id/'raw.npz')


def assert_fixed(raw, prepared_arrays, camera):
    expected = (int(camera['height']), int(camera['width']))
    if raw['depth'].shape != expected: raise ValueError('Rendered camera dimensions differ from fixed input')
    for key in ('photo_mask', 'target_mask', 'surrounding_mask', 'outside_mask'):
        if not np.array_equal(raw[key], prepared_arrays[key]): raise ValueError('Rendered fixed mask changed: '+key)
    domains(raw)


def assembly_reference(cohort, source0, source1):
    """Nearest source-sample distances on fixed UAS IDs; density dependent."""
    refs = cohort['reference_points']; distances = []
    for source in (source0, source1):
        xyz = source['xyz']; valid = np.isfinite(xyz).all(1)
        distances.append(cKDTree(xyz[valid]).query(refs, workers=1)[0] if valid.any() and len(refs) else np.full(len(refs), np.nan))
    row = dict(role='DIRECT_ASSEMBLY_POINT_SAMPLE_DIAGNOSTIC', caveat='Nearest source-point distance depends on sample density; not surface accuracy or a matched source correspondence.', domains={})
    for code, label in enumerate(DOMAINS, 1):
        m = cohort['domain_code'] == code; delta = distances[1][m]-distances[0][m]
        row['domains'][label] = dict(fixed_reference_count=int(m.sum()), prior_only_distance_m=stats(distances[0][m]),
                                    source_selected_distance_m=stats(distances[1][m]), difference_m=stats(delta),
                                    improved_gt_1cm=int((delta < -.01).sum()), damaged_gt_1cm=int((delta > .01).sum()))
    return row, dict(reference_original_indices=cohort['reference_original_indices'], domain_code=cohort['domain_code'],
                    prior_only_nearest_sample_distance_m=distances[0], source_selected_nearest_sample_distance_m=distances[1])


def fixed_crop(arrays, padding=32):
    mask = arrays['target_mask'] if arrays['target_mask'].any() else arrays['photo_mask']
    y, x = np.where(mask); h, w = mask.shape
    if not len(x): return (0, 0, w, h)
    x0, x1 = max(0, int(x.min())-padding), min(w, int(x.max())+padding+1)
    y0, y1 = max(0, int(y.min())-padding), min(h, int(y.max())+padding+1)
    return x0, y0, x1, y1


def crop_array(arr, bbox):
    x0, y0, x1, y1 = bbox
    return np.asarray(arr)[y0:y1, x0:x1]


def contour_domains(ax, arrays, bbox):
    for name, color in [('target_mask', '#26ff38'), ('surrounding_mask', '#ffd326')]:
        mask = crop_array(arrays[name], bbox)
        if mask.any() and not mask.all(): ax.contour(mask.astype(float), levels=[.5], colors=[color], linewidths=.7)


def save_figure(fig, path):
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def plot_stage6(folder, training, rid, view, steps, rows):
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    colors = dict(prior_only='#3265b0', source_selected='#ca6b15')
    for arm in ARMS:
        for domain, ax in zip(DOMAINS, axes):
            vals = []
            for step in steps:
                selected = [r['render'][domain] for r in rows if r['comparison'] == arm+'_optimization' and r['iteration'] == step]
                n = sum(x['fixed_pixels'] for x in selected)
                vals.append(sum(x['photo_mae_after']*x['fixed_pixels'] for x in selected if x['fixed_pixels'])/n if n else np.nan)
            ax.plot(steps, vals, 'o-', color=colors[arm], label=arm)
            ax.set(xlabel='iteration', ylabel='RGB MAE [0,1]', title=domain+' - all fixed view pixels')
            ax.legend(fontsize=8)
    for ax in axes:
        if not any(np.isfinite(line.get_ydata()).any() for line in ax.lines):
            ax.text(.5,.5,'NO FIXED PIXELS\nNOT ASSESSED',ha='center',va='center',transform=ax.transAxes,color='#805500')
    fig.suptitle('Fixed-denominator reconstruction fit; training views, not held-out accuracy')
    save_figure(fig, folder/'06_checkpoint_fit.png')
    fig, axes = plt.subplots(2, len(steps), figsize=(15, 6))
    for i, arm in enumerate(ARMS):
        for j, step in enumerate(steps):
            raw = raw_render(training, rid, arm, step, view['id']); box = fixed_crop(raw)
            axes[i, j].imshow(np.clip(crop_array(raw['rgb'], box), 0, 1)); contour_domains(axes[i, j], raw, box)
            axes[i, j].set_title(f'{arm}\niteration {step}', fontsize=9); axes[i, j].axis('off')
    fig.suptitle('Same source-fixed crop at every checkpoint; green target / yellow surrounding')
    save_figure(fig, folder/'06_snapshots.png')
    histories = {}
    for arm in ARMS:
        for name in ('loss_trace.jsonl', 'loss_history.jsonl', 'losses.jsonl', 'training.jsonl'):
            path = training/rid/arm/name
            if path.exists(): histories[arm] = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]; break
    if histories:
        fig, axes = plt.subplots(2, 3, figsize=(13, 6))
        keys = ['total', 'photo_l1', 'source_depth_huber', 'source_normal', 'normal', 'distortion']
        for ax, key in zip(axes.flat, keys):
            for arm, history in histories.items():
                points = []
                for r in history:
                    losses = r.get('terms', r.get('losses', r.get('loss', r)))
                    value = losses.get(key) if isinstance(losses, dict) else None
                    step = r.get('iteration', r.get('step'))
                    if step is not None and isinstance(value, (int, float)): points.append((step, value))
                if points:
                    x, y = zip(*points); ax.plot(x, y, label=arm, color=colors[arm], linewidth=.7)
            ax.set(title=key, xlabel='iteration'); ax.legend(fontsize=7) if ax.lines else ax.text(.5, .5, 'NOT RECORDED', ha='center', transform=ax.transAxes)
        fig.suptitle('Recorded training-view losses; not validation metrics')
        save_figure(fig, folder/'06_losses.png')
        fig,axes=plt.subplots(1,2,figsize=(12,4))
        for ax,key in zip(axes,['candidate_depth_mae_m','context_depth_mae_m']):
            count_key='candidate_depth_pixels' if key.startswith('candidate') else 'context_depth_pixels'
            for arm,history in histories.items():
                points=[(r['iteration'],r.get('terms',{}).get(key)) for r in history
                        if isinstance(r.get('terms',{}).get(key),(int,float)) and r.get('counts',{}).get(count_key,0)>0]
                if points:
                    x,y=zip(*points);ax.plot(x,y,label=arm,color=colors[arm],linewidth=.7)
            ax.set(title=key,xlabel='iteration',ylabel='Raw source camera-Z MAE (m)')
            if ax.lines:ax.legend(fontsize=8)
            else:ax.text(.5,.5,'NOT RECORDED',ha='center',transform=ax.transAxes)
        fig.suptitle('Sampled training view source fit; empty source domains omitted, not zero-filled')
        save_figure(fig,folder/'06_source_fit.png')


def plot_stage7(folder, raw00, raw01, raw10, raw11):
    box = fixed_crop(raw00)
    photo = raw00['photo']; target = raw00
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    for ax, arr, title in zip(axes[0], [photo, raw01['rgb'], raw11['rgb']], ['Current photo', 'Prior-only final', 'Source-selected final']):
        ax.imshow(np.clip(crop_array(arr, box), 0, 1)); contour_domains(ax, target, box); ax.set_title(title); ax.axis('off')
    comparisons = [(raw00, raw10, 'Source assembly: selected 0 - prior 0'), (raw10, raw11, 'Selected optimization: final - 0'), (raw01, raw11, 'Matched finals: selected - prior')]
    photodeltas = [np.mean(np.abs(b['rgb']-photo), -1)-np.mean(np.abs(a['rgb']-photo), -1) for a,b,_ in comparisons]
    limit = max(.005, max(float(np.max(np.abs(crop_array(d, box)))) for d in photodeltas))
    for ax, delta, (_, _, title) in zip(axes[1], photodeltas, comparisons):
        im=ax.imshow(crop_array(delta, box), cmap='coolwarm', vmin=-limit, vmax=limit)
        contour_domains(ax, target, box); ax.set_title(title, fontsize=9); ax.axis('off'); fig.colorbar(im, ax=ax, fraction=.035)
    fig.suptitle('RGB error difference: blue improves / red worsens; common unclipped scale')
    save_figure(fig, folder/'07_rgb_comparison.png')
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    positive = np.concatenate([crop_array(x['depth'], box)[crop_array(valid_depth(x), box)] for x in [raw00, raw10, raw11]])
    low, high = (float(positive.min()), float(positive.max())) if len(positive) else (0., 1.)
    if high <= low: high = low+1e-6
    for ax, raw, title in zip(axes[0], [raw00, raw10, raw11], ['Prior-only iteration 0', 'Selected iteration 0', 'Selected final']):
        depth = np.where(valid_depth(raw), raw['depth'], np.nan)
        im = ax.imshow(crop_array(depth, box), cmap='viridis', vmin=low, vmax=high)
        contour_domains(ax, target, box); ax.set_title(title); ax.axis('off'); fig.colorbar(im, ax=ax, fraction=.035)
    deltas = [np.where(valid_depth(a)&valid_depth(b), b['depth']-a['depth'], np.nan) for a,b,_ in comparisons]
    finite = np.concatenate([crop_array(d, box)[np.isfinite(crop_array(d, box))] for d in deltas])
    limit = max(.001, float(np.max(np.abs(finite)))) if len(finite) else .001
    for ax, delta, (_, _, title) in zip(axes[1], deltas, comparisons):
        im=ax.imshow(crop_array(delta, box), cmap='coolwarm', vmin=-limit, vmax=limit)
        contour_domains(ax, target, box); ax.set_title(title, fontsize=9); ax.axis('off'); fig.colorbar(im, ax=ax, fraction=.035)
    fig.suptitle('Alpha-weighted Gaussian-center camera-Z (m), paired alpha >= 0.5; not ray-intersection surface depth')
    save_figure(fig, folder/'07_depth_comparison.png')
    write(folder/'display_contract.json', dict(crop_xyxy=box, crop_from='prepared target union +32px; regional photo bounds for empty target',
          photo_error_delta_limit=max(.005, max(float(np.max(np.abs(crop_array(d, box)))) for d in photodeltas)),
          depth_absolute_min=low, depth_absolute_max=high, depth_delta_abs_limit=limit, values_clipped=False,
          geometry_validity='paired alpha >=0.5 and finite positive expected camera-Z'))


def plot_parameters(folder, checkpoints, parameter_rows):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    color = dict(prior_only='#3265b0', source_selected='#ca6b15')
    for arm in ARMS:
        before, after = checkpoints[arm]; free = before['trainable_geometry'].astype(bool)
        delta = np.linalg.norm(after['xyz']-before['xyz'], axis=1)
        d = np.sort(delta[free]); axes[0].plot(np.arange(len(d)), d, label=arm, color=color[arm])
        norms = np.sort(angle_degrees(before['normal'][free], after['normal'][free]))
        axes[1].plot(np.arange(len(norms)), norms, label=arm, color=color[arm])
        axes[2].bar(arm, int((delta > 0).sum()), color=color[arm])
    axes[0].set(xlabel='trainable Gaussian rank', ylabel='XYZ displacement (m)', title='Actual center changes')
    axes[1].set(xlabel='trainable Gaussian rank', ylabel='normal change (degrees)', title='Unoriented normal changes')
    axes[2].set(ylabel='Gaussian count', title='Actually moved centers')
    for ax in axes[:2]: ax.legend(fontsize=8)
    for ax in axes[:2]:
        if not any(len(line.get_ydata()) for line in ax.lines):
            ax.text(.5,.5,'NO TRAINABLE GEOMETRY',ha='center',transform=ax.transAxes,color='#805500')
    fig.suptitle('Fresh source-assembled primitives; no old Gaussian-ID association implied')
    save_figure(fig, folder/'07_parameters.png')


def plot_damage(folder, rows, views, final):
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    for j, domain in enumerate(DOMAINS):
        for comparison, color, label in [('source_selected_optimization','#ca6b15','selected 0 -> final'), ('prior_only_optimization','#3265b0','prior 0 -> final'), ('matched_finals','#00897b','prior final -> selected final')]:
            selected = [r for r in rows if r['comparison'] == comparison and r['iteration'] == final]
            byid = {r['view_id']:r for r in selected}
            y = [byid[v['id']]['render'][domain]['photo_mae_delta'] for v in views]
            axes[0,j].plot(range(len(views)), [np.nan if x is None else x for x in y], 'o-', label=label, color=color, linewidth=.8, markersize=3)
            y = [byid[v['id']]['reference'][domain]['paired_absolute_error_delta_m']['mean'] for v in views]
            axes[1,j].plot(range(len(views)), [np.nan if x is None else x for x in y], 'o-', label=label, color=color, linewidth=.8, markersize=3)
        axes[0,j].set(title=domain, ylabel='RGB MAE change', xlabel='fixed view index')
        axes[1,j].set(ylabel='Paired UAS |camera-Z error| change (m)', xlabel='fixed view index')
        for ax in axes[:,j]:
            assessed=any(np.isfinite(line.get_ydata()).any() for line in ax.lines)
            if assessed: ax.axhline(0,color='black',linewidth=.5)
            else: ax.text(.5,.5,'NO PAIRED ASSESSMENT',ha='center',transform=ax.transAxes,color='#805500')
            ax.legend(fontsize=6)
    fig.suptitle('Every fixed view: negative improves / positive worsens; empty cohorts omitted, raw coverage reported')
    save_figure(fig, folder/'08_damage_all_views.png')


def format_number(value, digits=5):
    if value is None: return '미산출'
    if isinstance(value, bool): return '확인' if value else '불일치'
    if isinstance(value, int): return str(value)
    if isinstance(value, float): return f'{value:.{digits}f}'
    return str(value)


def pixel_lines(text,font,width=792):
    """Wrap Korean/Latin text using actual glyph widths, including long tokens."""
    lines=[]
    for paragraph in str(text).splitlines() or ['']:
        current=''
        for character in paragraph:
            if current and font.getlength(current+character)>width:
                lines.append(current.rstrip());current=character.lstrip()
            else:current+=character
        lines.append(current.rstrip())
    return lines


def preparation_overview(args,manifests,prepared):
    """Timestamped prepared-data snapshot; creates no per-region report folder."""
    if not args.font or not args.font.exists(): return
    font=ImageFont.truetype(str(args.font),25);small=ImageFont.truetype(str(args.font),20)
    title=ImageFont.truetype(str(args.font),32);parts=[]
    for rid,manifest in manifests.items():
        counts=manifest['counts'];im=Image.open(prepared/rid/'04_masks.png').convert('RGB');im.thumbnail((390,520))
        text=[rid+' · 소스 선택 준비',f'관측 판정 통과: {counts["frozen_admitted_patches"]}개 패치',
              f'Prior 대조: {counts["prior_points"]:,}개 표본',f'선택 조립: {counts["selected_points"]:,}개 표본',
              f'Prior 제거: {counts["removed_prior_points"]:,}',f'MVS 추가: {counts["added_mvs_points"]:,}',
              '대상 형상 갱신 유보' if not counts['frozen_admitted_patches'] else '선택된 소스의 2DGS 학습 대기',
              '주황: MVS 선택', '분홍: 투영 지지·형상 감독 유보', '파랑: Prior 유지']
        lines=[line for textline in text for line in pixel_lines(textline,font if textline==text[0] else small,360)]
        parts.append((rid,im,lines,max(im.height,len(lines)*33)+30))
    head=['소스 판정 → 직접 조립 준비 완료','P1·P2·P3 · 학습 결과가 아닌 입력 단계의 기록',
          time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime()),'다음: 동일 2DGS 학습 → 전후 형상·영상·주변 손상 비교']
    headline=[line for x in head for line in pixel_lines(x,title if x==head[0] else small)]
    footerlines=pixel_lines('패치 수는 건물 수·고유 표면 수·변화 면적이 아닙니다. 최적화와 UAS 평가는 이후 별도 단계입니다.',small)
    height=24+len(headline)*42+sum(p[3]+14 for p in parts)+len(footerlines)*30+20
    canvas=Image.new('RGB',(840,height),'white');dd=ImageDraw.Draw(canvas);y=24
    for index,line in enumerate(headline):dd.text((24,y),line,font=title if index==0 else small,fill='#173b48');y+=42
    for rid,im,lines,rowheight in parts:
        dd.line((24,y,816,y),fill='#d5e2e7',width=2);y+=14
        for index,line in enumerate(lines):dd.text((24,y+index*33),line,font=font if index==0 else small,fill='#173b48')
        canvas.paste(im,(430,y));y+=rowheight
    for line in footerlines:
        dd.text((24,y),line,font=small,fill='#805500');y+=30
    if y+20>height:raise ValueError('Prepared overview exceeded calculated canvas height')
    canvas.crop((0,0,840,y+20)).save(args.output/'preparation_overview.png')


def mobile_pages(args, document):
    if not args.font or not args.font.exists(): raise ValueError('Existing Korean font required for final mobile outputs')
    font = ImageFont.truetype(str(args.font), 25); small = ImageFont.truetype(str(args.font), 20)
    titlefont = ImageFont.truetype(str(args.font), 31)
    pages, summaries = [], []
    for region in document['regions']:
        rid=region['id']; folder=args.output/rid
        for stage in region['stages']:
            # One portrait page per image avoids unreadable giant composite mosaics.
            images = stage['images'] or [None]
            for image_entry in images:
                page=Image.new('RGB',(840,1188),'white'); dd=ImageDraw.Draw(page); y=24
                dd.text((24,y),f'{rid} · {stage["number"]}단계 · {stage["title"]}',font=font,fill='#173b48'); y+=45
                for line in pixel_lines(stage['description'],small): dd.text((24,y),line,font=small,fill='#425763'); y+=31
                if image_entry:
                    im=Image.open(args.output/image_entry['src']).convert('RGB'); im.thumbnail((792, max(120, 900-y)))
                    page.paste(im,((840-im.width)//2,y)); y+=im.height+18
                for m in stage.get('metrics',[]):
                    text=f'{m["label"]}: {format_number(m["value"])} {m.get("unit", "")}'
                    wrapped=pixel_lines(text,small)
                    if y+29*len(wrapped)>1120:break
                    for line in wrapped: dd.text((24,y),line,font=small,fill='#173b48'); y+=29
                dd.text((24,1150),'기술 진단 · scientific_verdict: null · 상세 수치: summary.json',font=small,fill='#855b16')
                pages.append(page)
        metriclines=[]
        for m in region['metrics'][:13]:
            metriclines+=pixel_lines(f'{m["label"]}: {format_number(m["value"])} {m.get("unit", "")}',font)
        illustrations=[]
        for name in ['07_rgb_comparison.png','07_depth_comparison.png','08_damage_all_views.png']:
            im=Image.open(folder/name).convert('RGB'); h=round(im.height*792/im.width);illustrations.append(im.resize((792,h)))
        footers=[line for text in ['RGB 오차: 파랑 감소 / 빨강 증가. 깊이 차이의 색은 이동 방향.',
                 '소스 조립 효과와 GS 학습 효과를 분리한 제한된 기술 비교입니다.'] for line in pixel_lines(text,small)]
        height=25+52+len(metriclines)*36+sum(im.height+12 for im in illustrations)+len(footers)*30+20
        card=Image.new('RGB',(840,height),'white'); dd=ImageDraw.Draw(card); y=25
        dd.text((24,y),rid+' · 소스 선택 + 2DGS 결과',font=titlefont,fill='#173b48'); y+=52
        for line in metriclines:dd.text((24,y),line,font=font,fill='#173b48');y+=36
        for im in illustrations:card.paste(im,(24,y));y+=im.height+12
        for line in footers:
            dd.text((24,y),line,font=small,fill='#855b16'); y+=30
        if y+15>height:raise ValueError('Mobile layout exceeded calculated canvas height')
        card=card.crop((0,0,840,y+15)); card.save(folder/'mobile.png'); summaries.append(card)
        region['links'].append(dict(label=rid+' 모바일 요약 이미지',href=f'{rid}/mobile.png'))
    if pages:
        pages[0].save(args.output/'eight_stages_mobile.pdf',save_all=True,append_images=pages[1:],resolution=110.)
        summaries[0].save(args.output/'three_regions_mobile.pdf',save_all=True,append_images=summaries[1:],resolution=110.)
    document['links'] += [dict(label='P1·P2·P3 모바일 요약 PDF',href='three_regions_mobile.pdf'),
                          dict(label='전체 단계별 상세 PDF',href='eight_stages_mobile.pdf'),dict(label='모든 원수치 JSON',href='summary.json')]


def run_full(args, prepared, config, manifests, document):
    started=time.time(); steps=list(map(int,config['training']['checkpoints'])); final=int(config['training']['iterations'])
    training=args.training or args.attempt/'training'
    receipts=verify_training(prepared,training,config['regions'],config,args.config)
    # The complete seal list is durable before any reference NPZ is opened.
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'receipt.json').exists() or (args.output/'training_seals_verified.json').exists():
        raise ValueError('Final report already started; use a new --output for a retry')
    write(args.output/'training_seals_verified.json',dict(scientific_verdict=None,config_sha256=sha(args.config),
          receipts=[dict(region=rid,arm=arm,path=relative(r['path'],args.output),sha256=r['sha256']) for (rid,arm),r in receipts.items()],
          reference_opened_before_this_record=False))
    if args.reference_root is None: raise ValueError('--reference-root required for completed diagnostic')
    allresults=[]; invariant_ok=True
    for rid,manifest in manifests.items():
        print(json.dumps(dict(stage='EVALUATING',region=rid)),flush=True)
        folder=args.output/rid; folder.mkdir(exist_ok=False); reference_folder=folder/'reference'; reference_folder.mkdir()
        reference_path=args.reference_root/rid/'reference.npz'; verify_file(reference_path,REFERENCE_SHAS[rid])
        with np.load(reference_path,allow_pickle=False) as f: points=f['uas_xyz'].astype(np.float64)
        frozen=[]
        for view in manifest['views']:
            arrays=load_npz(prepared/rid/view['arrays_path'])
            cohort=front_return_cohort(points,view,arrays)
            path=reference_folder/(view['id']+'_cohort.npz'); np.savez_compressed(path,**cohort)
            frozen.append(dict(view_id=view['id'],sha256=sha(path),path=relative(path,args.output),
                               original_return_ids=len(cohort['reference_original_indices']),source_masks_sha256=view['arrays_sha256']))
        del points
        write(reference_folder/'cohorts_frozen.json',dict(region=rid,reference_sha256=REFERENCE_SHAS[rid],
              selection_uses_render_depth_or_alpha=False,scientific_verdict=None,cohorts=frozen,
              caveat='Frontmost measured return per nearest native RGB pixel. Missing UAS foreground may leave actually occluded samples.'))
        assemblies={arm:load_npz(prepared/rid/manifest['arms'][arm]) for arm in ARMS}
        assembly=compare_assemblies(assemblies['prior_only'],assemblies['source_selected']); write(folder/'assembly_comparison.json',assembly)
        checkpoints={}; params={}
        for arm in ARMS:
            first=load_npz(training/rid/arm/'checkpoint_000000.npz'); last=load_npz(training/rid/arm/f'checkpoint_{final:06d}.npz')
            if not np.array_equal(first['stable_source_id'],assemblies[arm]['stable_source_id']): raise ValueError('Initializer source IDs differ')
            if not np.array_equal(first['xyz'],assemblies[arm]['xyz']): raise ValueError('Initializer changed source centers before iteration 0')
            params[arm],parameter_arrays=compare_parameters(first,last)
            np.savez_compressed(folder/(arm+'_parameter_changes.npz'),**parameter_arrays)
            checkpoints[arm]=(first,last); invariant_ok &= params[arm]['frozen_geometry_exact']
        write(folder/'parameter_comparison.json',params)
        rows=[]; source_scores=[]
        representative=None; max_authority=-1
        for view_index,view in enumerate(manifest['views']):
            fixed=load_npz(prepared/rid/view['arrays_path']); cohort=load_npz(reference_folder/(view['id']+'_cohort.npz'))
            authority=int(fixed['authority_mask'].sum())
            if authority>max_authority: representative=view; max_authority=authority
            direct,direct_arrays=assembly_reference(cohort,assemblies['prior_only'],assemblies['source_selected'])
            direct.update(view_id=view['id'],view_index=view_index); source_scores.append(direct)
            np.savez_compressed(reference_folder/(view['id']+'_direct_assembly.npz'),**direct_arrays)
            initial={arm:raw_render(training,rid,arm,0,view['id']) for arm in ARMS}
            for arr in initial.values(): assert_fixed(arr,fixed,view)
            if not np.array_equal(initial['prior_only']['photo'],initial['source_selected']['photo']): raise ValueError('Arms use different RGB pixels')
            def compare_and_store(name,step,before,after):
                assert_fixed(after,fixed,view)
                if not np.array_equal(before['photo'],after['photo']): raise ValueError('Current RGB changed across iterations')
                metrics=compare_renders(before,after,before['photo'],fixed)
                raw,ref=score_reference(cohort,view,before,after)
                row=dict(region=rid,view_id=view['id'],view_index=view_index,image_name=view['image_name'],
                         comparison=name,iteration=step,render=metrics,reference=ref,
                         excluded_full_frame_pixels=int((~fixed['photo_mask']).sum()),
                         reference_cohort_sha256=sha(reference_folder/(view['id']+'_cohort.npz')),
                         scientific_verdict=None)
                rows.append(row)
                # Every comparison keeps same original IDs; raw per-return error deltas remain inspectable.
                np.savez_compressed(reference_folder/f'{view["id"]}_{name}_{step:06d}.npz',**raw)
            compare_and_store('source_assembly_render',0,initial['prior_only'],initial['source_selected'])
            finals={}
            for arm in ARMS:
                for step in steps:
                    current=initial[arm] if step==0 else raw_render(training,rid,arm,step,view['id'])
                    compare_and_store(arm+'_optimization',step,initial[arm],current)
                    if step==final: finals[arm]=current
            compare_and_store('matched_finals',final,finals['prior_only'],finals['source_selected'])
        write(folder/'all_views_comparisons.json',rows); write(folder/'direct_assembly_reference.json',source_scores)
        plot_stage6(folder,training,rid,representative,steps,rows)
        raw00=raw_render(training,rid,'prior_only',0,representative['id']); raw01=raw_render(training,rid,'prior_only',final,representative['id'])
        raw10=raw_render(training,rid,'source_selected',0,representative['id']); raw11=raw_render(training,rid,'source_selected',final,representative['id'])
        plot_stage7(folder,raw00,raw01,raw10,raw11); plot_parameters(folder,checkpoints,params); plot_damage(folder,rows,manifest['views'],final)
        region_doc=next(r for r in document['regions'] if r['id']==rid)
        for stage in region_doc['stages']:
            if stage['number']<=5 and not stage['images']: raise ValueError('Missing actual prepared stage figure')
            stage['status']='COMPLETE'
        region_doc.update(status='COMPLETE_TECHNICAL_DIAGNOSTIC',representative_view=representative['id'],
                          representative_rule='Most frozen independently admitted authority pixels, tie broken by manifest order. No outcome or UAS selection.')
        region_doc['stages'][4]['metrics']=[metric('Prior 대조 표본',assembly['prior_only_points']),metric('선택 조립 표본',assembly['source_selected_points']),
              metric('제거된 Prior 원본 ID',assembly['removed_prior_ids']),metric('추가된 소스 원본 ID',assembly['inserted_source_ids']),metric('공통 유지 소스 동일',assembly['preserved_context_exact'])]
        region_doc['stages'][5]['images']=[dict(src=f'{rid}/06_checkpoint_fit.png',label='모든 고정 관측 창의 checkpoint별 영상 적합도'),
              dict(src=f'{rid}/06_snapshots.png',label='같은 위치·범위의 iteration별 실제 렌더링')]
        if (folder/'06_losses.png').exists(): region_doc['stages'][5]['images'].append(dict(src=f'{rid}/06_losses.png',label='실제 학습 손실 기록; 깊이는 Huber 항'))
        if (folder/'06_source_fit.png').exists(): region_doc['stages'][5]['images'].append(dict(src=f'{rid}/06_source_fit.png',label='표본 시점의 실제 소스 깊이 MAE; 정답 정확도 아님'))
        region_doc['stages'][6]['images']=[dict(src=f'{rid}/07_rgb_comparison.png',label='소스 조립 효과·GS 학습 효과·최종 arm 차이'),
              dict(src=f'{rid}/07_depth_comparison.png',label='같은 측정 창의 깊이와 전후 차이'),dict(src=f'{rid}/07_parameters.png',label='실제로 바뀐 Gaussian 파라미터')]
        region_doc['stages'][7]['images']=[dict(src=f'{rid}/08_damage_all_views.png',label='모든 시점의 대상·주변·외부 영상 및 UAS 변화')]
        rep_rows=[r for r in rows if r['view_id']==representative['id']]
        selected=next(r for r in rep_rows if r['comparison']=='source_selected_optimization' and r['iteration']==final)
        control=next(r for r in rep_rows if r['comparison']=='prior_only_optimization' and r['iteration']==final)
        match=next(r for r in rep_rows if r['comparison']=='matched_finals')
        initial_effect=next(r for r in rep_rows if r['comparison']=='source_assembly_render')
        target=selected['render']['target']; surrounding=selected['render']['surrounding']; rt=selected['reference']['target']
        region_doc['metrics']=[metric('대표 시점의 대상 픽셀',target['fixed_pixels']),metric('새 선택 조립 Gaussian',assembly['source_selected_points']),
              metric('실제 중심 이동 Gaussian',params['source_selected']['moved_gaussians']),
              metric('대상 RGB MAE: 선택 초기',target['photo_mae_before']),metric('대상 RGB MAE: 선택 최종',target['photo_mae_after']),
              metric('대상 RGB MAE: 최종 선택−Prior',match['render']['target']['photo_mae_delta']),
              metric('주변 RGB MAE: 선택 최종−초기',surrounding['photo_mae_delta']),
              metric('주변 렌더 피복 손실',surrounding['coverage_lost_pixels'],'pixels'),
              metric('대상 UAS 전후 유효 / 고정 표본',f'{rt["paired_valid"]} / {rt["fixed_reference_count"]}'),
              metric('대상 UAS 절대 Z 오차 변화',rt['paired_absolute_error_delta_m']['mean'],'m'),
              metric('대상 UAS 최종 선택−Prior 오차',match['reference']['target']['paired_absolute_error_delta_m']['mean'],'m'),
              metric('주변 UAS 1cm 초과 손상',selected['reference']['surrounding']['transitions'][0]['damaged']),
              metric('영역 밖 형상·불투명도 동일',params['source_selected']['frozen_geometry_exact'])]
        region_doc['stages'][5]['metrics']=[metric('최종 iteration',final),metric('고정 카메라 수',len(manifest['views'])),metric('선택 조립 형상 학습 Gaussian',params['source_selected']['trainable_geometry'])]
        region_doc['stages'][6]['metrics']=[metric('대상: 소스 선택의 초기 RGB MAE 차이',initial_effect['render']['target']['photo_mae_delta']),
              metric('대상: Prior 최적화 RGB MAE 변화',control['render']['target']['photo_mae_delta']),
              metric('대상: 선택 최적화 RGB MAE 변화',target['photo_mae_delta']),
              metric('대상: 최종 선택−Prior RGB MAE 차이',match['render']['target']['photo_mae_delta']),
              metric('선택 Gaussian 최대 XYZ 이동',params['source_selected']['xyz_displacement_m']['maximum'],'m'),
              metric('수정 가능한 Gaussian 평균 법선 변화',params['source_selected']['trained_normal_change_degrees']['mean'],'°')]
        direct_rep=next(r for r in source_scores if r['view_id']==representative['id'])['domains']['target']
        stage8=[metric('직접 Prior 조립: 대상 UAS 최근접 원표본 거리',direct_rep['prior_only_distance_m']['mean'],'m'),
                metric('직접 선택 조립: 대상 UAS 최근접 원표본 거리',direct_rep['source_selected_distance_m']['mean'],'m'),
                metric('최종 선택−Prior: 대상 UAS 절대 Z 오차 차이',match['reference']['target']['paired_absolute_error_delta_m']['mean'],'m')]
        for label,k in [('대상','target'),('주변','surrounding'),('외부','outside')]:
            rd=selected['reference'][k]; md=selected['render'][k]
            stage8 += [metric(label+' 고정 픽셀',md['fixed_pixels']),metric(label+' RGB MAE 변화',md['photo_mae_delta']),
                 metric(label+' 렌더 피복 손실',md['coverage_lost_pixels'],'pixels'),metric(label+' 깊이 최대 변화',md['depth_absolute_change_m']['maximum'],'m'),
                 metric(label+' UAS 고정 원본 표본',rd['fixed_reference_count']),metric(label+' UAS 전후 유효 표본',rd['paired_valid']),
                 metric(label+' UAS 절대 Z 오차 전',rd['paired_before_absolute_camera_z_error_m']['mean'],'m'),
                 metric(label+' UAS 절대 Z 오차 후',rd['paired_after_absolute_camera_z_error_m']['mean'],'m'),
                 metric(label+' UAS 피복 손실',rd['coverage_lost'],'pixels'),
                 metric(label+' UAS 1cm 초과 개선',rd['transitions'][0]['improved']),metric(label+' UAS 1cm 초과 손상',rd['transitions'][0]['damaged'])]
        region_doc['stages'][7]['metrics']=stage8
        if params['source_selected']['moved_gaussians']==0:
            region_doc['stages'][6]['description']='이 지역은 선택 arm에서 실제 중심 이동이 0개입니다. 소스 조립·다른 파라미터·외관 변화는 별도로 확인해야 하며 형상 수정 성공으로 해석하지 않습니다. '+region_doc['stages'][6]['description']
        if not target['fixed_pixels']:
            region_doc['stages'][7]['description']='독립적으로 선택된 대상 영역이 없어 대상·주변 지표는 미산출입니다. 외부 유효 영역의 외관 학습 변화와 두 arm 동일성을 확인합니다. '+region_doc['stages'][7]['description']
        region_doc['links'] += [dict(label='전체 시점·전체 iteration 원수치',href=f'{rid}/all_views_comparisons.json'),
             dict(label='Gaussian 파라미터 전후 기록',href=f'{rid}/parameter_comparison.json'),dict(label='직접 조립 비교',href=f'{rid}/assembly_comparison.json'),
             dict(label='직접 조립의 고정 UAS 표본 진단',href=f'{rid}/direct_assembly_reference.json'),dict(label='고정 UAS 원본 ID 계보',href=f'{rid}/reference/cohorts_frozen.json')]
        for arm in ARMS: region_doc['links'].append(dict(label=arm+' 학습 완료 원본 기록',href=relative(receipts[(rid,arm)]['path'],args.output)))
        allresults.append(dict(region=rid,representative_view=representative['id'],assembly=assembly,parameters=params,
             comparisons=rows,direct_assembly_reference=source_scores,scientific_verdict=None))
        publish_document(args,document)
    write(args.output/'summary.json',dict(scientific_verdict=None,regions=allresults,config_sha256=sha(args.config),
          reference_depth_role='Same original UAS return IDs with nearest native-pixel frontmost measured returns; not a watertight surface.',
          aggregation='Every view retained separately; repeated UAS IDs across views are not independent samples.',
          geometry_change_is_accuracy=False))
    document['status']='COMPLETE_TECHNICAL_DIAGNOSTIC' if invariant_ok else 'FAIL_FROZEN_GEOMETRY_INVARIANT'
    document['generated_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    mobile_pages(args,document); publish_document(args,document)
    write(args.output/'receipt.json',dict(task_id=document['task_id'],status='PASS_REPORT_BUILD' if invariant_ok else 'FAIL_FROZEN_GEOMETRY_INVARIANT',
          scientific_verdict=None,config_sha256=sha(args.config),script_sha256=sha(__file__),font_sha256=sha(args.font),
          reference_access='Only after verifying all completed training receipts',
          elapsed_seconds=time.time()-started,python=platform.python_version(),numpy=np.__version__,
          outputs={str(p.relative_to(args.output)):sha(p) for p in sorted(args.output.rglob('*')) if p.is_file()}))
    print(json.dumps(dict(status=document['status'],output=str(args.output),scientific_verdict=None)),flush=True)
    if not invariant_ok: raise RuntimeError('Frozen geometry mismatch, comparison saved for inspection')


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Project execution requires Docker')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--attempt',type=Path); ap.add_argument('--prepared',type=Path); ap.add_argument('--training',type=Path)
    ap.add_argument('--config',type=Path); ap.add_argument('--reference-root',type=Path)
    ap.add_argument('--font',type=Path); ap.add_argument('--output',type=Path)
    ap.add_argument('--partial',action='store_true'); ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test: self_test(); return
    if args.attempt is None: ap.error('--attempt required')
    if args.output is None: args.output=args.attempt/'report'
    if args.config is None:
        candidates=[args.attempt/'frozen/config.json',args.attempt/'frozen/experiment.json',Path('/repo/configs/phd/source_selected_2dgs_v1/experiment.json')]
        args.config=next((x for x in candidates if x.exists()),None)
    if args.config is None: ap.error('--config required')
    config=read(args.config); prepared=find_prepared(args); manifests=verify_prepared(prepared,config['regions'])
    document=stage_document(args,prepared,manifests)
    if args.partial:
        if (args.output/'receipt.json').exists(): raise ValueError('Refusing to replace a sealed final report with partial data')
        args.output.mkdir(parents=True,exist_ok=True)
        preparation_overview(args,manifests,prepared)
        if (args.output/'preparation_overview.png').exists():document['links'].append(dict(label='입력 준비 단계 모바일 요약',href='preparation_overview.png'))
        publish_document(args,document)
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
        write(args.output/'progress_receipts'/f'{stamp}_{time.time_ns()}.json',dict(status='PREPARED_STAGES_ONLY',scientific_verdict=None,
              reference_opened=False,config_sha256=sha(args.config),data_sha256=sha(args.output/'data.json')))
        print(json.dumps(dict(status='PREPARED_STAGES_ONLY',output=str(args.output))),flush=True)
    else:
        try: run_full(args,prepared,config,manifests,document)
        except Exception as error:
            args.output.mkdir(parents=True,exist_ok=True)
            failure=args.output/('failure_'+str(time.time_ns())+'.json')
            write(failure,dict(status='FAIL_REPORT_BUILD',scientific_verdict=None,error_type=type(error).__name__,error=str(error)))
            raise


if __name__=='__main__': main()
