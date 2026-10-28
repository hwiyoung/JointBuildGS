"""Frozen AXES71-v2 before/after distances and baseline replay, Docker CPU only."""
import argparse
import gc
import json
import time
import traceback
from pathlib import Path
from axes_adapter import MP, ax, inputs, distances, values
from mesh_common import sha, dump, now
C, D = Path('/config'), Path('/docs')


def state(key, stage, **kw):
    row = dict(key=key, stage=stage, at=now(), scientific_verdict=None, **kw)
    dump(MP/'status'/f'axes_{key}.json', row)
    print(json.dumps(row, ensure_ascii=False), flush=True)


def config():
    p = C/'axes_addendum_v1.json'
    assert sha(p) == json.loads((C/'axes_addendum_v1.lock.json').read_text())['sha256']
    return json.loads(p.read_text())


def targets(cfg):
    return json.loads((C/'mesh_targets_v1.json').read_text())['targets'] + cfg['extra_targets']


def verify_inputs(cfg, site):
    for row in cfg['inputs']:
        if row['site'] in (None, site):
            assert sha(row['path']) == row['sha256'], row['path']


def measure(row, stage, mesh, expected_sha, ctx):
    key = row['key']
    folder = MP/'axes_dist'/key/stage
    record = folder/'values.json'
    if record.exists():
        r = json.loads(record.read_text())
        assert r['mesh_sha256'] == expected_sha
        return r
    state(key, stage+'_distance', mesh=str(mesh))
    assert sha(mesh) == expected_sha, str(mesh)
    t = time.monotonic()
    paths = distances(row['site'], row['prior'], row['result'], mesh, folder, ctx)
    state(key, stage+'_aggregation')
    data = values(row['site'], row['prior'], row['result'], ctx, paths)
    r = dict(status='PASS', key=key, stage=stage, mesh=str(mesh), mesh_sha256=expected_sha,
             per_point_files=[dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size) for p in paths if p],
             values=data, seconds=time.monotonic()-t, finished_at=now(), scientific_verdict=None)
    dump(record, r)
    return r


def parity(saved_only=False):
    cfg = config()
    p = D/'tables'/('axes_saved_aggregation_replay.json' if saved_only else 'axes_baseline_replay.json')
    if p.exists():
        r = json.loads(p.read_text())
        assert r['status'] == 'PASS', 'baseline replay previously failed; inspect its record'
        return r
    ref = cfg['baseline']
    row = next(r for r in targets(cfg) if r['key'] == ref['key'])
    verify_inputs(cfg, row['site'])
    ctx = inputs(row['site'], row['prior'])
    if saved_only:
        paths=(ax.dist_file(row['site'],row['prior'],row['result']),ax.x_file(row['site'],row['prior'],row['result']),ax.b0gt_file(row['site'],row['prior'],row['result']))
        actual=values(row['site'],row['prior'],row['result'],ctx,paths)
    else:
        actual = measure(row, 'before', Path(row['mesh']), row['sha256'], ctx)['values']
    unit = row['site']+'/'+row['prior']
    expected = json.loads((ax.TAB/'a3_metrics.json').read_text())['data'][unit][ref['method']]['values'][row['result']]
    checks = []
    def compare(name, got, want, share=False):
        tol = cfg['parity_tolerance']['share_abs' if share else 'distance_cm_abs']
        good = got is None and want is None if got is None or want is None else abs(got-want) <= tol
        checks.append(dict(field=name, actual=got, expected=want, tolerance=tol, pass_check=good))
    for key, want in expected.items():
        got = actual['axes71_cells'][key]
        if not str(got['status']).startswith('있음') or not str(want['status']).startswith('있음'):
            continue
        for name in ['R_tau', 'mean', 'med', 'out4', 'far1', 'n_gt']:
            compare(f'{key}/gt/{name}', got['gt'].get(name), want['gt'].get(name), name in ['R_tau','out4','far1'])
        for name in ['P_tau', 'mean', 'n', 'excluded']:
            compare(f'{key}/res/E/{name}', got['res']['E'].get(name), want['res']['E'].get(name), name=='P_tau')
    original_axes = json.loads((ax.TAB/'a4_axes.json').read_text())['data'][unit][ref['method']][row['result']]
    for line, bins in original_axes.items():
        for i, want in bins.items():
            got = actual['axes'][line][i]
            for name in ['R_tau','P_tau','mean','res_mean','med','n_gt','n_res','excluded_share']:
                compare(f'{line}/{i}/{name}',got.get(name),want.get(name), name in ['R_tau','P_tau','excluded_share'])
    assert checks
    passed = all(r['pass_check'] for r in checks)
    result = dict(status='PASS' if passed else 'STOP_BASELINE_MISMATCH', key=row['key'],
                  full_geometry_recomputed=not saved_only,
                  source_mesh_sha256=row['sha256'], checks=checks, comparisons=len(checks), failed=sum(not r['pass_check'] for r in checks),
                  source_reports=[str(ax.TAB/'a3_metrics.json'), str(ax.TAB/'a4_axes.json')],
                  finished_at=now(), scientific_verdict=None)
    dump(p, result)
    state(row['key'], ('saved_aggregation_verified' if saved_only else 'baseline_verified') if passed else 'STOP_BASELINE_MISMATCH', comparisons=len(checks), failed=result['failed'])
    assert passed, 'AXES71-v2 baseline mismatch; new metric queue stopped'
    return result


def process(key):
    cfg = config()
    assert json.loads((D/'tables/axes_baseline_replay.json').read_text())['status']=='PASS'
    out = D/'tables/axes'/f'{key}.json'
    if out.exists():
        return json.loads(out.read_text())
    row = next(r for r in targets(cfg) if r['key']==key)
    clean = json.loads((D/'tables/meshes'/f'{key}.json').read_text())
    if clean['status'] in ['UNAVAILABLE', 'UNAVAILABLE_FROZEN_STOP']:
        result=dict(key=key,status=clean['status'],reason=clean.get('reason'),target=row,scientific_verdict=None)
        dump(out,result)
        return result
    assert clean['status']=='PASS', 'cleanup must be complete'
    verify_inputs(cfg,row['site'])
    ctx=inputs(row['site'],row['prior'])
    before=measure(row,'before',Path(row['mesh']),row['sha256'],ctx)
    post=MP/Path(clean['cleanup']['output']).relative_to('/out')
    after=measure(row,'after',post,clean['cleanup']['output_sha256'],ctx)
    result=dict(key=key,target=row,status='PASS',before=before,after=after,finished_at=now(),
                units=dict(shares='fraction 0..1',distances='cm, uncapped'),scientific_verdict=None)
    dump(out,result)
    state(key,'complete',seconds=before['seconds']+after['seconds'])
    del ctx
    gc.collect()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('key');args=parser.parse_args()
    try:
        parity(args.key=='baseline-saved') if args.key in ['baseline','baseline-saved'] else process(args.key)
    except Exception as exc:
        state(args.key,'FAILED',error=str(exc),traceback=traceback.format_exc())
        with (D/'issues.md').open('a') as f:
            f.write(f'\n- {now()}: AXES71 추가 지표 {args.key} 실패: {type(exc).__name__}: {exc}. 원본 입력과 기존 결과는 보존.\n')
        raise
