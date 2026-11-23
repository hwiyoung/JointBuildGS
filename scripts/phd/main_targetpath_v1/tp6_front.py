"""Order 4: who draws the surface at the point (CPU; reads /tp/contrib, the 30,000 ply and target_monitor snapshot). usage: tp6_front.py
Per (point, facing view) pair of 가: 잃음 (and 가: 지킴 for reference) and 나: 고침 (and 나: 고치지 못함 where computed): the three splats of largest
weight at the pixel. Kind of a splat (snapshot_30000): target_tag 1 and its target (patch_ids[target_index]) = the point's method target patch ->
같은 목표에 위치 제약; tag 1 and another target -> 다른 목표에 위치 제약 (with that target's judgment region and whether that target is right:
share of the wrong-target point file's points of that patch whose method target is within tau >= 0.5); tag 2 -> 제약 해제; else 제약 없음.
Distance along the ray: splat depth - point depth (front < -tau, within, behind > tau). Opacity, size (larger scale).
가 only: share of splats whose centre height equals, within tau, the height of a GT point at 1-3 m horizontal distance from the point
('양옆의 면이 이어져 걸친 것'; GT points at the point's own height (within tau) are left out); same in the GTT run for the same points.
나 (order 4 bullet 4): seeds of the point's (wrong) method target patch at 30,000: descendants (snapshot init_id) inside the patch's allowed band
(target_tag 1, same target, |n.(x - anchor)| <= 1.96 sigma), same target outside the band, retargeted to another target, released, other; seed with no
descendant -> removed. Per point the best fate (차례: 구간 안 > 같은 목표 구간 밖 > 재할당 > 제약 해제 > 그 밖 > 제거).
R1 x ALS: exit paths and times of the Gaussians bound to the point's target patch in the TRAINLOG record run (TRAINERR addendum6 ga
patch_R1rep_b10__ALS.npz, run tl_R1_ALS_own = a rerun of the FINALTRAIN recipe with whole-scene dumps, not the FINALTRAIN model itself).
Writes tables tp_front, tp_front_other, tp_height, tp_seed_fate, tp_track (+ per point main kind into /tp/points/front_<stem>.npz)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from scipy.spatial import cKDTree
MIN = 1000
FATE = ['조각 허용 구간 안', '같은 목표, 구간 밖', '다른 목표로 재할당', '제약 해제', '그 밖(제약 없음)', '제거']
PATHS_KO = ['제약 해제', '재할당', '재설정 뒤 제거', '그 밖의 제거', '분할로 대체']

def share(a, b): return round(100*a/b, 2) if b else None

def model_arrays(stem, run):
    m = model_of(stem, run); g = ply_read(m/'point_cloud/iteration_30000/point_cloud.ply', ['x', 'y', 'z', 'scale_0', 'scale_1', 'opacity'])
    s = loadz(m/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index', 'patch_ids', 'init_id'])
    xyz = np.c_[g['x'], g['y'], g['z']]; assert len(s['xyz']) == len(xyz) and np.abs(s['xyz']-xyz).max() < 1e-4
    ti = s['target_index']; row = np.where(s['target_tag'] == 1, s['patch_ids'][np.clip(ti, 0, len(s['patch_ids'])-1)], -1)
    return dict(xyz=xyz, op=1/(1+np.exp(-g['opacity'])), size=np.exp(np.maximum(g['scale_0'], g['scale_1'])), tag=s['target_tag'], row=row, init=s['init_id'], ti=ti)

def height_match(pt, Xall, tau, zc, gt2d, gtz):
    """per pair: True if a GT point at 1-3 m horizontal distance from the pair's point, on another surface (|z_gt - z_point| > tau), has
    |z_gt - z_centre| <= tau. Neighbours are found once per point (sorted heights), pairs are tested by binary search."""
    up = np.unique(pt); out = np.zeros(len(pt), bool); order = np.argsort(pt, kind='stable'); ps = pt[order]
    for a in range(0, len(up), 500):
        u = up[a:a+500]; nb = gt2d.query_ball_point(Xall[u, :2], 3.0, workers=8)
        for k, q_ in zip(u, nb):
            if not q_: continue
            q_ = np.asarray(q_); dxy = np.linalg.norm(gt2d.data[q_]-Xall[k, :2], axis=1); hz = gtz[q_[dxy >= 1.0]]; tp_ = tau[order[np.searchsorted(ps, k)]]; hz = np.sort(hz[np.abs(hz-Xall[k, 2]) > tp_])
            if not len(hz): continue
            m = order[np.searchsorted(ps, k):np.searchsorted(ps, k, 'right')]; lo = np.searchsorted(hz, zc[m]-tau[m]); hi = np.searchsorted(hz, zc[m]+tau[m], 'right'); out[m] = hi > lo
    return out

def main():
    t0 = time.monotonic(); front, other, height, fate, track = [], [], [], [], []
    for stem in STEMS:
        site = stem.split('__')[0]; P = loadz(O/'points'/f'sel_{stem}.npz'); n = len(P['group']); jreg = loadz(FT/'targets'/f'{stem}.npz', ['judge_region'])['judge_region']
        pok = P['patch_ok_share_all']; A = gt_reference(stem); gxyz = A['reference__xyz'].astype('f8'); gt2d = cKDTree(gxyz[:, :2]); gtz = gxyz[:, 2]
        per = {}
        for run in ['ft', 'gtt']:
            cf = [O/'contrib'/f'{run}_{stem}_{m}.npz' for m in ('all', 'sub')]; cf = [p for p in cf if p.exists()]
            if not cf or not has_run(stem, run): continue
            c = loadz(cf[0]); Mg = model_arrays(stem, run); pt = c['pt'].astype('i8'); z = c['z'].astype('f8'); tau = P['tau'][pt].astype('f8'); grp = P['group'][pt]
            zp = loadz(O/'pairs'/f'{run}_{stem}.npz', ['pt', 'view', 'occ10']); key = zp['pt'].astype('i8')*100000+zp['view']; oo_ = np.argsort(key); k2 = pt*100000+c['view']
            pp_ = np.clip(np.searchsorted(key[oo_], k2), 0, len(oo_)-1); assert (key[oo_][pp_] == k2).all(); occ10 = zp['occ10'][oo_][pp_]
            tg = c['top_g']; has = tg >= 0; g_ = np.where(has, tg, 0)
            if run == 'ft': own = P['patch_row'][pt]
            else: own = P['gt_square'][pt]
            kind = np.where(Mg['tag'][g_] == 1, np.where(Mg['row'][g_] == own[:, None], 0, 1), np.where(Mg['tag'][g_] == 2, 2, 3)); kind[~has] = -1
            dist = c['top_dep'].astype('f8')-z[:, None]; dpos = np.where(dist < -tau[:, None], 0, np.where(dist > tau[:, None], 2, 1)); dpos[~has] = -1
            op = np.where(has, Mg['op'][g_], np.nan); size = np.where(has, Mg['size'][g_], np.nan)
            orow = np.where(kind == 1, Mg['row'][g_], -1); oreg = np.where(orow >= 0, jreg[np.clip(orow, 0, None)] if run == 'ft' else -1, -9)
            ook = np.where(orow >= 0, pok[np.clip(orow, 0, len(pok)-1)] >= .5 if run == 'ft' else False, False)
            hm = np.zeros(len(pt), bool); gsel = np.isin(grp, [0, 1]) & has[:, 0]
            if gsel.any(): hm[gsel] = height_match(pt[gsel], P['xyz'].astype('f8'), tau[gsel], Mg['xyz'][g_[gsel, 0], 2].astype('f8'), gt2d, gtz)
            per[run] = dict(pt=pt, kind=kind, hm=hm, gsel=gsel, vis=~occ10)
            for vs, vmask in [('가려지지 않은 영상(10 m 규칙)', ~occ10), ('바깥쪽 모든 영상', np.ones(len(pt), bool))]:
              for g in sorted(set(grp.tolist())):
                m = (grp == g) & vmask; npts = int((P['group'] == g).sum()); big = npts >= MIN; k1 = kind[m, 0]; w1 = c['top_w'][m]
                r = dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO[run], view_set=vs, group=GRP[g], points=npts, pairs=int(m.sum()), pairs_with_splat=int(has[m, 0].sum()),
                         acc_median=float(np.nanmedian(c['acc'][m])) if m.any() else None)
                for i, nm in enumerate(GKIND):
                    r[f'top1_{nm}_pct'] = share(int((k1 == i).sum()), int((k1 >= 0).sum())) if big else None
                    wk = (kind[m] == i)*w1; r[f'top3w_{nm}_pct'] = share(float(wk.sum()), float(w1[kind[m] >= 0].sum())) if big else None
                for i, nm in enumerate(POS3): r[f'top1_{nm}_pct'] = share(int((dpos[m, 0] == i).sum()), int((dpos[m, 0] >= 0).sum())) if big else None
                r['top1_offset_tau_median'] = float(np.nanmedian((dist[m, 0]/tau[m]))) if m.any() else None
                r['top1_opacity_median'] = float(np.nanmedian(op[m, 0])) if m.any() else None; r['top1_size_median_m'] = float(np.nanmedian(size[m, 0])) if m.any() else None
                r['top1_weight_median'] = float(np.median(w1[:, 0])) if m.any() else None
                for rk in (1, 2):   # 2nd and 3rd largest-weight splat: same columns as the 1st (verification addendum, order 4 first bullet)
                    kr = kind[m, rk]; hr = has[m, rk]; t = f'top{rk+1}'; r[f'{t}_pairs_with_splat'] = int(hr.sum())
                    for i, nm in enumerate(GKIND): r[f'{t}_{nm}_pct'] = share(int((kr == i).sum()), int((kr >= 0).sum())) if big else None
                    for i, nm in enumerate(POS3): r[f'{t}_{nm}_pct'] = share(int((dpos[m, rk] == i).sum()), int((dpos[m, rk] >= 0).sum())) if big else None
                    r[f'{t}_offset_tau_median'] = float(np.nanmedian(dist[m, rk][hr]/tau[m][hr])) if hr.any() else None
                    r[f'{t}_opacity_median'] = float(np.nanmedian(op[m, rk][hr])) if hr.any() else None; r[f'{t}_size_median_m'] = float(np.nanmedian(size[m, rk][hr])) if hr.any() else None
                    r[f'{t}_weight_median'] = float(np.median(w1[hr, rk])) if hr.any() else None
                front.append(r)
                k1o = m[:, None] & (kind == 1)
                ro = dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO[run], view_set=vs, group=GRP[g], points=npts, other_target_splats=int(k1o.sum()),
                          other_target_right_pct=share(int((k1o & ook).sum()), int(k1o.sum())) if (big and run == 'ft') else None)
                for rg, nm in [(0, '일치'), (1, '보존'), (2, '보정'), (3, '보정(빈 공간)'), (4, '결측'), (9, '미판정')]:
                    ro[f'other_region_{nm}_pct'] = share(int((k1o & (oreg == rg)).sum()), int(k1o.sum())) if (big and run == 'ft') else None
                other.append(ro)
            # per point main kind (top-1 kind with most views)
            mk = np.full(n, -1, 'i1'); cnt = np.zeros((n, 4), 'i4'); v = kind[:, 0] >= 0; np.add.at(cnt, (pt[v], kind[v, 0]), 1); h = cnt.sum(1) > 0; mk[h] = cnt[h].argmax(1)
            savez(O/'points'/f'front_{run}_{stem}.npz', main_kind=mk, kind_views=cnt)
        # height table: same points, both runs side by side
        for vs in ['가려지지 않은 영상(10 m 규칙)', '바깥쪽 모든 영상']:
          for g in [0, 1]:
            npts = int((P['group'] == g).sum()); r = dict(title=TITLE, stem=STEM_KO[stem], view_set=vs, group=GRP[g], points=npts)
            for run in ['ft', 'gtt']:
                if run not in per: r[f'{run}_height_match_pct'] = None; continue
                d = per[run]; m = d['gsel'] & (P['group'][d['pt']] == g) & (d['vis'] if vs[0] == '가' else True); r[f'{run}_pairs'] = int(m.sum())
                r[f'{run}_height_match_pct'] = share(int(d['hm'][m].sum()), int(m.sum())) if npts >= MIN else None; r[f'{run}_height_match_n'] = int(d['hm'][m].sum())
                pp = np.bincount(d['pt'][m], d['hm'][m], n); pn = np.bincount(d['pt'][m], minlength=n); sel = pn > 0
                r[f'{run}_points_majority_match_n'] = int((pp[sel]/pn[sel] > .5).sum())
            height.append(r)
        # 나 seeds fate (FINALTRAIN)
        s = loadz(ft_model(stem)/'target_monitor/snapshot_30000.npz', ['xyz', 'target_tag', 'target_index', 'patch_ids', 'init_id', 'patch_anchor', 'patch_normal', 'patch_sigma'])
        sd = loadz(FT/'stage1'/stem/'seeds.npz', ['patch', 'origin']); ti = np.clip(s['target_index'], 0, len(s['patch_ids'])-1); tag = s['target_tag']
        row = np.where(tag == 1, s['patch_ids'][ti], -1); hgt = np.abs(((s['xyz']-s['patch_anchor'][ti])*s['patch_normal'][ti]).sum(1)); band = hgt <= 1.96*s['patch_sigma'][ti]
        o = np.argsort(s['init_id'], kind='stable'); ii = s['init_id'][o]; st_ = np.searchsorted(ii, np.arange(len(sd['patch'])+1))
        seeds_of = {}; ps = np.flatnonzero((sd['origin'] == 1) & (sd['patch'] >= 0)); oo = np.argsort(sd['patch'][ps], kind='stable'); sp = sd['patch'][ps][oo]; sidx = ps[oo]
        for g in [2, 3]:
            sel = np.flatnonzero(P['group'] == g); pts_f = np.full(len(sel), -1); cnts = np.zeros(len(FATE), 'i8'); nseed = 0
            for a, k in enumerate(sel):
                prw = P['patch_row'][k]
                if prw < 0: continue
                lo, hi = np.searchsorted(sp, prw), np.searchsorted(sp, prw, 'right'); best = 9
                for sdx in sidx[lo:hi]:
                    nseed += 1; dsc = o[st_[sdx]:st_[sdx+1]]
                    if not len(dsc): f = 5
                    else:
                        fs = np.where(tag[dsc] == 1, np.where(row[dsc] == prw, np.where(band[dsc], 0, 1), 2), np.where(tag[dsc] == 2, 3, 4)); f = int(fs.min())
                    cnts[f] += 1; best = min(best, f)
                pts_f[a] = best if best < 9 else -1
            npts = len(sel); r = dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO['ft'], group=GRP[g], points=npts, points_with_seeds=int((pts_f >= 0).sum()), seeds=int(nseed))
            for i, nm in enumerate(FATE):
                r[f'seed_{nm}_pct'] = share(int(cnts[i]), int(cnts.sum())) if npts >= MIN else None; r[f'seed_{nm}_n'] = int(cnts[i])
                r[f'point_best_{nm}_pct'] = share(int((pts_f == i).sum()), int((pts_f >= 0).sum())) if npts >= MIN else None; r[f'point_best_{nm}_n'] = int((pts_f == i).sum())
            fate.append(r)
        # R1 x ALS exit paths (record run)
        if stem == 'R1rep_b10__ALS':
            a = loadz(TE/'addendum6/ga/patch_R1rep_b10__ALS.npz'); pid = s['patch_ids']; Pv = a['patches']; it = a['iterations']; nm_ = a['names']
            pos = {int(p): i for i, p in enumerate(Pv)}
            for g in [0, 1, 2, 3]:
                sel = np.flatnonzero(P['group'] == g); vx = np.searchsorted(pid, P['patch_row'][sel]); okv = (P['patch_row'][sel] >= 0) & (vx < len(pid))
                okv[okv] &= pid[vx[okv]] == P['patch_row'][sel][okv]; idx_ = np.array([pos.get(int(v), -1) if o_ else -1 for v, o_ in zip(vx, okv)])
                cov = idx_ >= 0; pc = a['path_counts'][idx_[cov]]; mp = a['main_path'][idx_[cov]]; fe = a['first_empty'][idx_[cov]]
                r = dict(title=TITLE, stem=STEM_KO[stem], run='TRAINLOG 기록 판(tl_R1_ALS_own, FINALTRAIN 처방 다시 학습)', group=GRP[g], points=len(sel), points_with_track=int(cov.sum()),
                         exits=int(pc.sum()))
                for i, nm in enumerate(PATHS_KO):
                    r[f'exit_{nm}_pct'] = share(int(pc[:, i].sum()), int(pc.sum())); r[f'main_{nm}_pct'] = share(int((mp == i).sum()), int(cov.sum()))
                r['main_none_pct'] = share(int((mp < 0).sum()), int(cov.sum()))
                emp = fe >= 0; r['empty_by_30000_pct'] = share(int(emp.sum()), int(cov.sum()))
                r['first_empty_iteration_median'] = float(np.median(it[fe[emp]])) if emp.any() else None
                for lim in [1000, 3000, 7000, 15000]: r[f'empty_by_{lim}_pct'] = share(int((emp & (it[np.clip(fe, 0, None)] <= lim)).sum()), int(cov.sum()))
                track.append(r)
        print('TP6', stem, round(time.monotonic()-t0), flush=True)
    table('tp_front', front); table('tp_front_other', other); table('tp_height', height); table('tp_seed_fate', fate); table('tp_track', track)
    print('TP6_DONE', round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main()
