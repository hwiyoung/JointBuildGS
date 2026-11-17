"""PHD-MAIN-TRAINUNIT-v2 cells (run with run2_cpu.sh: /tu = v2 payload, /tu1 = v1 payload ro, docs = docs/.../v2).

  python tu2_cells.py partition      # 3 x 3 cells -> /tu/cells/cells.json (same schema as v1, read by tu_campus.unit_members)
  python tu2_cells.py records        # per-plan cell records (1, 2 x 2, 3 x 3), building membership, evaluation boxes -> docs tables

The partition is tu_cells.partition with only the count changed (trainunit_v2.json cells9): cuts at np.quantile(.., [1/3, 2/3])
of the training camera centres (for two parts np.quantile(.., [.5]) is the v1 np.median). Expansion, camera selection, box z range,
and the evaluation-box relation are the v1 code (coverage(), clip_polygon(), rect_dist rule) unchanged.
"""
import sys

from tu_common import *
from tu_campus import CAMPUS, cameras, read_points3d_bin
from tu_cells import boxes, coverage

C2 = C / 'trainunit_v2.json'
TU1 = Path('/tu1')
OFFSET = np.array([690953., 5336071.])   # WIDEN0-v2 training frame = EPSG:25832 - offset (x, y)


def cfg2():
    lock = json.loads((C / 'trainunit_v2.lock.json').read_text())
    assert sha(C2) == lock['config_sha256'], 'trainunit_v2.json changed after lock'
    return json.loads(C2.read_text())


def centres(names):
    cams = {x['name']: x for x in cameras(names)}
    out = {}
    for n, c in cams.items():
        M = np.asarray(c['W2C'], float)
        out[n] = -M[:3, :3].T @ M[:3, 3]
    return cams, out


def radius(cent):
    """fork scene/dataset_readers.getNerfppNorm on the training cameras: 1.1 x max distance to their mean."""
    c = np.array(cent)
    return float(1.1 * np.linalg.norm(c - c.mean(0), axis=1).max())


def partition():
    c2 = cfg2()
    split = json.loads((CAMPUS / 'split.json').read_text())
    train, test = split['train'], split['test']
    cams, centre = centres(train + test)
    Ct = np.array([centre[n] for n in train])
    m = n = 3
    sfm, _ = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    outer_lo = np.percentile(sfm[:, :2], .5, axis=0); outer_hi = np.percentile(sfm[:, :2], 99.5, axis=0)
    q = [i / m for i in range(1, m)]
    xcut = [-np.inf] + [float(v) for v in np.quantile(Ct[:, 0], q)] + [np.inf]
    cells, cid, ycuts = [], 0, []
    for i in range(m):
        colmask = (Ct[:, 0] >= xcut[i]) & (Ct[:, 0] < xcut[i + 1])
        ycut = [-np.inf] + [float(v) for v in np.quantile(Ct[colmask, 1], [j / n for j in range(1, n)])] + [np.inf]
        ycuts.append(ycut[1:-1])
        for j in range(n):
            mask = colmask & (Ct[:, 1] >= ycut[j]) & (Ct[:, 1] < ycut[j + 1])
            lo = np.array([xcut[i], ycut[j]]); hi = np.array([xcut[i + 1], ycut[j + 1]])
            own = Ct[mask, :2]
            ext = own.max(0) - own.min(0)
            elo = lo.copy(); ehi = hi.copy()
            for a in range(2):
                if np.isfinite(lo[a]):
                    elo[a] = lo[a] - .2 * ext[a]
                if np.isfinite(hi[a]):
                    ehi[a] = hi[a] + .2 * ext[a]
            blo = np.where(np.isfinite(elo), elo, outer_lo); bhi = np.where(np.isfinite(ehi), ehi, outer_hi)
            ins = (sfm[:, 0] >= blo[0]) & (sfm[:, 0] < bhi[0]) & (sfm[:, 1] >= blo[1]) & (sfm[:, 1] < bhi[1])
            z0, z1 = np.percentile(sfm[ins, 2], [.5, 99.5])
            box_lo = np.r_[blo, z0]; box_hi = np.r_[bhi, z1]
            pos = [nm for nm in train if elo[0] <= centre[nm][0] < ehi[0] and elo[1] <= centre[nm][1] < ehi[1]]
            vis, cov = [], {}
            for nm in train:
                if nm in pos:
                    continue
                f = coverage(cams[nm], box_lo, box_hi)
                cov[nm] = f
                if f >= .25:
                    vis.append(nm)
            own_names = [nm for nm, keep in zip(train, mask) if keep]
            tst = [nm for nm in test if elo[0] <= centre[nm][0] < ehi[0] and elo[1] <= centre[nm][1] < ehi[1]]
            cells.append(dict(id=cid, column=i, row=j, original_min=lo.tolist(), original_max=hi.tolist(),
                              expanded_min=elo.tolist(), expanded_max=ehi.tolist(), projection_box_min=box_lo.tolist(), projection_box_max=box_hi.tolist(),
                              own_cameras=len(own_names), position_selected=len(pos), visibility_added=len(vis), images=sorted(pos + vis),
                              test_images=sorted(tst), coverage_quantiles_of_others=np.quantile(list(cov.values()), [.1, .5, .9]).tolist() if cov else None))
            cid += 1
    BIG = 1e6
    fin = lambda v: float(np.clip(v, -BIG, BIG))
    segs = []
    for cc in cells:
        lo, hi = cc['original_min'], cc['original_max']
        for a in range(2):
            for v in [lo[a], hi[a]]:
                if not np.isfinite(v):
                    continue
                if a == 0:
                    segs.append(dict(cell=cc['id'], axis='x', at=float(v), lo=[float(v), fin(lo[1])], hi=[float(v), fin(hi[1])]))
                else:
                    segs.append(dict(cell=cc['id'], axis='y', at=float(v), lo=[fin(lo[0]), float(v)], hi=[fin(hi[0]), float(v)]))
    out = dict(at=now(), rule=c2['cells9'], k=m * n, m=m, n=n, x_cut=xcut[1:-1], y_cuts=ycuts, train_images=len(train),
               outer_limits_sfm_p05_p995=[outer_lo.tolist(), outer_hi.tolist()], cells=cells, boundaries=segs,
               evaluation_boxes=box_relation(cells, segs), images_per_cell=[len(cc['images']) for cc in cells], scientific_verdict=None)
    out = clean(out)
    dump(TU / 'cells/cells.json', out)
    print('CELLS9', [len(cc['images']) for cc in out['cells']], [(r['site'], r['cells'], round(r['nearest_boundary_distance_m'], 2)) for r in out['evaluation_boxes']], flush=True)


def clean(v):
    if isinstance(v, dict):
        return {a: clean(b) for a, b in v.items()}
    if isinstance(v, list):
        return [clean(b) for b in v]
    if isinstance(v, float) and not np.isfinite(v):
        return 1e9 if v > 0 else -1e9
    return v


def rect_dist(alo, ahi, blo, bhi):
    dx = max(blo[0] - ahi[0], alo[0] - bhi[0], 0.); dy = max(blo[1] - ahi[1], alo[1] - bhi[1], 0.)
    return float(np.hypot(dx, dy))


def box_relation(cells, segs):
    """v1 tu_cells.partition evaluation-box rule, unchanged."""
    BIG = 1e6
    fin = lambda v: float(np.clip(v, -BIG, BIG))
    rel = []
    for site, b in boxes().items():
        lo, hi = list(map(float, b['min'][:2])), list(map(float, b['max'][:2]))
        touch = [cc['id'] for cc in cells if rect_dist(lo, hi, [fin(v) for v in cc['original_min']], [fin(v) for v in cc['original_max']]) == 0 and
                 not (hi[0] <= cc['original_min'][0] or lo[0] >= cc['original_max'][0] or hi[1] <= cc['original_min'][1] or lo[1] >= cc['original_max'][1])]
        d = [dict(segment=sg, distance_m=rect_dist(lo, hi, sg['lo'], sg['hi'])) for sg in segs]
        dmin = min(x['distance_m'] for x in d) if d else None
        rel.append(dict(site=site, box_min=lo, box_max=hi, cells=touch, boundary_crosses_box=len(touch) > 1,
                        nearest_boundary_distance_m=dmin, within_2m_band=dmin is not None and dmin <= 2.,
                        nearest=[x for x in d if x['distance_m'] == dmin][:2] if d else []))
    return rel


def footprints():
    rows = json.loads((WD / 'inputs/lod2_buildings.json').read_text())
    out = {}
    for r in rows:
        rings = [np.array(g['ext'], float)[:, :2] - OFFSET for g in r['surfaces']['ground']]
        A = cx = cy = 0.
        for p in rings:
            x, y = p[:, 0], p[:, 1]
            x1, y1 = np.roll(x, -1), np.roll(y, -1)
            cr = x * y1 - x1 * y
            a = cr.sum() / 2
            A += a; cx += ((x + x1) * cr).sum() / 6; cy += ((y + y1) * cr).sum() / 6
        allv = np.concatenate(rings)
        out[r['id']] = dict(centroid=[cx / A, cy / A], area_m2=abs(A), vmin=allv.min(0).tolist(), vmax=allv.max(0).tolist(), vertices=allv)
    return out


def membership(plan, cells, fp):
    rows, outside = [], []
    for b, f in fp.items():
        x, y = f['centroid']
        cid = [c['id'] for c in cells if c['original_min'][0] <= x < c['original_max'][0] and c['original_min'][1] <= y < c['original_max'][1]]
        assert len(cid) == 1, (plan, b, cid)
        c = cells[cid[0]]
        v = f['vertices']
        lo, hi = np.array(c['expanded_min']), np.array(c['expanded_max'])
        whole = bool(((v >= lo) & (v < hi)).all())
        rows.append(dict(plan=plan, building=b, cell=cid[0], centroid_x=x, centroid_y=y, footprint_area_m2=f['area_m2'],
                         footprint_inside_expanded_cell=whole))
        if not whole:
            outside.append(b)
    return rows, outside


def cell_records(plan, cells, U, sfm, cams_centre, tu_root=None):
    out = []
    act = U['surface_exists']
    for c in cells:
        lo, hi = np.array(c['expanded_min'], float), np.array(c['expanded_max'], float)
        inside = lambda xy: (xy[:, 0] >= lo[0]) & (xy[:, 0] < hi[0]) & (xy[:, 1] >= lo[1]) & (xy[:, 1] < hi[1])
        pm = inside(U['centre'][:, :2])
        sm = inside(sfm[:, :2])
        r = radius([cams_centre[nm] for nm in c['images']])
        blo, bhi = np.array(c['projection_box_min'][:2]), np.array(c['projection_box_max'][:2])
        olo = np.maximum(np.array(c['original_min']), blo); ohi = np.minimum(np.array(c['original_max']), bhi)
        out.append(dict(plan=plan, cell=c['id'], own_cameras=c['own_cameras'], position_selected=c['position_selected'], visibility_added=c['visibility_added'],
                        train_images=len(c['images']), test_images=len(c.get('test_images', [])), sfm_points=int(sm.sum()),
                        target_patches=int(pm.sum()), target_patches_active=int((pm & act).sum()),
                        original_width_m=float(ohi[0] - olo[0]), original_height_m=float(ohi[1] - olo[1]),
                        expanded_width_m=float(bhi[0] - blo[0]), expanded_height_m=float(bhi[1] - blo[1]),
                        scene_radius_m=r, clone_split_scale_threshold_m=.01 * r, big_prune_world_threshold_m=.1 * r,
                        position_lr_scale_m=r))
    return out


def records():
    cfg2()
    split = json.loads((CAMPUS / 'split.json').read_text())
    _, cent = centres(split['train'] + split['test'])
    U = loadz(TU / 'targets/campus__ALS.npz', ['centre', 'surface_exists'])
    sfm, _ = read_points3d_bin(WD / 'mvs/full/sparse/points3D.bin')
    outer_lo = np.percentile(sfm[:, :2], .5, axis=0); outer_hi = np.percentile(sfm[:, :2], 99.5, axis=0)
    c9 = json.loads((TU / 'cells/cells.json').read_text())
    c4 = json.loads((TU1 / 'cells/cells.json').read_text())
    BIG = 1e9
    campus = dict(id=0, original_min=[-BIG, -BIG], original_max=[BIG, BIG], expanded_min=[-BIG, -BIG], expanded_max=[BIG, BIG],
                  projection_box_min=outer_lo.tolist() + [0.], projection_box_max=outer_hi.tolist() + [0.], own_cameras=len(split['train']),
                  position_selected=len(split['train']), visibility_added=0, images=split['train'], test_images=split['test'])
    plans = [('전체', [campus], []), ('넷', c4['cells'], c4['boundaries']), ('아홉', c9['cells'], c9['boundaries'])]
    fp = footprints()
    rec, mem, boxes_t, outs = [], [], [], {}
    for plan, cells, segs in plans:
        rec += cell_records(plan, cells, U, sfm, cent)
        rows, outside = membership(plan, cells, fp)
        mem += rows
        outs[plan] = outside
        for r in box_relation(cells, segs):
            boxes_t.append(dict(plan=plan, site=r['site'], cells=r['cells'], boundary_crosses_box=r['boundary_crosses_box'],
                                nearest_original_boundary_m=r['nearest_boundary_distance_m'], within_2m=r['within_2m_band']))
    # check against the v1 records of 2 x 2 (radius 185.9 / 282.1 / 228.0 / 199.2 m in the 11-17 reply; extent_override of the runs)
    v1r = {}
    for k in range(4):
        rcp = TU1 / f'runs/ef/cellsef_ALS_s0_cell{k}/receipt.json'
        att = json.loads(rcp.read_text())['attempts'][-1]['attempt']
        e = TU1 / f'runs/ef/cellsef_ALS_s0_cell{k}/attempt{att}/extent_override.json'
        v1r[k] = json.loads(e.read_text())['fork_radius'] if e.exists() else None
    ec = json.loads((TU1 / f'runs/ef/campusef30k_ALS_s0/attempt2/extent_override.json').read_text())['fork_radius'] \
        if (TU1 / 'runs/ef/campusef30k_ALS_s0/attempt2/extent_override.json').exists() else None
    for r in rec:
        if r['plan'] == '넷':
            r['scene_radius_fork_v1_run_m'] = v1r[r['cell']]
        if r['plan'] == '전체':
            r['scene_radius_fork_v1_run_m'] = ec
    write_table('cells_records', rec, 'order v2 2.2: per plan and cell: own cameras, training images (position + visibility), SfM points and target patches with centre in the expanded cell, original/expanded cell size (infinite edges clipped at SfM 0.5/99.5 % xy), scene radius (1.1 x max distance of the training camera centres from their mean = fork getNerfppNorm) and the thresholds it sets (clone/split 0.01 r, big-Gaussian prune 0.1 r, position lr x r); 넷 = v1 cells.json (scene_radius_fork_v1_run_m: radius written by the v1 run)')
    write_table('building_membership', mem, 'order v2 0.2 / 2.2: building -> cell whose original boundary contains the GroundSurface area centroid (training frame = EPSG:25832 - (690953, 5336071)); footprint_inside_expanded_cell = all GroundSurface vertices inside the expanded cell of that cell (not corrected)')
    summ = []
    for plan, cells, _ in plans:
        rows = [r for r in mem if r['plan'] == plan]
        summ.append(dict(plan=plan, buildings=len(rows), per_cell={c['id']: sum(r['cell'] == c['id'] for r in rows) for c in cells},
                         not_whole_in_expanded_cell=len(outs[plan]), not_whole_ids=outs[plan]))
    write_table('building_membership_summary', summ, 'buildings per cell and buildings whose footprint is not wholly inside the expanded cell')
    write_table('evaluation_boxes', boxes_t, 'order v2 2.2: evaluation boxes (GTJUDGE views box) against the original cell boundaries of each plan (v1 tu_cells rule)')
    print('RECORDS', [(r['plan'], r['cell'], r['train_images'], round(r['scene_radius_m'], 1), r.get('scene_radius_fork_v1_run_m')) for r in rec], flush=True)
    print('OUTSIDE', {k: len(v) for k, v in outs.items()}, flush=True)


def write_table(name, rows, note):
    import csv
    out = D / 'tables' / name
    out.parent.mkdir(parents=True, exist_ok=True)
    dump(out.with_suffix('.json'), dict(note=note, rows=rows, scientific_verdict=None))
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with out.with_suffix('.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows([{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()} for r in rows])
    fmt = lambda v: '' if v is None else (f'{v:.3f}' if isinstance(v, float) else (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)))
    with out.with_suffix('.md').open('w') as f:
        f.write(f'{note}\n\n| ' + ' | '.join(fields) + ' |\n| ' + ' | '.join('---' for _ in fields) + ' |\n')
        for r in rows:
            f.write('| ' + ' | '.join(fmt(r.get(k)) for k in fields) + ' |\n')


def merge():
    """v1 tu_postcpu.merge rule for the nine cells: keep xy in the original cell [min, max); concatenate."""
    from tu_postcpu import write
    from plyfile import PlyData
    cfg2()
    cells = json.loads((TU / 'cells/cells.json').read_text())['cells']
    parts, rec = [], []
    for c in cells:
        run = TU / 'runs' / f'cells9ef_ALS_s0_cell{c["id"]}'
        r = json.loads((run / 'receipt.json').read_text())
        assert r['status'] == 'TRAINING_COMPLETE', (run, r['status'])
        ply = run / f'attempt{r["attempts"][-1]["attempt"]}' / 'model/point_cloud/iteration_30000/point_cloud.ply'
        v = PlyData.read(str(ply))['vertex'].data
        lo, hi = np.array(c['original_min'], float), np.array(c['original_max'], float)
        x, y = v['x'].astype(float), v['y'].astype(float)
        keep = (x >= lo[0]) & (x < hi[0]) & (y >= lo[1]) & (y < hi[1])
        parts.append(v[keep])
        rec.append(dict(cell=c['id'], ply=str(ply), sha256=sha(ply), total=len(v), kept=int(keep.sum())))
    data = np.concatenate(parts)
    out = TU / 'runs/cells9ef_ALS_s0/merged/point_cloud.ply'
    write(out, data)
    dump(out.with_suffix('.json'), dict(at=now(), prior='ALS', cells=rec, merged=len(data), output_sha256=sha(out),
         rule='keep xy in original cell [min, max); concatenate (v1 tu_postcpu.merge)', scientific_verdict=None))
    print('MERGED9', len(data), flush=True)


if __name__ == '__main__':
    dict(partition=partition, records=records, merge=merge)[sys.argv[1]](*sys.argv[2:])
