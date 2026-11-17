"""Work ra tables (order 6), addendum6_c.json (locked). CPU.
  tables : ra_base_check (base re-extraction vs the earlier mesh), ra_groups (four groups x point state, within tau per model x variant), ra_scene (completeness / accuracy),
           ra_places (B0 visible wall 0-5 / 5-10 m, R1 x LoD2 wall 1, B0 south wall) -> addendum6/ra/within_<stem>.npz (per selected point, per model x variant)
  voxels : order 6.2 - TSDF value / weight at the GT points of the B0 visible wall (0-10 m) and R1 x LoD2 wall 1 and along the outward normal (+-0.25 m), re-counted
           with the Open3D 0.19 integration rule (src/phd/streamed_tsdf.py header: no update if d <= 0 or sdf <= -trunc, else tsdf = min(1, sdf / trunc),
           sdf = d - z_voxel, weight 1 per view, running mean) from the depths each variant handed to the TSDF (the stored renders); pixel = round of the projection;
           unit allocation is not modelled (a voxel counts every view that updates it) -> addendum6/ra/voxels_<model>_<variant>.npz, tables/ra_voxels"""
import sys, hashlib
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
RA6 = A6O/'ra'; PTS = A6O/'points'; GTJ6 = A6O/'gtj'; GTJ3 = A3O/'gtj'
VARS = ['base', 'occl_10', 'median_depth', 'occl_10_median', 'target_only']
MODELS = {'R1rep_b10__LoD2': ['ft', 'sb3_7000', 'sb3_30000'], 'B0_b10__LoD2': ['ft', 'tl_7000', 'tl_30000', 'sa2_30000'], 'R1rep_b10__ALS': ['ft'], 'B0_b10__ALS': ['ft'], 'B173nb_b10__ALS': ['ft'], 'B173nb_b10__LoD2': ['ft']}
MODEL_KO = {'ft': 'FINALTRAIN 30,000', 'sb3_7000': 'sb3 7,000', 'sb3_30000': 'sb3 30,000', 'tl_7000': '기록 판 7,000', 'tl_30000': '기록 판 30,000', 'sa2_30000': '사-2 30,000'}
REUSE = {('B0_b10__ALS', 'ft', 'base'), ('B0_b10__ALS', 'ft', 'median_depth'), ('B0_b10__LoD2', 'ft', 'base'), ('B0_b10__LoD2', 'ft', 'median_depth'), ('B173nb_b10__ALS', 'ft', 'base'), ('B173nb_b10__ALS', 'ft', 'median_depth')}
PLACES = {'visible_low': 'B0 잘 보이는 벽 0–5 m', 'visible_high': 'B0 잘 보이는 벽 5–10 m', 'south_wall': 'B0 남쪽 끝 벽', 'r1_lod2_wall1': 'R1 × LoD2 1번 벽'}

def ccfg6():
    p = R/'configs/phd/main_trainerr_v1/addendum6_c.json'; assert sha(p) == json.loads(p.with_name('addendum6_c.lock.json').read_text())['config_sha256'], 'addendum6_c changed after lock'
    return json.loads(p.read_text())

def mesh_dir(stem, model, var):
    """score folder (points.npz, score.json) and gtj folder (final.ply, renders) of a re-extraction."""
    if (stem, model, var) in REUSE: k = f'{stem}__ra_{var}'; return A3O/'meshes'/k, GTJ3/'meshes'/k, GTJ3/'renders'/k
    k = f'{stem}__ra6_{model}_{var}'; return A6O/'meshes'/k, GTJ6/'meshes'/k, GTJ6/'renders'/k

def earlier(stem, model):
    """earlier mesh (final.ply / primary.ply) and its per-GT-row within tau for the base check."""
    site, prior = stem.split('__')
    if model == 'ft': return RS/'addendum3_stage2/meshes'/f'{stem}__FINALTRAIN_30000/primary.ply', ('a11', f'reference__FINALTRAIN_30000__within_tau1')
    it = model.split('_')[1]
    if model.startswith('sb3'): return A4O/'gtj/meshes'/f'{stem}__sb3_{it}/final.ply', ('pts', A4O/'meshes'/f'{stem}__sb3_{it}/points.npz')
    if model.startswith('tl'): return A4O/'gtj/meshes'/f'{stem}__tlre_{it}/final.ply', ('pts', A4O/'meshes'/f'{stem}__tlre_{it}/points.npz')
    return A4O/'gtj/meshes'/f'{stem}__sa2_30000/final.ply', ('pts', A4O/'meshes'/f'{stem}__sa2_30000/points.npz')

def place_rows(stem):
    out = {}
    for pl in PLACES:
        if (pl == 'r1_lod2_wall1') != (stem == 'R1rep_b10__LoD2'): continue
        if stem not in ('R1rep_b10__LoD2', 'B0_b10__LoD2'): continue
        P = place_points5(pl); A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); rp = A['reference__point_id']; o = np.argsort(rp); j = o[np.searchsorted(rp[o], P['point_id'])]; out[pl] = (j, P)
    return out

def tables():
    base_chk, groups, scene, places = [], [], [], []
    for stem, models in MODELS.items():
        S = loadz(PTS/f'sel_{stem}.npz'); A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); tw = A['reference__judgment_mesh__within_tau1'].astype(bool); pr = place_rows(stem); W = {}
        for model in models:
            for var in VARS:
                sd, gd, _ = mesh_dir(stem, model, var)
                if not (sd/'points.npz').exists(): continue
                w = loadz(sd/'points.npz', ['reference__within_tau1'])['reference__within_tau1'].astype(bool); W[f'{model}__{var}'] = w[S['a11_row']]
                sc = json.loads((sd/'score.json').read_text()); r0 = next(x for x in sc['rows'] if x.get('surface') == 'all' and x.get('case_id') == 0)
                scene.append(dict(stem=stem, model=MODEL_KO[model], variant=var, completeness_pct=r0['completeness_pct'], accuracy_pct=r0['accuracy_pct'], gt_no_surface_pct=r0['gt_no_surface_pct'], result_n=r0['result_n'],
                                  reused_from_addendum3=(stem, model, var) in REUSE))
                if var == 'base':
                    ep, (kind, src) = earlier(stem, model); fp = gd/'final.ply'
                    same = sha(fp) == sha(ep) if fp.exists() and ep.exists() else None
                    we = A[src].astype(bool) if kind == 'a11' else loadz(src, ['reference__within_tau1'])['reference__within_tau1'].astype(bool)
                    base_chk.append(dict(stem=stem, model=MODEL_KO[model], earlier=str(ep).replace(str(PH), 'payload'), final_ply_byte_equal=same, gt_rows=len(w), within_tau_same_pct=pct(w == we),
                                         reused_from_addendum3=(stem, model, var) in REUSE))
                for defn in ['FINALTRAIN', '그 모델의 기준 판']:
                    if defn == 'FINALTRAIN': G = S['group']
                    else:
                        if f'{model}__base' not in W: continue
                        b = W[f'{model}__base']; G = np.where(tw[S['a11_row']], np.where(b, 0, 1), np.where(b, 2, 3))
                    for stt in [0, 1, 2, 3, 4]:
                        for gk in range(4):
                            m = (G == gk) & ((S['state'] == stt) if stt else True); n = int(m.sum())
                            if n: groups.append(dict(stem=stem, model=MODEL_KO[model], variant=var, definition=defn, state='전체' if not stt else f'상태 {stt}', group=GROUP_KO[gk], n=n, small=n < 30, within_tau_pct=pct(W[f'{model}__{var}'][m])))
                for pl, (j, P) in pr.items():
                    places.append(dict(place=PLACES[pl], stem=stem, model=MODEL_KO[model], variant=var, gt_points=len(j), within_tau_pct=pct(w[j])))
        RA6.mkdir(parents=True, exist_ok=True); savez(RA6/f'within_{stem}.npz', sel_index=np.arange(len(S['group'])), **{k: v for k, v in W.items()})
        print('RA6_TAB', stem, len(W), flush=True)
    table6('ra_base_check', base_chk); table6('ra_groups', groups); table6('ra_scene', scene); table6('ra_places', places)

def voxels(stem, model, var):
    c = ccfg6()['work_ra']['voxel_values']; offs = np.asarray(c['offsets_m'], 'f8'); TR = .25
    _, _, rd = mesh_dir(stem, model, var); rec = json.loads((rd/'receipt.json').read_text()); views = rec['views']
    pls = ['visible_low', 'visible_high'] if stem == 'B0_b10__LoD2' else ['r1_lod2_wall1']; X = []; N_ = []; lab = []; tau = []
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); rp = A['reference__point_id']; o = np.argsort(rp)
    for pl in pls:
        P = place_points5(pl); X.append(P['xyz']); N_.append(P['out']); lab += [pl]*len(P['xyz']); j = o[np.searchsorted(rp[o], P['point_id'])]; tau.append(A['reference__tau_m'][j])
    X = np.concatenate(X).astype('f8'); N_ = np.concatenate(N_).astype('f8'); n = len(X); V = X[:, None, :]+offs[None, :, None]*N_[:, None, :]   # n x k x 3
    mi = json.loads((FT/'stage1'/stem/'maps/index.json').read_text())['views']; site = stem.split('__')[0]; MV = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'/site/'maps/mvs'
    tsum = np.zeros(V.shape[:2]); wsum = np.zeros(V.shape[:2]); pv = {k: [] for k in ['view', 'handed', 'z0', 'added0', 'occluded']}
    for vi, v in enumerate(views):
        K = np.asarray(v['K']); M = np.asarray(v['W2C']); d = loadz(rd/v['file'], ['depth'])['depth']; H, Wd = d.shape
        Vc = V@M[:3, :3].T+M[:3, 3]; z = Vc[..., 2]; ok = z > 0
        u = np.round(K[0, 0]*Vc[..., 0]/np.where(ok, z, 1)+K[0, 2]).astype('i8'); w_ = np.round(K[1, 1]*Vc[..., 1]/np.where(ok, z, 1)+K[1, 2]).astype('i8')
        ok &= (u >= 0) & (u < Wd) & (w_ >= 0) & (w_ < H); dd = np.where(ok, d[np.clip(w_, 0, H-1), np.clip(u, 0, Wd-1)], 0.); sdf = dd-z
        up = ok & (dd > 0) & (dd < 300.) & (sdf > -TR); t = np.minimum(1., sdf/TR); tsum += np.where(up, t, 0.); wsum += up
        k0 = int(np.argmin(np.abs(offs))); m0 = ok[:, k0]
        if m0.any():
            ii = np.flatnonzero(m0); uu = u[ii, k0]; ww = w_[ii, k0]
            with np.load(FT/'stage1'/stem/'maps'/mi[v['name']]['file']) as zz: tdep = zz['depth'][ww, uu]; tw_ = zz['weight'][ww, uu]
            mv = np.load(MV/f'{v["name"]}.npy')[ww, uu]; occ = np.isfinite(tdep) & (tdep > 0) & (tw_ > 0) & np.isfinite(mv) & (mv > 0) & (mv < tdep-10.)
            pv['view'].append(np.c_[ii, np.full(len(ii), vi)]); pv['handed'].append(dd[ii, k0]); pv['z0'].append(z[ii, k0]); pv['added0'].append(np.where(up[ii, k0], t[ii, k0], np.nan)); pv['occluded'].append(occ)
    tsdf = np.where(wsum > 0, tsum/np.maximum(wsum, 1), np.nan); pvv = {k: np.concatenate(v_) for k, v_ in pv.items()}
    sg = np.sign(tsdf); change = np.array([bool(np.any((sg[i, :-1]*sg[i, 1:]) < 0)) for i in range(n)])
    savez(RA6/f'voxels_{stem}__{model}__{var}.npz', xyz=X, out=N_, place=np.array(lab), tau=np.concatenate(tau), offsets=offs, tsdf=tsdf, weight=wsum, sign_change=change, **{f'view_{k}': v for k, v in pvv.items()})
    rows = []
    for pl in pls:
        m = np.array(lab) == pl; k0 = int(np.argmin(np.abs(offs)))
        r = dict(stem=stem, model=MODEL_KO[model], variant=var, place=PLACES[pl], points=int(m.sum()), sign_change_pct=pct(change[m]), tsdf_at_point_q=q4(tsdf[m, k0]), weight_at_point_q=q4(wsum[m, k0]),
                 no_change_all_positive_pct=pct((~change[m]) & np.all((tsdf[m] > 0) | np.isnan(tsdf[m]), 1)), no_change_all_negative_pct=pct((~change[m]) & np.all((tsdf[m] < 0) | np.isnan(tsdf[m]), 1)))
        pm = m[pvv['view'][:, 0]]
        r.update(view_pairs=int(pm.sum()), occluded_pairs_pct=pct(pvv['occluded'][pm]), added_at_point_occluded_q=q4(pvv['added0'][pm & pvv['occluded']]), added_at_point_open_q=q4(pvv['added0'][pm & ~pvv['occluded']]),
                 handed_minus_point_depth_occluded_m_q=q4((pvv['handed']-pvv['z0'])[pm & pvv['occluded'] & (pvv['handed'] > 0)]), handed_minus_point_depth_open_m_q=q4((pvv['handed']-pvv['z0'])[pm & ~pvv['occluded'] & (pvv['handed'] > 0)]),
                 no_depth_handed_pct=pct(pvv['handed'][pm] <= 0))
        for kk, of in enumerate(offs): r[f'tsdf_median_at_{of:+.2f}m'] = med(tsdf[m, kk])
        rows.append(r)
    p = A6D/'tables'/'ra_voxels.json'; old = json.loads(p.read_text())['rows'] if p.exists() else []
    old = [x for x in old if not (x['stem'] == stem and x['model'] == MODEL_KO[model] and x['variant'] == var)]+rows; table6('ra_voxels', old); print('RA6_VOX', stem, model, var, n, flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'tables': tables, 'voxels': lambda: voxels(*a[1:4])}[a[0]]()
