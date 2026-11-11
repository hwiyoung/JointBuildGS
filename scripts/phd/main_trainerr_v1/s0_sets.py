"""Stage 0 (order 2.1-2.3): recount the 12 values from the stored point data, build point sets and record ranges.
No training, no mesh making. Reads only stored per-point distances, stored meshes (ray casts for c3 target distance) and GT arrays."""
import ast, gzip, importlib.util, subprocess
from common import *
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, '/repo')
from src.phd.metrics_v3.surface import MeshScene

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
NL = load_module(R/'scripts/phd/main_gtjudge_v1/normal_line.py', 'te_normal_line')

def inherit(path, names, scope):
    p = R/path; tree = ast.parse(p.read_text()); nodes = [x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef)) and x.name in names]
    assert {x.name for x in nodes} == set(names); exec(compile(ast.Module(body=nodes, type_ignores=[]), str(p), 'exec'), scope)
    return {n: scope[n] for n in names}
_env = dict(np=np, subprocess=subprocess, O=O, sha=sha, Path=Path)
_env.update(inherit('scripts/phd/main_judgeapply_v1/inherited/photo_planes.py', ['tangent'], dict(np=np)))
COLS = inherit('scripts/phd/main_rescore_v1/geometry.py', ['patch_basis', 'columns'], _env)
_env['patch_basis'] = COLS['patch_basis']
def columns(points, core, folder):
    # unchanged RESCORE geometry.columns (prism.cpp from scripts/phd/main_rescore_v1, compiled to /te/bin)
    _env['__file__'] = str(R/'scripts/phd/main_rescore_v1/geometry.py')
    src = R/'scripts/phd/main_rescore_v1/prism.cpp'; exe = O/'bin/prism'; exe.parent.mkdir(exist_ok=True)
    if not exe.exists(): subprocess.run(['g++', '-O3', '-std=c++17', str(src), '-o', str(exe)], check=True); exe.with_suffix('.sha256').write_text(sha(src))
    return COLS['columns'](points, core, folder)

def ref_part(z, method):
    return {k: z[f'reference__{method}__{k}'] for k in ['s_m', 'state', 'within_tau1']}
def res_part(z, method, keys=('point_id', 'xyz', 'normal', 'case_id', 'reference_row_id', 'wall', 'tau_m', 's_m', 'state', 'eligible_new', 'eligible_old', 'within_tau1', 'reference_found')):
    return {k: z[f'result__{method}__{k}'] for k in keys}

def acc(r, case, rule='new'):
    e = r['eligible_new' if rule == 'new' else 'eligible_old'].astype(bool) & (r['case_id'] == case)
    return 100*float((e & r['within_tau1'].astype(bool)).sum())/max(1, int(e.sum())), int(e.sum())
def comp(rp, base, case):
    m = base['case_id'] == case
    return 100*float(rp['within_tau1'][m].astype(bool).mean()), int(m.sum())

def write_set(name, cols):
    savez(O/'sets'/f'{name}.npz', **cols)
    keys = list(cols); n = len(cols[keys[0]])
    with gzip.open(O/'sets'/f'{name}.csv.gz', 'wt') as f:
        flat = []
        for k in keys:
            v = cols[k]
            if v.ndim == 2: flat += [(f'{k}_{i}', v[:, i]) for i in range(v.shape[1])]
            else: flat.append((k, v))
        f.write(','.join(h for h, _ in flat)+'\n')
        for i in range(n): f.write(','.join(str(v[i]) for _, v in flat)+'\n')

def subsample(idx, c):
    s = c['point_sets']['subsample']
    if len(idx) <= s['max_points']: return idx, False
    rng = np.random.default_rng(s['seed']); return np.sort(rng.choice(idx, s['max_points'], replace=False)), True

def main():
    c = cfg(); t0 = Timer('stage0_sets'); rows_rep = []; counts = []; lost_xyz = {s: [] for s in SCENES}
    for stem in SCENES:
        site, prior = stem.split('__'); roof_tau, wall_tau = tau_of(site, prior)
        A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); A12 = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz')
        base = {k: A11[f'reference__{k}'] for k in ['point_id', 'xyz', 'normal', 'case_id', 'wall', 'tau_m']}
        assert np.array_equal(base['point_id'], A12['reference__point_id']) and np.array_equal(base['case_id'], A12['reference__case_id'])
        rows = loadz(GT/'scenes'/stem/'rows.npz', ['xyz', 'row_owner', 'row_tau_m']); cells = loadz(GT/'scenes'/stem/'stage1_cells.npz')
        assert np.array_equal(cells['case_id'], base['case_id']) and np.allclose(rows['xyz'][base['point_id']], base['xyz'], atol=1e-3)
        core = loadz(JA/'core_points'/f'{stem}.npz'); tgt = {a: loadz(arm_paths(stem, a)['targets'], ['patch_id', 'region']) for a in ARMS}
        assert np.array_equal(tgt['own']['patch_id'], tgt['gt']['patch_id'])
        def patch_cols(owner):
            prow = np.where(owner >= 0, core['source_index'][np.clip(owner, 0, None)], -1)
            return dict(core_owner=owner.astype('i4'), patch_row=prow.astype('i8'), patch_id=np.where(prow >= 0, tgt['own']['patch_id'][np.clip(prow, 0, None)], ''),
                        judge_own=np.where(prow >= 0, tgt['own']['region'][np.clip(prow, 0, None)], -9).astype('i1'), judge_gt=np.where(prow >= 0, tgt['gt']['region'][np.clip(prow, 0, None)], -9).astype('i1'))
        refd = {m: ref_part(A11, m) for m in ['judgment_mesh', 'gt_judgment_mesh', 'FINALTRAIN_30000']}; refd['A1'] = ref_part(A12, 'A1')
        resd = {m: res_part(A11, m) for m in ['judgment_mesh', 'gt_judgment_mesh', 'FINALTRAIN_30000']}; resd['A1'] = res_part(A12, 'A1')
        for cell, cs in c['cells'].items():
            if f"{cs['site']}__{cs['prior']}" != stem: continue
            case = cs['case_id']
            for arm in ARMS:
                tm, rm = TARGET_METHOD[arm], TRAINED_METHOD[arm]
                for stage, m, exp in [('target', tm, cs['expected'][arm][0]), ('trained', rm, cs['expected'][arm][1])]:
                    if cs['metric'] == 'completeness': v, n = comp(refd[m], base, case); vo = None
                    else: v, n = acc(resd[m], case, 'new'); vo, _ = acc(resd[m], case, 'old')
                    rows_rep.append(dict(cell=cell, arm=arm, stage=stage, method=m, metric=cs['metric'], expected=exp, recounted=round(v, 4), diff_pp=round(v-exp, 4),
                                         over_0p1=abs(round(v, 1)-exp) > c['scoring']['reproduction_tolerance_pp']+1e-9, denominator=n, old_rule_accuracy=None if vo is None else round(vo, 4)))
                # ---- point sets ----
                if cs['metric'] == 'completeness':
                    sel = base['case_id'] == case; tw = refd[tm]['within_tau1'].astype(bool); rw = refd[rm]['within_tau1'].astype(bool)
                    lost = np.flatnonzero(sel & tw & ~rw); ctrl_all = np.flatnonzero(sel & tw & rw); ctrl, sub = subsample(ctrl_all, c)
                    for setname, idx in [('lost', lost), ('control', ctrl)]:
                        col = dict(point_id=base['point_id'][idx], xyz=base['xyz'][idx].astype('f8'), normal=base['normal'][idx].astype('f8'), wall=base['wall'][idx].astype('u1'),
                                   tau_m=base['tau_m'][idx].astype('f8'), **patch_cols(rows['row_owner'][base['point_id'][idx]]),
                                   judge_gt_cells=cells['judge_gt'][base['point_id'][idx]], judge_original_cells=cells['judge_original'][base['point_id'][idx]],
                                   target_s_m=refd[tm]['s_m'][idx], target_state=refd[tm]['state'][idx], trained_s_m=refd[rm]['s_m'][idx], trained_state=refd[rm]['state'][idx],
                                   set=np.full(len(idx), 0 if setname == 'lost' else 1, 'i1'))
                        write_set(f'{cell}_{arm}_{setname}', col)
                        if setname == 'lost': lost_xyz[stem].append(col['xyz'])
                    counts.append(dict(cell=cell, arm=arm, cell_rows=int(sel.sum()), lost=len(lost), control_all=len(ctrl_all), control=len(ctrl), control_subsampled=sub,
                                       few=len(lost) < c['point_sets']['few_flag']['lost_below']))
                else:
                    r = resd[rm]; e = r['eligible_new'].astype(bool) & (r['case_id'] == case); w = r['within_tau1'].astype(bool)
                    cand = np.flatnonzero(e & ~w); ctrl_all = np.flatnonzero(e & w); ctrl, sub = subsample(ctrl_all, c)
                    sc = MeshScene.from_ply(str(arm_paths(stem, arm)['target_mesh'])); idx = np.r_[cand, ctrl]
                    st, off = NL.measure(sc, r['xyz'][idx].astype('f8'), r['normal'][idx].astype('f8'), r['wall'][idx].astype(bool)); del sc
                    ts = np.full(len(r['xyz']), np.nan); ts[idx] = st
                    far = ~(np.abs(ts) <= r['tau_m'])
                    lost = cand[far[cand]]
                    if rm == 'A1': owner_all = loadz(GT/'scenes'/stem/'distances/A1_samples.npz', ['owner'])['owner']; owner = lambda ii: owner_all[r['point_id'][ii]]
                    else:
                        oo, _ = columns(r['xyz'][idx].astype('f8'), core, O/'work/columns'/f'{stem}__{rm}'); om = dict(zip(idx.tolist(), oo.tolist()))
                        owner = lambda ii: np.array([om[i] for i in ii], 'i4')
                    for setname, ii in [('lost', lost), ('control', ctrl)]:
                        rr = r['reference_row_id'][ii]
                        col = dict(point_id=r['point_id'][ii], xyz=r['xyz'][ii].astype('f8'), normal=r['normal'][ii].astype('f8'), wall=r['wall'][ii].astype('u1'), tau_m=r['tau_m'][ii].astype('f8'),
                                   **patch_cols(owner(ii)), reference_row_id=rr, judge_gt_cells=np.where(rr >= 0, cells['judge_gt'][np.clip(rr, 0, None)], -9).astype('i1'),
                                   judge_original_cells=np.where(rr >= 0, cells['judge_original'][np.clip(rr, 0, None)], -9).astype('i1'),
                                   target_s_m=ts[ii], target_state=(~np.isfinite(ts[ii])).astype('u1'), trained_s_m=r['s_m'][ii], trained_state=r['state'][ii],
                                   reference_found=r['reference_found'][ii], set=np.full(len(ii), 0 if setname == 'lost' else 1, 'i1'))
                        write_set(f'{cell}_{arm}_{setname}', col)
                        if setname == 'lost': lost_xyz[stem].append(col['xyz'])
                    counts.append(dict(cell=cell, arm=arm, cell_rows=int(e.sum()), outside_tau_to_gt=len(cand), lost=len(lost), lost_share_of_outside=len(lost)/max(1, len(cand)),
                                       control_all=len(ctrl_all), control=len(ctrl), control_subsampled=sub, few=len(lost) < c['point_sets']['few_flag']['lost_below']))
        A11.close(); A12.close()
    table('stage0_reproduce', rows_rep); table('stage0_point_sets', counts)
    # ---- record ranges (order 2.3) ----
    rg = c['region']; regs = []
    for stem, parts in lost_xyz.items():
        P = np.unique(np.concatenate(parts), axis=0); pairs = cKDTree(P).query_pairs(rg['link_m'], output_type='ndarray')
        A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(P), len(P))); n, lab = connected_components(A, directed=False)
        boxes = []
        for k in range(n):
            Q = P[lab == k]; lo, hi = Q.min(0), Q.max(0)
            boxes.append([lo[0]-rg['xy_pad_m'], hi[0]+rg['xy_pad_m'], lo[1]-rg['xy_pad_m'], hi[1]+rg['xy_pad_m'], lo[2]-rg['z_below_m'], hi[2]+rg['z_above_m'], int(len(Q))])
        boxes.sort(key=lambda b: -b[6]); v = 0.25; B = np.array([b[:6] for b in boxes])
        lo = np.floor(B[:, [0, 2, 4]].min(0)/v)*v; hi = np.ceil(B[:, [1, 3, 5]].max(0)/v)*v; shape = np.round((hi-lo)/v).astype(int)
        occ = np.zeros(shape, bool)
        for b in B:
            i0 = np.floor((b[[0, 2, 4]]-lo)/v+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/v-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
        reg = dict(stem=stem, lost_points=len(P), clusters=n, boxes=boxes, box_columns=['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax', 'points'], voxel_m=v,
                   grid_origin=lo.tolist(), grid_shape=shape.tolist(), occupied_voxels=int(occ.sum()), occupied_volume_m3=float(occ.sum()*v**3),
                   rule=rg, sources=c['region']['lost_sources'][stem], scientific_verdict=None)
        dump(O/'region'/f'{stem}.json', reg); regs.append(dict(stem=stem, lost_points=len(P), clusters=n, largest_cluster=boxes[0][6], volume_m3=reg['occupied_volume_m3'],
                                                               bbox_min=lo.tolist(), bbox_max=hi.tolist()))
    table('stage0_region', regs)
    progress(f'단계 0 재현·점 집합·기록 범위 계산 {t0.done():.0f} s')
    print('REPRO', [(r['cell'], r['arm'], r['stage'], r['recounted'], r['expected']) for r in rows_rep]); print('COUNTS', counts); print('REGION', regs)

if __name__ == '__main__': main()
