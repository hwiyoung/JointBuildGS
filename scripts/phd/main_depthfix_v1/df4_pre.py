"""Order 4 + reply 1 §2: pre-training counts (no training, CPU). usage: df4_pre.py <stem>
GT is used here only to check what the switches do (order 9). GT depth buffer per view = TARGETPATH tp0_gtbuf (GTTARGET g1_maps rule).
'GT-occluded pixel' = a target pixel whose GT buffer is nearer than the target depth by > 0.5 m (GTTARGET gt_point_occlusion_margin_m).
'target right at a pixel' = |target depth − GT buffer| <= τ of the owner patch kind (roof / wall τ of the scene); pixels without GT buffer are counted apart.
writes /docs/tables/pre/<name>_<stem>.csv/json and /df/patchinfo/<stem>_rejudge.npz"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TP = PH/'main_targetpath_v1/PHD-MAIN-TARGETPATH-v1'; WT = PH/'main_wrongtarget_v1/PHD-MAIN-WRONGTARGET-v1'; TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'
MAPS = {'판 0': 'base', '판 1': 'ga', '판 2': 'ga_na', '판 3': 'ga_da', '판 4': 'ga_na_da'}
TK = [0, 1, 2, 3]
FOLD = D/'tables/pre'

def q(a, p): return float(np.quantile(a, p)) if len(a) else None

def pixels(stem, c, pi, tb):
    site, prior = stem.split('__'); roof, wall = tau_of(site, prior); ptau = np.where(tb['kind'] == 2, wall if prior == 'LoD2' else roof, roof)
    typ = pi['type']; ids = np.flatnonzero(tb['surface_exists']); mvsroot = S0/'fork_inputs/s61'/site/'maps'
    idx = json.loads((O/'maps/base/ga'/stem/'index.json').read_text())
    A = {k: np.zeros(5) for k in ['base_px', 'back', 'front10', 'back_right', 'front10_right', 'back_gt', 'front10_gt', 'front10_mvs_wrong', 'front10_mvs_gt']}
    B = dict(occ=0, occ_p0=0, occ_p1_disc_occ=0, occ_p1_disc_ok=0, occ_p1_background=0, occ_p1_none=0, occ_p1_zero=0,
             back_new_owner=0, back_new_right=0, back_new_gt=0, back_to_background=0, back_to_none=0)
    W = {m: {k: [0., 0, []] for k in TK} for m in MAPS}
    for j, (name, meta) in enumerate(idx['views'].items()):
        K = np.asarray(meta['K']); M = np.asarray(meta['W2C']); Cc = cam_centre(M)
        front = np.zeros(len(tb['area']), bool); front[ids] = ((Cc[None] - tb['target'][ids])*tb['normal'][ids]).sum(1) > 0
        zb = loadz(O/'maps/base/base'/stem/f'{name}.npz'); zg = loadz(O/'maps/base/ga'/stem/f'{name}.npz')
        gt = np.load(TP/'gtbuf'/site/f'{name}.npy'); gtv = np.isfinite(gt)
        mvs = np.load(mvsroot/'mvs'/f'{name}.npy'); mvalid = np.isfinite(mvs) & (mvs > 0)
        ob, og = zb['owner'], zg['owner']; hb, hg = ob >= 0, og >= 0
        tyb = np.where(hb, typ[np.maximum(ob, 0)], 4); tyb[hb & (tyb < 0)] = 4; tyg = np.where(hg, typ[np.maximum(og, 0)], 4); tyg[hg & (tyg < 0)] = 4
        taub = np.where(hb, ptau[np.maximum(ob, 0)], np.nan); taug = np.where(hg, ptau[np.maximum(og, 0)], np.nan)
        rb = gtv & hb & (np.abs(zb['depth'] - gt) <= taub); rg = gtv & hg & (np.abs(zg['depth'] - gt) <= taug)
        back = hb & ~front[np.maximum(ob, 0)]; f10 = zg['front_rule']
        def add(key, mask, ty): A[key] += np.bincount(ty[mask].astype(int), minlength=5)[:5]
        add('base_px', hb, tyb); add('back', back, tyb); add('front10', f10, tyg); add('back_right', back & rb, tyb); add('front10_right', f10 & rg, tyg)
        add('back_gt', back & gtv, tyb); add('front10_gt', f10 & gtv, tyg)
        add('front10_mvs_wrong', f10 & gtv & (np.abs(mvs - gt) > taug), tyg); add('front10_mvs_gt', f10 & gtv, tyg)
        occ = hb & gtv & (gt < zb['depth'] - .5); B['occ'] += int(occ.sum()); B['occ_p0'] += int((occ & (zb['weight'] > 0)).sum())
        g_occ = hg & gtv & (gt < zg['depth'] - .5)
        B['occ_p1_disc_occ'] += int((occ & g_occ & (zg['weight'] > 0)).sum()); B['occ_p1_disc_ok'] += int((occ & hg & ~g_occ & (zg['weight'] > 0)).sum())
        B['occ_p1_zero'] += int((occ & hg & (zg['weight'] == 0)).sum()); B['occ_p1_background'] += int((occ & ~hg & (zg['weight'] > 0)).sum()); B['occ_p1_none'] += int((occ & ~hg & (zg['weight'] == 0)).sum())
        B['back_new_owner'] += int((back & hg).sum()); B['back_new_right'] += int((back & rg).sum()); B['back_new_gt'] += int((back & hg & gtv).sum())
        B['back_to_background'] += int((back & ~hg & (zg['weight'] > 0)).sum()); B['back_to_none'] += int((back & ~hg & (zg['weight'] == 0)).sum())
        for m, v in MAPS.items():
            z = zb if v == 'base' else (zg if v == 'ga' else loadz(O/'maps/base'/v/stem/f'{name}.npz', ['weight', 'owner']))
            own = z['owner']; h = own >= 0; w = z['weight']; ty = np.where(h, typ[np.maximum(own, 0)], -1)
            for k in TK:
                mk = h & (w > 0) & (ty == k); W[m][k][0] += float(w[mk].sum()); W[m][k][1] += int(mk.sum()); W[m][k][2].append(w[mk][::13])
        if (j+1) % 60 == 0: print('PRE', stem, j+1, flush=True)
    rows = []
    for k in [0, 1, 2, 3, 4]:
        nm = TYPE_KO.get(k, '그 밖') if k < 4 else '목표 없음(종류 밖)'
        r = dict(stem=STEM_KO[stem], type=nm, target_pixels_p0=int(A['base_px'][k]))
        for key, lab in [('back', '뒷면'), ('front10', '10 m')]:
            r[f'{lab}_빠진_화소'] = int(A[key][k]); r[f'{lab}_빠진_비율_pct'] = 100*A[key][k]/A['base_px'][k] if A['base_px'][k] else None
            r[f'{lab}_빠진_가운데_참값_있음'] = int(A[f'{key}_gt'][k]); r[f'{lab}_빠진_가운데_목표_맞음_pct'] = 100*A[f'{key}_right'][k]/A[f'{key}_gt'][k] if A[f'{key}_gt'][k] else None
        r['10 m_빠진_가운데_영상깊이_틀림'] = int(A['front10_mvs_wrong'][k]); r['10 m_빠진_가운데_영상깊이_틀림_pct'] = 100*A['front10_mvs_wrong'][k]/A['front10_mvs_gt'][k] if A['front10_mvs_gt'][k] else None
        rows.append(r)
    tot = {key: A[key].sum() for key in A}
    rows.append(dict(stem=STEM_KO[stem], type='모두', target_pixels_p0=int(tot['base_px']), **{f'{lab}_빠진_화소': int(tot[key]) for key, lab in [('back', '뒷면'), ('front10', '10 m')]},
                     **{f'{lab}_빠진_비율_pct': 100*tot[key]/tot['base_px'] for key, lab in [('back', '뒷면'), ('front10', '10 m')]},
                     **{f'{lab}_빠진_가운데_참값_있음': int(tot[f'{key}_gt']) for key, lab in [('back', '뒷면'), ('front10', '10 m')]},
                     **{f'{lab}_빠진_가운데_목표_맞음_pct': (100*tot[f'{key}_right']/tot[f'{key}_gt'] if tot[f'{key}_gt'] else None) for key, lab in [('back', '뒷면'), ('front10', '10 m')]},
                     **{'10 m_빠진_가운데_영상깊이_틀림': int(tot['front10_mvs_wrong']), '10 m_빠진_가운데_영상깊이_틀림_pct': 100*tot['front10_mvs_wrong']/tot['front10_mvs_gt'] if tot['front10_mvs_gt'] else None}))
    table(f'ga_removed_{stem}', rows, FOLD)
    o = B['occ']; occ_row = dict(stem=STEM_KO[stem], gt_occluded_target_pixels_p0=o, p0_instructed_pct=100*B['occ_p0']/o if o else None,
        p1_still_occluded_disc_pct=100*B['occ_p1_disc_occ']/o if o else None, p1_new_visible_disc_pct=100*B['occ_p1_disc_ok']/o if o else None,
        p1_weight0_disc_pct=100*B['occ_p1_zero']/o if o else None, p1_image_depth_pct=100*B['occ_p1_background']/o if o else None, p1_nothing_pct=100*B['occ_p1_none']/o if o else None,
        p1_instructed_pct=100*(B['occ_p1_disc_occ']+B['occ_p1_disc_ok']+B['occ_p1_background'])/o if o else None)
    nb = int(A['back'].sum())
    back_row = dict(stem=STEM_KO[stem], back_removed=nb, new_owner_pct=100*B['back_new_owner']/nb if nb else None, new_owner_with_gt=B['back_new_gt'],
        new_owner_right_pct=100*B['back_new_right']/B['back_new_gt'] if B['back_new_gt'] else None, to_image_depth_pct=100*B['back_to_background']/nb if nb else None, to_nothing_pct=100*B['back_to_none']/nb if nb else None)
    table(f'ga_gt_occluded_{stem}', [occ_row], FOLD); table(f'ga_back_new_owner_{stem}', [back_row], FOLD)
    wrows = []
    for m in MAPS:
        for k in TK:
            s_ = np.concatenate(W[m][k][2]) if W[m][k][2] else np.zeros(0)
            wrows.append(dict(stem=STEM_KO[stem], arm=m, type=TYPE_KO[k], pixels=W[m][k][1], mean=W[m][k][0]/W[m][k][1] if W[m][k][1] else None,
                              q10=q(s_, .1), q25=q(s_, .25), q50=q(s_, .5), q75=q(s_, .75), q90=q(s_, .9), max=float(s_.max()) if len(s_) else None))
    table(f'weights_by_type_{stem}', wrows, FOLD)

def ra_counts(stem, c, pi, tb):
    site, prior = stem.split('__'); sp = pi['split']; A = pi['area']; typ = pi['type']; rows = []
    for fam, key, kap in [('κ 가정', 'c_kA', c['kappa'][prior]), ('κ 1', 'c_k1', 1.0)]:
        cc = pi[key][sp]; face_prior = cc >= .5; base_prior = typ[sp] == 2; ch = face_prior != base_prior
        r = dict(stem=STEM_KO[stem], kappa=fam, kappa_value=kap, patches=int(sp.sum()), area_m2=float(A[sp].sum()),
                 return_patches=int((typ[sp] == 2).sum()), image_patches=int((typ[sp] == 1).sum()),
                 c_q10=q(cc, .1), c_q50=q(cc, .5), c_q90=q(cc, .9), c_0_02_pct=100*float(np.mean(cc < .2)), c_02_05_pct=100*float(np.mean((cc >= .2) & (cc < .5))), c_05_1_pct=100*float(np.mean(cc >= .5)),
                 c_ge_05_pct=100*float(face_prior.mean()), seed_face_changed_patches=int(ch.sum()), seed_face_changed_area_m2=float(A[sp][ch].sum()),
                 changed_return_to_image=int((ch & base_prior).sum()), changed_image_to_prior=int((ch & ~base_prior).sum()))
        rows.append(r)
    table(f'ra_patches_{stem}', rows, FOLD)
    # GT points on split patches: is the face with the larger c right? (GT only for this check)
    w = loadz(WT/'points'/f'wt_{stem}.npz', ['point_id', 's_prior', 's_mvs', 'tau', 'case_id'])
    ra = loadz(TE/'addendum2/points'/f'ra_{stem}__own.npz', ['point_id', 'patch_raw']); assert np.array_equal(w['point_id'], ra['point_id'])
    pr = ra['patch_raw']; on = pr >= 0; onsp = np.zeros(len(pr), bool); onsp[on] = sp[pr[on]]
    pok = np.abs(w['s_prior']) <= w['tau']; mok = np.isfinite(w['s_mvs']) & (np.abs(w['s_mvs']) <= w['tau'])
    rows = []
    for fam, key in [('κ 가정', 'c_kA'), ('κ 1', 'c_k1')]:
        p = pr[onsp]; facep = pi[key][p] >= .5; basep = typ[p] == 2
        ok_c = np.where(facep, pok[onsp], mok[onsp]); ok_0 = np.where(basep, pok[onsp], mok[onsp])
        rows.append(dict(stem=STEM_KO[stem], kappa=fam, gt_points=int(onsp.sum()), gt_patches=int(len(np.unique(p))), larger_c_face_right_pct=100*float(ok_c.mean()) if len(p) else None,
                         p0_target_face_right_pct=100*float(ok_0.mean()) if len(p) else None, prior_right_pct=100*float(pok[onsp].mean()) if len(p) else None, image_right_pct=100*float(mok[onsp].mean()) if len(p) else None,
                         rule='맞음 = 그 면(사전 정보 면 / 영상 깊이 면)까지 참값 점의 법선 거리(addendum11 s_prior / s_mvs) ≤ τ'))
    table(f'ra_gt_face_{stem}', rows, FOLD)

def rejudge(stem, c, pi, tb):
    """reply 1 §2: campus vs scene image height, and the type if significance and magnitude are re-judged with scene heights (photo check not redone)."""
    site, prior = stem.split('__'); m = pi['joined']; A = pi['area']; typ = pi['type']; kind = pi['kind']; tau = pi['tau']
    mix = json.loads((NA5/'t12_mixture.json').read_text())['mixture'][prior]; T = np.where(kind == 2, mix['벽']['boundary_m'] if prior == 'LoD2' else np.nan, mix['지붕']['boundary_m'])
    dh = pi['scene_mvs_h'] - pi['campus_mvs_h']; both = m & np.isfinite(dh)
    rows = []
    for k in [0, 1, 2, 3]:
        mk = both & (typ == k); a = np.abs(dh[mk])
        rows.append(dict(stem=STEM_KO[stem], type=TYPE_KO[k], patches_both_heights=int(mk.sum()), area_m2=float(A[mk].sum()), abs_diff_median_m=q(a, .5), abs_diff_p90_m=q(a, .9),
                         over_tau_area_pct=100*float(A[mk][a > tau[mk]].sum()/A[mk].sum()) if mk.any() else None))
    table(f'height_campus_vs_scene_{stem}', rows, FOLD)
    # checks of the campus rule from the patch values
    L = pi['L_m']; dfc = pi['d_for_check']; geo = pi['campus_geometry']; cn = pi['campus_n']
    ck = m & (cn >= 4) & np.isfinite(L) & np.isfinite(dfc)
    sig_c = ck & (np.abs(dfc) > L); agree_sig = float(np.mean((geo[ck] == 1) == sig_c[ck])) if ck.any() else None
    big_c = np.abs(pi['d_m_campus']) >= T; sgm = m & pi['significant']; agree_big = float(np.mean(big_c[sgm] == pi['mix_large'][sgm])) if sgm.any() else None
    # re-judge with scene heights
    act = typ >= 0; n_s = tb['n']; ds = pi['d_scene']; okh = m & act & np.isfinite(ds) & (n_s >= 4) & np.isfinite(L)
    sig_s = okh & (np.abs(ds + pi['offset_check']) > L); big_s = okh & (np.abs(ds) >= T)
    ts = typ.copy()
    rj = okh & np.isin(typ, [0, 1, 2])
    ts[rj & sig_s & big_s] = np.where(pi['returned'][rj & sig_s & big_s], 2, 1)
    ts[rj & sig_s & ~big_s] = 0
    ts[rj & ~sig_s & pi['significant']] = 0
    ch = rj & (ts != typ)
    savez(O/'patchinfo'/f'{stem}_rejudge.npz', type_scene=ts, changed=ch, rejudged=rj, sig_scene=sig_s, big_scene=big_s)
    rows = []
    for a_ in [0, 1, 2]:
        for b_ in [0, 1, 2]:
            mk = rj & (typ == a_) & (ts == b_)
            rows.append(dict(stem=STEM_KO[stem], type_campus=TYPE_KO[a_], type_scene=TYPE_KO[b_], patches=int(mk.sum()), area_m2=float(A[mk].sum())))
    rows.append(dict(stem=STEM_KO[stem], type_campus='바뀜 합', type_scene='', patches=int(ch.sum()), area_m2=float(A[ch].sum()),
                     share_of_rejudged_area_pct=100*float(A[ch].sum()/A[rj].sum()) if rj.any() else None,
                     not_rejudged_no_scene_height=int((m & act & np.isin(typ, [0, 1, 2]) & ~okh).sum()),
                     check_campus_sig_rule_agree_pct=100*agree_sig if agree_sig is not None else None, check_campus_big_rule_agree_pct=100*agree_big if agree_big is not None else None,
                     rule='유의 = n≥4 · |d + (d_for_check − d_campus)| > L_m(캠퍼스 값), 큼 = |d| ≥ 혼합 경계(지붕/벽); 장면 d = 장면 영상 높이 − 장면 사전 정보 높이; 점검(combo_D)은 캠퍼스 값 그대로; 유의하지 않게 된 패치 = 가중 평균'))
    table(f'rejudge_scene_{stem}', rows, FOLD)

def main(stem):
    c = cfg(False); t0 = time.monotonic(); pi = loadz(O/'patchinfo'/f'{stem}.npz'); tb = loadz(O/'families/base/targets'/f'{stem}.npz')
    rejudge(stem, c, pi, tb); ra_counts(stem, c, pi, tb); pixels(stem, c, pi, tb)
    print('PRE_DONE', stem, round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main(sys.argv[1])
