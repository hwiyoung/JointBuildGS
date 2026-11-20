"""5절 상자 MVS(세 실험 지역)에 방법 B(두 판)·C 를 캠퍼스와 같은 규약·같은 설정으로 적용 → 원통 none 과 같은 패치의 B_orig·B_view·C(+지워진 점만 _rm). 참값 읽지 않음. CPU.
방법 B: mf5 와 같은 wolff.cpp·같은 σ 규칙(그 상자의 patch_match.log, 영상마다 depth_max − depth_min 의 1 %)·t_v 원문 = 그 상자의 깊이 지도 수 × 7.5 %. 색 = 상자 영상(1400x1013)을 1024x741 로 줄임.
방법 C: mf6 와 같은 규칙(151동 중 상자 점이 닿는 건물마다 윤곽 + 5 m 안의 상자 점, 이웃 50, 1.0 배). 상자 점은 그 상자의 모든 유효 화소(같은 화소는 하나).
사용: mf10b_box_bc.py <지역> [...]   (mf10_box.py 가 먼저 none·A 를 낸 뒤)"""
import sys, subprocess
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
import mf10_box as MB
from mf10_box import GEO, A1, J3, BOXR, unproject_b, site_patches, cyl
from mfcommon import *
import mfcommon as MC
import cv2
from scipy.spatial import cKDTree
from matplotlib.path import Path as MPath
from mf6_stat import footprints
METHODS = ['B_orig', 'B_view', 'C']

def load(site):
    WSb = BOXR/f'box_{site}'; rows = poses(WSb/'sparse/images.bin'); names = sorted(rows)
    none = np.unpackbits(np.load(O/'masks'/f'box_{site}_none.npy'), axis=1, count=H*Wd).astype(bool).reshape(len(names), H, Wd)
    Zc = {}
    def depth(nm):
        if nm not in Zc:
            p = WSb/'stereo/depth_maps'/f'{nm}.geometric.bin'; Zc[nm] = read_depth(p) if p.exists() else np.zeros((H, Wd), np.float32)
        return Zc[nm]
    return WSb, rows, names, none, depth

def wolff(site, WSb, rows, names, none):
    cf = MC.cfg()['method_B_wolff2016']; tmp = O/'tmp'/f'wolff_box_{site}'; tmp.mkdir(parents=True, exist_ok=True); K = intrinsics()
    has = [(WSb/'stereo/depth_maps'/f'{nm}.geometric.bin').exists() for nm in names]
    rng_ = {}; cur = None
    for l in (WSb/'patch_match.log').read_text(errors='replace').splitlines():   # mf5 와 같은 읽기
        if 'Processing view' in l: cur = l.rsplit(' for ', 1)[1].split(' ===')[0].strip()
        elif 'depth_min:' in l and cur: rng_.setdefault(cur, {})['min'] = float(l.rsplit(':', 1)[1])
        elif 'depth_max:' in l and cur:
            e = rng_.setdefault(cur, {}); e.setdefault('max', float(l.rsplit(':', 1)[1])); cur = None
    sig = np.array([(rng_[n]['max'] - rng_[n]['min'])*.01 if h else 0. for n, h in zip(names, has)]); sig.tofile(tmp/'sigma.f64')
    cam = np.zeros((len(names), 12))
    for i, nm in enumerate(names): q, t = rows[nm]; cam[i, :9] = rotation(q).ravel(); cam[i, 9:] = t
    cam.tofile(tmp/'cams.bin')
    (tmp/'depths.txt').write_text('\n'.join(str(WSb/'stereo/depth_maps'/f'{nm}.geometric.bin') if h else '-' for nm, h in zip(names, has)) + '\n')
    cp = tmp/'colors.u8'
    with cp.open('wb') as f:
        for nm in names:
            im = cv2.imread(str(WSb/'images'/nm), cv2.IMREAD_COLOR); assert im is not None and im.shape[:2] == (1013, 1400), nm
            f.write(np.ascontiguousarray(cv2.resize(im, (Wd, H), interpolation=cv2.INTER_AREA)[..., ::-1]).tobytes())
    exe = O/'bin/wolff'; assert exe.exists(); tvo = sum(has)*0.075
    subprocess.run([str(exe), str(len(names)), str(Wd), str(H), *map(repr, [K['fx'], K['fy'], K['cx'], K['cy']]), str(tmp/'depths.txt'), str(cp), str(tmp/'cams.bin'), str(tmp/'sigma.f64'),
                    repr(cf['t_d_over_sigma']), repr(cf['t_p']), repr(tvo), str(tmp/'flags.u8'), str(tmp/'stats.txt'), os.environ.get('MF_CPUS', '16')], check=True)
    fl = np.fromfile(tmp/'flags.u8', dtype=np.uint8).reshape(len(names), H*Wd); nn = none.reshape(len(names), -1); assert np.array_equal(nn, (fl & 128) > 0)
    bo = (fl & 135) == 135; bv = (fl & 139) == 139; tot = int(nn.sum()); cnt = lambda b: int(((fl & b) == b).sum())
    save_mask(f'box_{site}_B_orig', bo.reshape(len(names), H, Wd)); save_mask(f'box_{site}_B_view', bv.reshape(len(names), H, Wd)); cp.unlink()
    rec = dict(at=now(), name=f'box_{site}', images=len(names), depth_maps=int(sum(has)), t_v_original=tvo, pixels_valid=tot,
               condition_pass_pct={'거리 (-t_d<d<0)': 100*cnt(129)/tot, '색 (p<t_p)': 100*cnt(130)/tot, 'v>t_v 원문': 100*cnt(132)/tot, 'v>t_v 시점': 100*cnt(136)/tot, '법선 없음': 100*cnt(144)/tot},
               B_orig_pct=100*float(bo.sum()/tot), B_view_pct=100*float(bv.sum()/tot), scientific_verdict=None)
    dump(O/'masks'/f'box_{site}_B.json', rec); print('WOLFF', site, rec['B_orig_pct'], rec['B_view_pct'], flush=True)
    return bo.reshape(len(names), H, Wd), bv.reshape(len(names), H, Wd)

def stat(site, rows, names, none, depth):
    cf = MC.cfg()['method_C_statistical']; k = cf['k']; sr = cf['std_ratio']; K = intrinsics(); FP = footprints()
    X = []; KEY = []
    for i, nm in enumerate(names):
        v = np.flatnonzero(none[i].ravel())
        if len(v): X.append(unproject_b(np.full(len(v), i), v, names, rows, K, depth)); KEY.append(i*(H*Wd) + v.astype(np.int64))
    X = np.concatenate(X); KEY = np.concatenate(KEY); x0, y0 = X[:, 0].min(), X[:, 1].min(); x1, y1 = X[:, 0].max(), X[:, 1].max()
    removed = []; REC = []
    for b, e in FP.items():
        bx = e['poly'].bounds
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1: continue
        m = np.flatnonzero((X[:, 0] >= bx[0]) & (X[:, 0] <= bx[2]) & (X[:, 1] >= bx[1]) & (X[:, 1] <= bx[3]))
        if not len(m): continue
        inside = np.zeros(len(m), bool)
        for g in (list(e['poly'].geoms) if hasattr(e['poly'], 'geoms') else [e['poly']]):
            mm = MPath(np.asarray(g.exterior.coords)).contains_points(X[m, :2])
            for h in g.interiors: mm &= ~MPath(np.asarray(h.coords)).contains_points(X[m, :2])
            inside |= mm
        m = m[inside]; x = X[m].astype(np.float64)
        if len(x) <= k: REC.append(dict(building=b, points=int(len(x)), removed=0)); continue
        tree = cKDTree(x); md = np.empty(len(x))
        for s in range(0, len(x), 1_000_000):
            dd, _ = tree.query(x[s:s+1_000_000], k=k + 1, workers=int(os.environ.get('MF_CPUS', '8'))); md[s:s+1_000_000] = dd[:, 1:].mean(1)
        mu, sd = md.mean(), md.std(); out = md > mu + sr*sd; removed.append(KEY[m[out]])
        REC.append(dict(building=b, points=int(len(x)), removed=int(out.sum()), mean_m=float(mu), std_m=float(sd), threshold_m=float(mu + sr*sd)))
    rem = np.unique(np.concatenate(removed)) if removed else np.empty(0, np.int64)
    mC = none.reshape(-1).copy(); assert mC[rem].all(); mC[rem] = False; mC = mC.reshape(none.shape); save_mask(f'box_{site}_C', mC)
    rec = dict(at=now(), name=f'box_{site}', k=k, std_ratio=sr, buildings_touched=len(REC), box_points=int(len(X)), pixels_removed=int(len(rem)), removed_pct=100*len(rem)/int(none.sum()), per_building=REC, scientific_verdict=None)
    dump(O/'masks'/f'box_{site}_C.json', rec); print('STAT_C', site, rec['pixels_removed'], rec['removed_pct'], flush=True)
    return mC

def run(site):
    T = Timer(); WSb, rows, names, none, depth = load(site)
    M = {}
    M['B_orig'], M['B_view'] = wolff(site, WSb, rows, names, none); T.mark('wolff')
    M['C'] = stat(site, rows, names, none, depth); T.mark('stat')
    K = intrinsics(); FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'; GEO.BASE.mkdir(parents=True, exist_ok=True)
    if not (GEO.BASE/'cylinders').exists(): GEO.build()
    out = dict(site=site, priors={})
    for prior in ['LoD2', 'ALS']:
        sc = {nm: ext for nm, ext, _ in J3.scenes(prior)}
        if site not in sc: out['priors'][prior] = 'scene not in JC figure 1'; continue
        ext = sc[site]; d = A1.load(prior); idx, C, Nn, kind = site_patches(prior, ext, d)
        z0 = np.load(O/'box'/f'{site}__{prior}.npz'); assert np.array_equal(z0['idx'], idx)
        lo = [ext[0] - 3, ext[1] + 3, ext[2] - 3, ext[3] + 3]; X = []; S = {m: [] for m in METHODS}
        for i, nm in enumerate(names):   # mf10_box.run_site 와 같은 점 고르기
            v = np.flatnonzero(none[i].ravel())
            if not len(v): continue
            x = unproject_b(np.full(len(v), i), v, names, rows, K, depth); kk = (x[:, 0] >= lo[0]) & (x[:, 0] <= lo[1]) & (x[:, 1] >= lo[2]) & (x[:, 1] <= lo[3])
            X.append(x[kk])
            for m in METHODS: S[m].append(M[m][i].ravel()[v[kk]])
        X = np.concatenate(X); rec = {}
        for m in METHODS:
            s = np.concatenate(S[m]); res = {}
            for tag, mk in [(m, s), (f'{m}_rm', ~s)]:
                tmp = FAST/f'pts_box_{site}_{tag}.npy'; np.save(tmp, X[mk]); res[tag] = cyl(tmp, prior, C, Nn, kind, f'{site}_{tag}'); tmp.unlink()
            r0 = z0['none__raw_n']; v = r0 >= 0; eq = int((r0[v] == res[m]['raw_n'][v] + res[f'{m}_rm']['raw_n'][v]).sum())
            np.savez(O/'box'/f'{site}__{prior}__{m}.npz', idx=idx, **{f'{t}__{k_}': a for t in res for k_, a in res[t].items()})
            rec[m] = dict(box_points=int(len(X)), box_points_survived=int(s.sum()), check2_patches=int(v.sum()), check2_equal=eq, raw_n_le_none=bool((res[m]['raw_n'][v] <= r0[v]).all()))
        out['priors'][prior] = rec; T.mark(prior)
    out.update(seconds=T.s(), marks=T.marks, GT_read_for_filtering=False, scientific_verdict=None); dump(O/'box'/f'{site}__BC.json', out)
    print('BOXBC', site, json.dumps(jsafe(out['priors']), ensure_ascii=False), round(T.s()), flush=True)

def main(sites):
    MC.cfg()
    for s in sites:
        if not (O/'box'/f'{s}__BC.json').exists(): run(s)
    MB.table(sites); MC.progress(f'mf10b 상자 MVS B·C {sites} 끝')

if __name__ == '__main__': main(sys.argv[1:])
