"""덧붙임 4 5절: 건물별 3차원 뷰어(인터넷 없이 열리는 HTML 하나 = 건물 하나 x 사전 정보 하나). 학습 없음, 저장값만 읽음.
범위 = 그 건물 LoD2 다각형 XY 범위 + 10 m(자르지 않음, Z 모두). 점은 구역 점 파일의 100 m 칸(덤 구역 빼고)에서 모아 겹침 없음.
층: 사전 정보 면(LoD2 = 판단이 쓴 WIDEN0 lod2_mesh.npz 의 다각형 삼각형(캡 뺌), 반투명 회색 + 면 테두리 / 항공 LiDAR 원래 점 + 그 건물 als_shift_m, 회색 점), 판단 GT 패치(가2 정답 색, 솎지 않음),
영상 깊이 점(초록), 드론 LiDAR(검정). 점은 상한을 넘으면 무작위로 솎고(씨앗 고정) 비율을 화면에 적음. 50 MB 넘으면 둘로 나눔(아직 없음).
나오는 것: /docs/viewer/가2/<건물>_<사전 정보>.html (+ .json). 사용: g9_viewer2.py"""
from common import *
import pandas as pd, base64
VD = D/'viewer/가2'; CAPS = {'mvs': 1_500_000, 'gt': 1_000_000, 'als': 500_000}; PL = {'면 안쪽': 0, '면 경계': 1, '건물 가장자리': 2, '자리 없음': 3}
SHIFT = np.array([690953.0, 5336071.0, 604.0])
def earclip(P2):
    """단순 다각형(구멍 없음) 귀 자르기 -> 삼각형 번호 목록."""
    idx = list(range(len(P2))); A = 0.5*sum(P2[i-1][0]*P2[i][1] - P2[i][0]*P2[i-1][1] for i in range(len(P2)))
    if A < 0: idx = idx[::-1]
    tris = []; guard = 0
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    while len(idx) > 3 and guard < 10000:
        guard += 1; ok = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k-1], idx[k], idx[(k+1) % len(idx)]; a, b, c = P2[i0], P2[i1], P2[i2]
            if cross(a, b, c) <= 1e-12: continue
            if any(cross(a, b, P2[j]) >= 0 and cross(b, c, P2[j]) >= 0 and cross(c, a, P2[j]) >= 0 for j in idx if j not in (i0, i1, i2)): continue
            tris.append((i0, i1, i2)); idx.pop(k); ok = True; break
        if not ok: break
    if len(idx) == 3: tris.append(tuple(idx))
    return tris
def poly_tris(ext):
    X = np.array(ext[:-1] if np.allclose(ext[0], ext[-1]) else ext, float)
    if len(X) < 3: return X, []
    c = X.mean(0); _, _, vt = np.linalg.svd(X - c); e1, e2 = vt[0], vt[1]; P2 = [((x - c)@e1, (x - c)@e2) for x in X]; return X, earclip(P2)
def core_points(tiles, kind, box):
    out = []
    for t in tiles:
        x0, x1, y0, y1 = tile_core(t); f = WI/'points'/t/f'{kind}_xyz.npy'
        if not f.exists(): continue
        X = np.load(f, mmap_mode='r')
        for s in range(0, len(X), 20_000_000):
            q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= max(x0, box[0])) & (q[:, 0] < min(x1, box[1])) & (q[:, 1] >= max(y0, box[2])) & (q[:, 1] < min(y1, box[3])); out.append(q[m])
    return np.concatenate(out) if out else np.empty((0, 3))
def b64(a): return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
def quant(X, lo, ext):
    return np.clip(np.round((X - lo)/ext*65535), 0, 65535).astype('<u2')
def main():
    c = cfg(); rng = np.random.default_rng(c['ga2']['audit']['seed'] + 1); B = buildings('ga2'); VD.mkdir(parents=True, exist_ok=True); COL = c['colours']
    lod = {b['id']: b for b in json.loads((PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json').read_text())}
    three = (R/'src/apps/gs3d_4way_viewer/build/three.module.min.js').read_text(); tpl = (HERE/'viewer/building.html').read_text(); index = []
    F = {p: pd.read_csv(O/f'forward_{p}_ga2.csv.gz') for p in PRIORS}; G = {p: loadz(inp('patches', prior=p), ['centre', 'normal', 'tangent1', 'prior_height_m', 'tile', 'tiles']) for p in PRIORS}
    for bid, br in sorted(B.items()):
        L = lod[bid]; allv = np.array([v for s in L['surfaces'].values() for poly in s for v in poly['ext']], float) - SHIFT
        box = (allv[:, 0].min() - 10, allv[:, 0].max() + 10, allv[:, 1].min() - 10, allv[:, 1].max() + 10)
        tiles = sorted({t for t in G['LoD2']['tiles'] if (lambda r: r[0] < box[1] and r[1] > box[0] and r[2] < box[3] and r[3] > box[2])(tile_core(t))})
        pts = {k: core_points(tiles, k2, box) for k, k2 in [('mvs', 'mvs_a'), ('gt', 'gt'), ('als', 'als')]}
        site = SITES[br['experiment_sites'][0]]
        for prior in PRIORS:
            T = Timer(); f = F[prior][F[prior].building == bid]
            if not len(f): continue
            g = G[prior]; i = f.patch_index.values; nrm = g['normal'][i]; S = g['centre'][i] + np.nan_to_num(g['prior_height_m'][i])[:, None]*np.nan_to_num(nrm)
            layers = {'mvs': pts['mvs'], 'gt': pts['gt']}
            if prior == 'ALS': layers['als'] = pts['als'] + np.array(br['als_shift_m'])
            allp = np.concatenate([S] + [v for v in layers.values() if len(v)]); lo = allp.min(0) - .5; ext = allp.max(0) + .5 - lo; info = {}; data = {}
            for k, X in layers.items():
                n0 = len(X)
                if n0 > CAPS[k]: X = X[np.sort(rng.choice(n0, CAPS[k], replace=False))]
                data[k] = b64(quant(X, lo, ext)); info[k] = dict(total=n0, shown=len(X), ratio=len(X)/max(n0, 1))
            polys = []
            if prior == 'LoD2':   # 판단이 쓴 LoD2 메시(WIDEN0 prior_tiles/<구역>/lod2_mesh.npz, 지역 좌표·같은 높이 기준), 다각형 삼각형만(캡 뺌)
                best = None
                for t in tiles:
                    mf = WI/'prior_tiles'/t/'lod2_mesh.npz'
                    if not mf.exists(): continue
                    z = np.load(mf); bn = list(z['building_names'])
                    if bid not in bn: continue
                    sel = np.flatnonzero((z['tri_building'] == bn.index(bid)) & (np.arange(len(z['F'])) < int(z['n_poly_tris'])))
                    if best is None or len(sel) > len(best[1]): best = (t, sel, z['V'], z['F'], z['tri_surface'])
                if best is not None:
                    t_, sel, Vm, Fm, ts = best; Fs = Fm[sel]; used = np.unique(Fs); remap = -np.ones(len(Vm), int); remap[used] = np.arange(len(used))
                    ed = {}
                    for tri, sf in zip(Fs, ts[sel]):
                        for a_, b_ in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
                            k_ = (sf, min(a_, b_), max(a_, b_)); ed[k_] = ed.get(k_, 0) + 1
                    edges = [[int(remap[a_]), int(remap[b_])] for (sf, a_, b_), n_ in ed.items() if n_ == 1]
                    polys = dict(tile=t_, v=np.round(Vm[used] - lo, 3).tolist(), f=remap[Fs].tolist(), e=edges)
            ans = np.array([(FWD + [FWD_X]).index(a) for a in f.answer], np.uint8); t1 = g['tangent1'][i]; ptiles = sorted(set(f.patch_id.str.split(':').str[1]))
            P = dict(c=b64((S - lo).astype('<f4')), n=b64(np.round(np.nan_to_num(nrm)*127).astype('i1')), t1=b64(np.round(np.nan_to_num(t1)*127).astype('i1')), a=b64(ans),
                     hI=b64(f.h_I_m.values.astype('<f4')), nb0=b64(f.gt_band_prior.values.astype('<f4')), nbI=b64(f.gt_band_image.values.astype('<f4')), ncol=b64(f.gt_column.values.astype('<f4')),
                     tau=b64(f.tau_m.values.astype('<f4')), pl=b64(np.array([PL.get(x, 3) for x in f.place], np.uint8)), k=b64(f.kind.values.astype(np.uint8)), id=b64(f.patch_id.str.split(':').str[-1].astype(int).values.astype('<i4')), tl=b64(np.array([ptiles.index(x) for x in f.patch_id.str.split(':').str[1]], np.uint8)))
            bb = S if not polys else np.array(polys['v']) + lo; bl = np.r_[allv[:, :2].min(0), bb[:, 2].min()] - lo; bh = np.r_[allv[:, :2].max(0), bb[:, 2].max()] - lo
            meta = dict(view=dict(c=((bl + bh)/2).tolist(), bl=bl.tolist(), bh=bh.tolist(), span=float(max(bh[0] - bl[0], bh[1] - bl[1]) + 20), h=float(bh[2] - bl[2])), building=bid, site=site, prior=prior, prior_name=PN[prior], id_prefix=prior, patch_tiles=ptiles, lo=lo.tolist(), ext=ext.tolist(), shift=SHIFT.tolist(), patches=len(f),
                        answers=FWD + [FWD_X], colours=COL, places=list(PL), info=info, als_shift_m=br['als_shift_m'] if prior == 'ALS' else None, polys=(len(polys['f']) if polys else 0),
                        lod2_mesh_tile=(polys['tile'] if polys else None), tiles=tiles, area_by_answer={a: float(f.area_m2[f.answer == a].sum()) for a in FWD + [FWD_X]})
            html = tpl.replace('/*THREE*/', three).replace('/*META*/', json.dumps(meta, ensure_ascii=False)).replace('/*POLYS*/', json.dumps(polys)).replace('/*PATCHES*/', json.dumps(P)).replace('/*POINTS*/', json.dumps(data))
            name = f"{site.replace(' ', '')}_{bid.replace('DEBY_LOD2_', '')}_{prior}"; out = VD/f'{name}.html'; out.write_text(html); mb = out.stat().st_size/1e6
            if mb > c['ga2']['viewer']['size_limit_mb']: issue(f'뷰어 {name} {mb:.1f} MB > 50 MB (나누지 않음, 상한을 낮춰 다시 낼 것)')
            dump(VD/f'{name}.json', dict(at=now(), file=out.name, mb=mb, seconds=T.s(), **{k: v for k, v in meta.items() if k not in ['colours']}, scientific_verdict=None))
            index.append(dict(file=out.name, building=bid, site=site, prior=prior, patches=len(f), mb=round(mb, 1), **{f'{k}_shown_pct': round(100*v['ratio'], 1) for k, v in info.items()}))
            print('VIEW', name, len(f), round(mb, 1), flush=True)
    dump(VD/'index.json', dict(at=now(), files=index, scientific_verdict=None)); progress(f'뷰어 가2: HTML {len(index)}개')
if __name__ == '__main__': main()
