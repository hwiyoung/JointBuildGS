"""5절 상자 MVS(세 실험 지역)의 살아남음 표 t5_survival_box (발주 5절 끝 줄). 걸러내기에는 참값을 쓰지 않음(참값은 τ 안 셈에만).
정의(issues.md): 상자 MVS = PREP-MEASURE mvs/box_<지역>(그 지역 학습 영상만 쓴 COLMAP 1단계). 패치·처음 상태·차이가 유의한 패치 = 캠퍼스 판(JUDGESTRUCT-v1)과 같음,
  지역 = JUDGECHECK-v2 그림 1 의 세 장면 범위(JS·7절 지도와 같음). 영상 깊이 점만 상자 MVS 의 화소마다 되투영한 점(WIDEN0 규약)으로 바꿈.
단계: 1) 방법 A 살아남은 화소(mf1 과 같은 규약·같은 fusion_survive, 검산 3 표본 1만) 2) 지역 범위 + 3 m 안 상자 점 3) 원통(JC 와 같은 cylinders) none·A 4) 표.
사용: mf10_box.py <지역> [<지역> ...]   (B0_b10 B173nb_b10 R1rep_b10); 표는 마지막에 모두 모아 씀."""
import sys, subprocess, importlib.util
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC
from mf1_surviveA import ply_xyz, vis_head
sys.path.insert(0, '/repo/scripts/phd/main_judgecheck_v2')   # JC 원통 모듈을 먼저(둘 다 'common' 이름을 씀)
_s = importlib.util.spec_from_file_location('jc_s1_geometry', '/repo/scripts/phd/main_judgecheck_v2/s1_geometry.py'); GEO = importlib.util.module_from_spec(_s); sys.modules['jc_s1_geometry'] = GEO; _s.loader.exec_module(GEO)
sys.path.remove('/repo/scripts/phd/main_judgecheck_v2'); sys.modules.pop('common', None); sys.modules.pop('inherit', None)
sys.path.insert(0, '/repo/scripts/phd/main_judgestruct_v1')
from jscommon import *
import a1_variants as A1
import js3_figs as J3
import pandas as pd
from mfcommon import *   # jscommon 의 O·cfg·D 등이 덮은 이름을 이 발주 것으로 되돌림 (SURF·STATE·PN·wq·JABL 은 jscommon 것 유지)
MLABEL = {'A': 'A', 'A2': 'A2 (세션 판)', 'B_orig': 'B-원문', 'B_view': 'B-시점 (세션이 정한 판)', 'C': 'C'}
BOXR = PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/mvs'

def survive(site):
    """방법 A 살아남은 화소. 반환: names, none(n,741,1024), A(n,741,1024), rec"""
    WSb = BOXR/f'box_{site}'; F = O/'fusion'/f'box_{site}'; assert json.loads((F/'fusion_receipt.json').read_text())['exit_code'] == 0
    rows = poses(WSb/'sparse/images.bin'); ids = image_ids(WSb/'sparse/images.bin'); names = sorted(rows)
    camp = poses(WS/'sparse/images.bin'); shared = [n for n in names if n in camp]; dpose = max([max(np.abs(np.array(rows[n][0]) - np.array(camp[n][0])).max(), np.abs(np.array(rows[n][1]) - np.array(camp[n][1])).max()) for n in shared] or [np.nan])
    print('POSE', site, len(names), 'shared', len(shared), 'max diff', dpose, flush=True); assert len(shared) and dpose < 1e-6, '상자 자세가 캠퍼스와 다른 좌표계'
    with (WSb/'sparse/cameras.bin').open('rb') as f:
        nc, = struct.unpack('<Q', f.read(8)); cid, model, iw, ih = struct.unpack('<iiQQ', f.read(24)); fx, fy, cx, cy = struct.unpack('<4d', f.read(32))
    Kc = (fx*1024/iw, fy*741/ih, cx*1024/iw, cy*741/ih)
    orders = {'images.bin 파일 차례': list(ids), 'image_id 차례': sorted(ids, key=lambda s: ids[s]), '이름 차례': sorted(ids)}
    n_f, X = ply_xyz(F/'fused.ply', 20000); V = vis_head(F/'fused.ply.vis', len(X)); Zc = {}
    def depth(nm):
        if nm not in Zc:
            p = WSb/'stereo/depth_maps'/f'{nm}.geometric.bin'; Zc[nm] = read_depth(p) if p.exists() else np.zeros((741, 1024), np.float32)
        return Zc[nm]
    test = {}
    for on, order in orders.items():
        ok = tot = 0
        for k in range(0, len(X), 40):
            for im in V[k]:
                nm = order[int(im)]; q, t = rows[nm]; Q = rotation(q)@X[k].astype(float) + np.array(t)
                c = int(round(Kc[0]*Q[0]/Q[2] + Kc[2])); r = int(round(Kc[1]*Q[1]/Q[2] + Kc[3])); tot += 1
                if 0 <= c < 1024 and 0 <= r < 741: z = depth(nm)[r, c]; ok += int(z > 0 and abs(z - Q[2]) <= .01*Q[2])
        test[on] = dict(entries=tot, matched=ok, pct=100*ok/max(tot, 1))
    best = max(test, key=lambda k: test[k]['pct']); order = orders[best]
    tmp = O/'tmp'/f'survA_box_{site}'; tmp.mkdir(parents=True, exist_ok=True); cam = np.zeros((len(order), 12))
    for i, nm in enumerate(order): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WSb/'stereo/depth_maps'/f'{nm}.geometric.bin') if (WSb/'stereo/depth_maps'/f'{nm}.geometric.bin').exists() else '-' for nm in order) + '\n')
    exe = O/'bin/fusion_survive'; assert exe.exists()
    tol = cfg()['method_A_colmap_stereo_fusion']['survival']['relative_depth_tol']
    subprocess.run([str(exe), str(F/'fused.ply'), str(F/'fused.ply.vis'), str(tmp/'cams.bin'), str(tmp/'depths.txt'), '1024', '741', *map(repr, Kc), str(tol), str(tmp/'mask.u8'), str(tmp/'stats.txt'), '997', str(tmp/'sample.bin')], check=True)
    st = dict(l.split(' ', 1) for l in (tmp/'stats.txt').read_text().splitlines())
    mk = np.fromfile(tmp/'mask.u8', dtype='u1').reshape(len(order), 741, 1024).astype(bool); pos = {nm: i for i, nm in enumerate(order)}; mA = mk[[pos[nm] for nm in names]]; del mk
    none = np.stack([(lambda z: np.isfinite(z) & (z > 0))(depth(nm)) for nm in names]); assert not (mA & ~none).any()
    save_mask(f'box_{site}_none', none); save_mask(f'box_{site}_A', mA)
    vp = none.reshape(len(names), -1).sum(1); sp = mA.reshape(len(names), -1).sum(1)
    smp = np.fromfile(tmp/'sample.bin', dtype=np.dtype([('k', '<u4'), ('im', '<u4'), ('r', '<u4'), ('c', '<u4'), ('x', '<f4'), ('y', '<f4'), ('z', '<f4')]))
    rs = np.random.default_rng(20261119); s = smp[np.sort(rs.choice(len(smp), min(10000, len(smp)), replace=False))]
    K = intrinsics(); Xp = unproject_b(np.array([names.index(order[int(i)]) for i in s['im']]), (s['r'].astype(np.int64)*1024 + s['c']), names, rows, K, depth)
    Xf = np.c_[s['x'], s['y'], s['z']].astype(float); dist = np.linalg.norm(Xp - Xf, axis=1)
    dep = np.array([(rotation(rows[order[int(i)]][0])@x + np.array(rows[order[int(i)]][1]))[2] for i, x in zip(s['im'], Xf)])
    chk3 = dict(sample=len(s), within_1pct=int((dist <= .01*dep).sum()), median_dist_m=float(np.median(dist)), max_ratio=float((dist/dep).max()))
    rec = dict(at=now(), name=f'box_{site}', workspace=str(WSb), fused_points=int(st['points']), stats=st, order_test=test, order_used=best, pose_max_abs_diff_vs_campus=float(dpose), images_shared_with_campus=len(shared), K_colmap=Kc, tol=tol,
               pixels_valid=int(vp.sum()), pixels_survived=int(sp.sum()), survived_pct=100*float(sp.sum()/vp.sum()),
               per_image=[dict(name=n_, valid=int(a), survived=int(b)) for n_, a, b in zip(names, vp, sp)], check3=chk3, scientific_verdict=None)
    dump(O/'masks'/f'box_{site}_A.json', rec); return names, rows, none, mA, depth, rec

def unproject_b(view, pix, names, rows, K, depth):
    """WIDEN0 규약(mfcommon.unproject 와 같은 식), 깊이는 상자 작업 공간."""
    fx, fy, cx, cy = K['fx'], K['fy'], K['cx'], K['cy']; out = np.empty((len(view), 3), np.float32)
    for v in np.unique(view):
        m = np.flatnonzero(view == v); name = names[int(v)]; z = depth(name)
        vv, uu = np.divmod(np.asarray(pix)[m].astype(np.int64), 1024); dd = z[vv, uu].astype(float)
        c = np.column_stack([(uu-cx)/fx*dd, (vv-cy)/fy*dd, dd]); _, Cm = cam_world(name, rows); out[m] = (c@Cm[:3, :3].T + Cm[:3, 3]).astype(np.float32)
    return out

def site_patches(prior, ext, d):
    """지역 범위 안 패치: (A1 차례 번호, 그 구역 geometry_raw 의 centre·normal·kind)"""
    ts = list(d['tiles']); idx = []; C = []; N = []; Kd = []
    for ti, t in enumerate(ts):
        m = np.flatnonzero(d['tile'] == ti); c = d['centre'][m]
        sel = (c[:, 0] >= ext[0]) & (c[:, 0] <= ext[1]) & (c[:, 1] >= ext[2]) & (c[:, 1] <= ext[3])
        if not sel.any(): continue
        g = loadz(JC/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'centre', 'normal', 'kind']); assert np.array_equal(g['patch_id'], d['patch_id'][m])
        idx.append(m[sel]); C.append(g['centre'][sel]); N.append(g['normal'][sel]); Kd.append(g['kind'][sel])
    return np.concatenate(idx), np.concatenate(C), np.concatenate(N), np.concatenate(Kd)

def cyl(tmp, prior, C, Nn, kind, tag):
    v = np.array(GEO.run(tmp, C, np.nan_to_num(Nn), [.075, .125], Path('/fast' if Path('/fast').is_dir() else O/'tmp')/f'cyl_box_{tag}_{prior}.bin'))
    ri = np.where((kind == 2) & (prior == 'LoD2'), 1, 0); hi = np.where(kind == 1, 1, 0); ii = np.arange(len(kind)); a = v[ii, hi, ri, :]
    bad = ~np.isfinite(Nn).all(1); n = a[:, 0].astype(int); raw = a[:, 6].astype(int); n[bad] = -1; raw[bad] = -1
    return dict(n=n, raw_n=raw, med=a[:, 2])

def run_site(site):
    T = Timer(); names, rows, none, mA, depth, rec = survive(site); T.mark('survive')
    K = intrinsics(); FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'
    GEO.BASE.mkdir(parents=True, exist_ok=True)
    if not (GEO.BASE/'cylinders').exists(): GEO.build()
    out = dict(site=site, survive=rec, priors={})
    for prior in ['LoD2', 'ALS']:
        sc = {nm: ext for nm, ext, _ in J3.scenes(prior)}
        if site not in sc: out['priors'][prior] = 'scene not in JC figure 1'; continue
        ext = sc[site]; d = A1.load(prior); idx, C, Nn, kind = site_patches(prior, ext, d)
        lo = [ext[0] - 3, ext[1] + 3, ext[2] - 3, ext[3] + 3]; X = []; S = []
        for i, nm in enumerate(names):
            v = np.flatnonzero(none[i].ravel())
            if not len(v): continue
            x = unproject_b(np.full(len(v), i), v, names, rows, K, depth); k = (x[:, 0] >= lo[0]) & (x[:, 0] <= lo[1]) & (x[:, 1] >= lo[2]) & (x[:, 1] <= lo[3])
            X.append(x[k]); S.append(mA[i].ravel()[v[k]])
        X = np.concatenate(X); S = np.concatenate(S); res = {}
        for tag, m in [('none', np.ones(len(X), bool)), ('A', S), ('A_rm', ~S)]:
            tmp = FAST/f'pts_box_{site}_{tag}.npy'; np.save(tmp, X[m]); res[tag] = cyl(tmp, prior, C, Nn, kind, f'{site}_{tag}'); tmp.unlink()
        v = res['none']['raw_n'] >= 0; chk2 = int((res['none']['raw_n'][v] == res['A']['raw_n'][v] + res['A_rm']['raw_n'][v]).sum())
        np.savez(O/'box'/f'{site}__{prior}.npz', idx=idx, **{f'{t}__{k}': a for t in res for k, a in res[t].items()})
        out['priors'][prior] = dict(patches=int(len(idx)), box_points=int(len(X)), box_points_survived=int(S.sum()), check2_patches=int(v.sum()), check2_equal=chk2, extent=list(map(float, ext)))
        T.mark(f'{prior}')
    out.update(seconds=T.s(), marks=T.marks, GT_read_for_filtering=False, scientific_verdict=None); dump(O/'box'/f'{site}.json', out)
    print('BOX', site, json.dumps(jsafe(out['priors']), ensure_ascii=False), round(T.s()), flush=True)

def table(sites):
    ROWS = []
    for prior in ['LoD2', 'ALS']:
        d = A1.load(prior); A = d['area']; pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int); sig = np.load(O/'judge'/prior/'patch_none.npz')['sig']
        gtp = d['gt_p']; taup = d['tau_p']
        for site in sites:
          f = O/'box'/f'{site}__{prior}.npz'
          if not f.exists(): continue
          z0 = np.load(f); ix = z0['idx']; a = A[ix]; r0 = z0['none__raw_n']; within = lambda med: np.isfinite(gtp[ix]) & np.isfinite(med) & (np.abs(med - gtp[ix]) <= taup[ix])
          w0 = within(z0['none__med']); few0 = (z0['none__n'] >= 0) & (z0['none__n'] < 4)
          for meth in ['A', 'A2', 'B_orig', 'B_view', 'C']:   # A 는 mf10_box, B·C 는 mf10b_box_bc
            fm = f if meth == 'A' else O/'box'/f'{site}__{prior}__{meth}.npz'
            if not fm.exists(): continue
            z = np.load(fm); assert np.array_equal(z['idx'], ix)
            w1 = within(z[f'{meth}__med']); few = (z[f'{meth}__n'] >= 0) & (z[f'{meth}__n'] < 4)
            with np.errstate(invalid='ignore', divide='ignore'): ratio = np.where(r0 > 0, z[f'{meth}__raw_n']/np.maximum(r0, 1), np.nan)
            for sn, kk in SURF[prior]:
                km = np.isin(d['kind'][ix], kk)
                for stn, stm in [(STATE[s_], pc[ix] == s_) for s_ in STATE_ORDER] + [('모두', np.ones(len(ix), bool))]:
                    mm = sig[ix] & km & stm; aa = a[mm].sum(); ok = mm & np.isfinite(ratio); wa = a[ok]
                    r = dict(prior=PN[prior], site=site, method=MLABEL.get(meth, meth), surface=sn, state=stn, patches=int(mm.sum()), area_m2=float(aa), box_lt4_before_area_pct=100*a[mm & few0].sum()/aa if aa else np.nan)
                    if ok.sum():
                        for qq in [.1, .5, .9]: r[f'survive_q{int(qq*100)}_pct'] = 100*wq(ratio[ok], wa, qq)
                        r['survive_mean_pct'] = 100*float(np.sum(ratio[ok]*wa)/wa.sum())
                    r['lt4_after_area_pct'] = 100*a[mm & few].sum()/aa if aa else np.nan
                    g_ = mm & np.isfinite(gtp[ix]); ag = a[g_].sum(); r['gt_area_m2'] = float(ag)
                    r['median_within_tau_before_pct'] = 100*a[g_ & w0].sum()/ag if ag else np.nan; r['median_within_tau_after_pct'] = 100*a[g_ & w1].sum()/ag if ag else np.nan
                    ROWS.append(r)
    S = pd.DataFrame(ROWS); T_ = Path('/docs/tables'); f1 = lambda v: '' if v is None or not np.isfinite(v) else f'{v:.1f}'
    S.to_csv(T_/'t5_survival_box.csv', index=False)
    (T_/'t5_survival_box.json').write_text(json.dumps(dict(rows=json.loads(S.to_json(orient='records', force_ascii=False)), scientific_verdict=None), ensure_ascii=False, indent=0))
    q = S[((S.prior == 'LoD2') & (S.surface == '모두')) | ((S.prior == '항공 LiDAR') & (S.surface == '지붕'))]
    L = ['# t5_survival_box', '', '5절 상자 MVS(세 실험 지역). 방법마다(A = COLMAP stereo_fusion 기본값, B-원문·B-시점 = Wolff 외 2016(B-시점은 세션이 정한 판), C = 통계적 걸러내기) 상자 작업 공간에서 돌려, 상자 MVS 의 화소마다 점이 살아남은 비율. 패치·처음 상태·차이가 유의한 패치 = 캠퍼스 판(JUDGESTRUCT-v1), '
         '지역 = JUDGECHECK-v2 그림 1 장면 범위. 상자 점 4개 미만 % 앞 = 상자 지금 점으로 이미 4개 미만이던 넓이. LoD2 = 지붕+벽, 항공 LiDAR = 지붕. 지붕·벽 나눔은 csv.', '', 'scientific_verdict: null', '',
         '| 사전 정보 | 지역 | 방법 | 처음 상태 | 패치 | 넓이 m² | 살아남은 비율 10·50·90 % / 평균 | 점 4개 미만 넓이 % 앞 → 뒤 | 중앙값 τ 안 넓이 % 앞 → 뒤 |', '|---|---|---|---|---|---|---|---|---|']
    for _, r in q.iterrows():
        L.append(f"| {r.prior} | {r.site} | {r.method} | {r.state} | {r.patches:,} | {r.area_m2:.1f} | {f1(r.get('survive_q10_pct'))} · {f1(r.get('survive_q50_pct'))} · {f1(r.get('survive_q90_pct'))} / {f1(r.get('survive_mean_pct'))} | "
                 f"{f1(r.box_lt4_before_area_pct)} → {f1(r.lt4_after_area_pct)} | {f1(r.median_within_tau_before_pct)} → {f1(r.median_within_tau_after_pct)} |")
    (T_/'t5_survival_box.md').write_text('\n'.join(L) + '\n'); print('\n'.join(L[:12]), flush=True)

def main(sites):
    MC.cfg(); (O/'box').mkdir(exist_ok=True)
    for s in sites:
        if not (O/'box'/f'{s}.json').exists(): run_site(s)
    table(sites); MC.progress(f'mf10 상자 MVS {sites} 끝')

if __name__ == '__main__': main(sys.argv[1:])
