"""Stage 4 (order 6.1, 6.2): simulations and confirm-run scoring.
  prep <stem> <arm> <cls> [tag]  (CPU): population of the class inside the scene range from the 30000 state -> drop list + PLY without them (= opacity 0)
  eval <stem> <arm> <family>     (CPU): recovery, control loss, scene accuracy loss, 6-가..라 for every cell of the stem
  host <gpu> <stem> <arm> <cls> [...]: prep -> unchanged mesh recipe (te_mesh via launch.gtj) -> full score -> eval"""
import struct
from common import *
POP = {'3-라': 'bg', '3-다': 'rel', '3-나': 'nbr', '3-가': 'same'}

def ply_filter(src, dst, keep):
    with open(src, 'rb') as f:
        head = b''
        while True:
            line = f.readline(); head += line
            if line.strip() == b'end_header': break
        props = [l.split()[1] for l in head.decode('ascii').splitlines() if l.startswith('property')]
        n = int(next(l.split()[2] for l in head.decode('ascii').splitlines() if l.startswith('element vertex'))); size = {b'float': 4, 'float': 4}
        rec = 4*len(props); assert all(p == 'float' for p in props), 'non-float PLY property'
        data = np.frombuffer(f.read(n*rec), dtype=np.uint8).reshape(n, rec)
    out = data[keep]; h = head.decode('ascii').replace(f'element vertex {n}', f'element vertex {len(out)}')
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, 'wb') as f: f.write(h.encode('ascii')); f.write(out.tobytes())

def region_inside(stem, xyz):
    reg = json.loads((O/'region'/f'{stem}.json').read_text()); v = float(reg['voxel_m']); lo = np.asarray(reg['grid_origin']); shape = tuple(reg['grid_shape']); occ = np.zeros(shape, bool)
    for b in reg['boxes']:
        b = np.asarray(b[:6], float); i0 = np.floor((b[[0, 2, 4]]-lo)/v+1e-9).astype(int); i1 = np.ceil((b[[1, 3, 5]]-lo)/v-1e-9).astype(int); occ[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
    k = np.floor((xyz-lo)/v).astype(int); ok = ((k >= 0) & (k < np.array(shape))).all(1); out = np.zeros(len(xyz), bool); out[ok] = occ[k[ok, 0], k[ok, 1], k[ok, 2]]; return out

def prep(stem, arm, cls, tag=''):
    from s0_sets import columns
    ap = arm_paths(stem, arm); model = Path(ap['model']); snap = loadz(model/'target_monitor/snapshot_30000.npz', ['xyz', 'origin', 'target_tag', 'target_index', 'patch_ids'])
    ins = region_inside(stem, snap['xyz'].astype(float)); tag_ = snap['target_tag']; ori = snap['origin']
    if cls == '3-라': sel = ins & (ori == 0) & (tag_ != 1)
    elif cls == '3-다': sel = ins & (ori == 1) & (tag_ == 2)
    else:
        b = np.flatnonzero(ins & (tag_ == 1)); core = loadz(JA/'core_points'/f'{stem}.npz'); own, _ = columns(snap['xyz'][b].astype('f8'), core, O/'work/columns'/f'sim_{stem}_{arm}')
        colrow = np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1); bp = snap['patch_ids'][snap['target_index'][b]]
        pick = (bp == colrow) if cls == '3-가' else (bp != colrow); sel = np.zeros(len(ins), bool); sel[b[pick]] = True
    fam = f'sim_{arm}_{POP[cls]}'; drop = np.flatnonzero(sel); ply = model/'point_cloud/iteration_30000/point_cloud.ply'
    out = O/'sim'/f'{stem}__{fam}'; savez(out/'drop.npz', full_index=drop); ply_filter(ply, out/'point_cloud.ply', ~sel)
    dump(out/'prep.json', dict(at=now(), stem=stem, arm=arm, cls=cls, family=fam, population=cfg()['check6']['populations'][cls], in_range=int(ins.sum()), dropped=len(drop),
         gaussians=len(sel), source_ply=str(ply), source_sha256=sha(ply), ply=str(out/'point_cloud.ply'), ply_sha256=sha(out/'point_cloud.ply'), rule='removed Gaussians = opacity 0', scientific_verdict=None))
    print('PREP', stem, arm, cls, len(drop), flush=True)

def scene_accuracy(res):
    e = res['eligible_new'].astype(bool); return 100*float((e & res['within_tau1'].astype(bool)).sum())/max(1, int(e.sum()))

def eval_(stem, arm, family):
    c = cfg(); sys.path.insert(0, '/repo')
    from src.phd.metrics_v3.surface import MeshScene
    from s0_sets import NL
    Z = loadz(O/'meshes'/f'{stem}__{family}'/'points.npz'); tm, rm = TARGET_METHOD[arm], TRAINED_METHOD[arm]
    A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); Ar = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz') if rm == 'A1' else A11
    base_case = A11['reference__case_id']; res_tr = {k: Ar[f'result__{rm}__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']}
    res_tg = {k: A11[f'result__{tm}__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']}
    res_new = {k: Z[f'result__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']}; rows = []
    mesh = O/'gtj/meshes'/f'{stem}__{family}'/'final.ply'; sc = None
    for cell, cs in c['cells'].items():
        if f"{cs['site']}__{cs['prior']}" != stem: continue
        case = cs['case_id']
        if cs['metric'] == 'completeness':
            m = base_case == case; tgt = 100*float(A11[f'reference__{tm}__within_tau1'][m].astype(bool).mean()); tr = 100*float(Ar[f'reference__{rm}__within_tau1'][m].astype(bool).mean())
            new = 100*float(Z['reference__within_tau1'][m].astype(bool).mean())
            lost = loadz(O/'sets'/f'{cell}_{arm}_lost.npz', ['point_id'])['point_id']; ctrl = loadz(O/'sets'/f'{cell}_{arm}_control.npz', ['point_id'])['point_id']
            lost_rec = 100*float(Z['reference__within_tau1'][lost].astype(bool).mean()) if len(lost) else None
            ctrl_loss = 100-100*float(Z['reference__within_tau1'][ctrl].astype(bool).mean()) if len(ctrl) else None
        else:
            f = lambda r: 100*float((r['eligible_new'].astype(bool) & (r['case_id'] == case) & r['within_tau1'].astype(bool)).sum())/max(1, int((r['eligible_new'].astype(bool) & (r['case_id'] == case)).sum()))
            tgt, tr, new = f(res_tg), f(res_tr), f(res_new); lost_rec = None
            if sc is None: sc = MeshScene.from_ply(str(mesh))
            cz = loadz(O/'sets'/f'{cell}_{arm}_control.npz', ['xyz', 'normal', 'wall', 'tau_m']); s, _ = NL.measure(sc, cz['xyz'], cz['normal'], cz['wall'].astype(bool))
            ctrl_loss = 100-100*float((np.isfinite(s) & (np.abs(s) <= cz['tau_m'])).mean())
        rec = (new-tr)/(tgt-tr) if abs(tgt-tr) > 1e-9 else None
        acc_loss = scene_accuracy(res_tr)-scene_accuracy(res_new)
        r = 100*rec if rec is not None else None
        k = cfg()['check6']['classes']
        cls = None if r is None else ('6-가' if r >= 50 and ctrl_loss <= 2 and acc_loss <= 2 else ('6-나' if r >= 50 else ('6-다' if r >= 20 else '6-라')))
        rows.append(dict(stem=stem, arm=arm, family=family, cell=cell, target=tgt, trained=tr, after=new, recovery_pct=r, lost_point_recovery_pct=lost_rec, control_loss_pp=ctrl_loss,
                         scene_accuracy_trained=scene_accuracy(res_tr), scene_accuracy_after=scene_accuracy(res_new), scene_accuracy_loss_pp=acc_loss, cls=cls))
    A11.close()
    dump(O/'sim'/f'{stem}__{family}'/'eval.json', dict(at=now(), rows=rows, scientific_verdict=None)); print('EVAL', rows, flush=True)

def host(gpu, stem, arm, *classes):
    sys.path.insert(0, str(Path(__file__).parent)); import launch as Lc
    from te_pipeline import must
    for cls in classes:
        fam = f'sim_{arm}_{POP[cls]}'; wd = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final_work'; final = Lc.O/'gtj/meshes'/f'{stem}__{fam}'/'final.ply'
        if not (Lc.O/'sim'/f'{stem}__{fam}'/'prep.json').exists(): must(Lc.job('te_sim.py', 'prep', stem, arm, cls, cpus=12, memory='40g'), 'prep')
        ply = f'/te/sim/{stem}__{fam}/point_cloud.ply'
        if not final.exists():
            if not (Lc.O/'gtj/renders'/f'{stem}__{fam}'/'receipt.json').exists(): must(Lc.gtj('render', stem, fam, ply, int(gpu)), 'render')
            for st in ['prepare', 'plan']:
                if st == 'prepare' and (wd/'binding.json').exists(): continue
                if st == 'plan' and (wd/'plan/plan.json').exists(): continue
                must(Lc.gtj(st, stem, fam), st)
            n = len(json.loads((wd/'plan/plan.json').read_text())['tiles'])
            for k in range(n):
                if not ((wd/'tiles'/f'tile{k}.npz').exists() and (wd/'tiles'/f'tile{k}.json').exists()): must(Lc.gtj(f'tile:{k}', stem, fam), f'tile {k}')
            if not (wd/'merged.json').exists():
                if Lc.gtj('merge', stem, fam): must(Lc.gtj('recover', stem, fam), 'recover')
            must(Lc.gtj('finish', stem, fam), 'finish')
        if not (Lc.O/'meshes'/f'{stem}__{fam}'/'score.json').exists(): must(Lc.gtj('score', stem, fam), 'score')
        must(Lc.job('te_sim.py', 'eval', stem, arm, fam), 'eval'); Lc.gtj('clean', stem, fam)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'prep': prep(*a[1:])
    elif a[0] == 'eval': eval_(*a[1:])
    elif a[0] == 'host': host(*a[1:])
