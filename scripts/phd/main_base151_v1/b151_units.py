"""PHD-MAIN-BASE151-v1 4.2 mesh units (configs/phd/main_base151_v1/score151.json), container side (jointbuildgs:dev, CPU; GTJUDGE
environment: /gtjudge = OUT/gt mirror, /b151 = OUT).

  python b151_units.py layout                       -> /b151/units/layout.json, /gtjudge/views/<unit>.json
  python b151_units.py job <run> <unit>             -> /gtjudge/jobs/<unit>__<P>__<run>.json (P = run prior; 2DGS: ALS key, shared)
  python b151_units.py mesh <key> <prepare|plan|tile:k|merge|finish>
Unit = (cell k, 100 m tile t): rectangle = tile core intersected with the ORIGINAL cell k rectangle, z = [GT p5 - 5 m, GT max + 5 m];
views = cell k training views with TRAINUNIT coverage > 0 of the unit box. Mesh = RESCORE mesh_pipeline.prepare + streamed TSDF (plan
auto:10) + bounded_merge + RESCORE cleanup.cpp with the unit rectangle (cos 1, sin 0 -> u = x, v = -y).
scientific_verdict: null
"""
import ast
import subprocess
import sys

import numpy as np

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
from inherited import O, module, cfg as gt_cfg, sha as gsha  # noqa: E402  (GTJUDGE O = /gtjudge)
import b151_common as BC  # noqa: E402

E0, N0 = 690953.0, 5336071.0
PRIORS = ['LoD2', 'ALS']


def inherit(path, names, scope):
    nodes = [x for x in ast.parse(Path(path).read_text()).body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    return [scope[n] for n in names]


from pathlib import Path  # noqa: E402
import json  # noqa: E402
import cv2  # noqa: E402

clip_polygon, coverage = inherit('/tus/tu_cells.py', ['clip_polygon', 'coverage'], dict(np=np, cv2=cv2))
B = BC.B


def tile_of(xy):
    e = np.floor((xy[:, 0] + E0) / 100).astype(int)
    n = np.floor((xy[:, 1] + N0) / 100).astype(int)
    return e, n


def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def cell_views(k):
    sys.path.insert(0, '/repo/scripts/phd/main_baselines_v1/cdgs')   # the exp checkout's scripts are mounted over /repo/scripts/phd
    import cdgs_io as IO
    src = BC.TU1 / 'scenes' / f'cell{k}'
    split = json.loads((src / 'split.json').read_text())
    ims = {r['name'].rsplit('.', 1)[0]: r for r in IO.read_images(src / 'scene_ALS/sparse/0/images.bin').values()}
    cal = json.loads((src / 'scene_ALS/jbgs_calibration.json').read_text())['images']
    out = []
    for n in sorted(split['train']):
        r = ims[n]
        M = np.eye(4)
        M[:3, :3] = qR(r['q'])
        M[:3, 3] = r['t']
        K = np.asarray(cal[n]['K'], float)
        out.append(dict(name=n, virtual=False, K=K.tolist(), W2C=M.tolist(), width=int(cal[n]['width']), height=int(cal[n]['height'])))
    return out


def layout():
    c = BC.cfg()
    BC.cfg('score151')
    cells = c['cells']['per_cell']
    pts = {p: np.load(B / 'gt' / f'gt151_{p}.npz') for p in PRIORS}
    keys = {}
    for p, z in pts.items():
        e, n = tile_of(z['xyz'][:, :2])
        for k in range(4):
            m = z['point_cell'] == k
            for ee, nn in set(zip(e[m].tolist(), n[m].tolist())):
                keys.setdefault((k, ee, nn), {})[p] = int((m & (e == ee) & (n == nn)).sum())
    units = []
    for (k, ee, nn), counts in sorted(keys.items()):
        cell = cells[k]
        lo = np.maximum([ee * 100 - E0, nn * 100 - N0], cell['original_min'])
        hi = np.minimum([ee * 100 + 100 - E0, nn * 100 + 100 - N0], cell['original_max'])
        zs = []
        for p, z in pts.items():
            xy = z['xyz'][:, :2]
            m = (xy >= lo).all(1) & (xy < hi).all(1) & (z['point_cell'] == k)
            zs.append(z['xyz'][m, 2])
        zz = np.concatenate(zs)
        box = [[float(lo[0]), float(lo[1]), float(np.quantile(zz, 0.05) - 5.0)], [float(hi[0]), float(hi[1]), float(zz.max() + 5.0)]]
        units.append(dict(unit=f'c{k}_{ee}_{nn}', cell=k, tile=f'{ee}_{nn}', rect_min=lo.tolist(), rect_max=hi.tolist(), box=box, gt_rows=counts,
                          area_m2=float(np.prod(hi - lo))))
    allv = {k: cell_views(k) for k in range(4)}
    for u in units:
        lo, hi = np.array(u['box'][0]), np.array(u['box'][1])
        vv = []
        for v in allv[u['cell']]:
            K = np.asarray(v['K'])
            cam = dict(W2C=v['W2C'], fx=K[0, 0], fy=K[1, 1], cx=K[0, 2] + 0.5, cy=K[1, 2] + 0.5, W=v['width'], H=v['height'])
            if coverage(cam, lo, hi) > 0:
                vv.append(dict(v, index=len(vv)))
        u['views'] = len(vv)
        BC.dump(O / 'views' / f'{u["unit"]}.json', dict(site=u['unit'], box=u['box'], views=vv, rule='cell training views with TRAINUNIT coverage > 0 of the unit box',
                                                       source='PHD-MAIN-BASE151-v1 b151_units.py layout', scientific_verdict=None))
    BC.dump(O / 'units/layout.json', dict(at=BC.now(), units=units, n=len(units), rule=BC.cfg('score151')['units'], scientific_verdict=None))
    print('UNITS', len(units), sum(u['views'] for u in units), flush=True)


def final_model(run, k):
    rec = json.loads((B / 'runs' / run / f'cell{k}' / 'receipt.json').read_text())
    assert rec['status'] == 'TRAINING_COMPLETE', (run, k, rec['status'])
    a = rec['attempts'][-1]['attempt']
    return B / 'runs' / run / f'cell{k}' / f'attempt{a}' / 'model/point_cloud/iteration_30000/point_cloud.ply'


def job(run, unit):
    lay = {u['unit']: u for u in json.loads((O / 'units/layout.json').read_text())['units']}
    u = lay[unit]
    method = run.split('_')[1]
    prior = 'ALS' if method == '2DGS' else run.split('_')[2]
    key = f'{unit}__{prior}__{run}'
    ply = final_model(run, u['cell'])
    fam = {'2DGS': '2DGS', 'GeoGS': 'GeoGS', 'CDGS': 'CDGS'}[method]
    BC.dump(O / 'jobs' / f'{key}.json', dict(site=unit, prior=prior, family=fam, key=key, ply=str(ply), box=u['box'], run=run, cell=u['cell'],
                                             note='render_model keeps the Gaussians of the cell model inside the unit box', scientific_verdict=None))
    print('JOB', key, flush=True)


def cleanup(key):
    """RESCORE cleanup.cpp unchanged with the unit rectangle (u = x, v = -y)."""
    import time
    t0 = time.monotonic()
    jobd = json.loads((O / 'jobs' / f'{key}.json').read_text())
    lay = {u['unit']: u for u in json.loads((O / 'units/layout.json').read_text())['units']}
    u = lay[jobd['site']]
    src = Path('/repo/scripts/phd/main_rescore_v1/cleanup.cpp')
    exe = O / 'bin/cleanup_b151'
    stamp = exe.with_suffix('.sha256')
    exe.parent.mkdir(exist_ok=True)
    if not exe.exists() or not stamp.exists() or stamp.read_text() != gsha(src):
        subprocess.run(['g++', '-O3', '-std=c++17', str(src), '-o', str(exe)], check=True)
        stamp.write_text(gsha(src))
    root = O / 'meshes' / key
    raw, out = root / 'final_work/merged.ply', root / 'final.ply'
    rec = out.with_suffix('.json')
    x0, y0 = u['rect_min']
    x1, y1 = u['rect_max']
    subprocess.run([str(exe), str(raw), str(out), str(rec), '1.0', '0.0', repr(x0), repr(x1), repr(-y1), repr(-y0)], check=True)
    v = json.loads(rec.read_text())
    v.update(status='PASS', unit=u['unit'], job=jobd, mesh_sha256=gsha(out), voxel_m=.05, trunc_m=.25, cluster_to_keep=50, cleanup_source_sha256=gsha(src),
             rectangle=dict(x=[x0, x1], y=[y0, y1]), inherited_rule='shared-edge triangle components; cutoff max(50, 50th-largest component triangle count); '
             'preserve all ties; remove degenerate triangles; all vertices inside the unit rectangle', seconds=time.monotonic() - t0, scientific_verdict=None)
    BC.dump(rec, v)
    print('MESH_COMPLETE', key, v['final_triangles'], flush=True)


def mesh(key, step):
    gt_cfg()
    jobd = json.loads((O / 'jobs' / f'{key}.json').read_text())
    wd = O / 'meshes' / key / 'final_work'
    sys.path.insert(0, '/repo')
    from src.phd import streamed_tsdf as T
    if step == 'prepare':
        module('mesh_pipeline').prepare(jobd, 'final')
    elif step == 'plan':
        T.plan(wd, 'auto:10')
        T.order(wd)
    elif step.startswith('tile:'):
        T.tile(wd, int(step.split(':')[1]))
    elif step == 'merge':
        module('bounded_merge').merge(wd, wd / 'merged.ply', wd / 'merged.json')
    elif step == 'finish':
        cleanup(key)
    else:
        raise ValueError(step)


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'layout':
        layout()
    elif a[0] == 'job':
        job(a[1], a[2])
    elif a[0] == 'mesh':
        mesh(a[1], a[2])
