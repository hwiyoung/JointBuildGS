"""방법마다 살아남은 점만으로 패치 값 다시 냄 (발주 6절 앞부분). 참값 읽지 않음. CPU.
구역마다: 점의 살아남음 = masks/<method>[영상, 화소] → 살아남은 점(키 차례 유지)만으로
  - 원통(JC s1_geometry 와 같은 cylinders.cpp, 같은 반지름·길이·면 찾기): n, n5, n10, mvs_mean/median/sd, raw_n(면 찾기 전 원통 안 모든 점)
  - 고리 u_M R1.5 (JC s1_ring = UNCERT 고리 커널, 같은 시드 규칙, 솎기는 살아남은 점의 키 앞부분)
none: 원통은 모두 다시 셈(저장 값과 같아야 함), u_M 은 JC 저장 값 + 재현 표본 200개.
사용: mf2_patch.py <method> <tile> [<tile> ...]   (<method>_rm = 그 방법이 지운 점만, 원통 수만 — 점검 2; MF_CYL_ONLY=1 이면 원통 값만)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC
sys.path.insert(0, '/repo/scripts/phd/main_judgecheck_v2')
import importlib.util
_s = importlib.util.spec_from_file_location('jc_s1_ring', '/repo/scripts/phd/main_judgecheck_v2/s1_ring.py'); RING = importlib.util.module_from_spec(_s); sys.modules['jc_s1_ring'] = RING; _s.loader.exec_module(RING)
_s = importlib.util.spec_from_file_location('jc_s1_geometry', '/repo/scripts/phd/main_judgecheck_v2/s1_geometry.py'); GEO = importlib.util.module_from_spec(_s); sys.modules['jc_s1_geometry'] = GEO; _s.loader.exec_module(GEO)
from scipy.spatial import cKDTree
K = RING.K

def survived(method, tile):
    P = WI/'points'/tile; V = np.load(P/'mvs_a_view.npy'); pix = np.load(O/'pixmap'/f'{tile}.npy'); assert len(V) == len(pix)
    if method == 'none': return np.ones(len(V), bool)
    if method.endswith('_rm'): return ~survived(method[:-3], tile)   # 점검 2: 지워진 점만(원통 수만 셈)
    M = np.load(O/'masks'/f'{method}.npy'); s = np.zeros(len(V), bool)   # 통째로 읽음(메모리 압박에서 메모리 맵 페이지가 밀려남)
    order = np.argsort(V, kind='stable'); Vs = V[order]; cuts = np.flatnonzero(np.diff(Vs)) + 1
    for seg in np.split(order, cuts):
        v = int(V[seg[0]]); row = np.unpackbits(M[v], count=H*Wd).astype(bool); s[seg] = row[pix[seg]]
    return s

def main(method, tile):
    MC.cfg(); T = Timer(); dest = O/'patch'/method/f'{tile}.npz'
    if dest.exists(): return
    lockf = dest.with_suffix('.lock'); lockf.parent.mkdir(parents=True, exist_ok=True)
    try: fd = os.open(lockf, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, now().encode()); os.close(fd)
    except FileExistsError: print('SKIP locked', method, tile, flush=True); return
    priors = [p for p in ['LoD2', 'ALS'] if (JC/'geometry_raw'/f'{tile}__{p}.npz').exists()]
    if not priors: return
    s = survived(method, tile); T.mark('survive')
    P = WI/'points'/tile; X = np.load(P/'mvs_a_xyz.npy'); Vw = np.load(P/'mvs_a_view.npy'); Kk = np.load(P/'mvs_a_key.npy')
    keep = np.flatnonzero(s); FAST = Path('/fast') if Path('/fast').is_dir() else O/'tmp'   # 점 임시 파일은 메모리(tmpfs)에: 원통 셈이 메모리 맵으로 되풀이해 읽음
    tmp = FAST/f'pts_{method}_{tile}.npy'; tmp.parent.mkdir(exist_ok=True, parents=True)
    Xk = X[keep]; del X; np.save(tmp, Xk)
    res = {}; rec = dict(at=now(), method=method, tile=tile, points=int(len(s)), survived=int(s.sum()))
    GEO.BASE.mkdir(parents=True, exist_ok=True)
    import shutil
    if not (GEO.BASE/'cylinders').exists():
        import fcntl
        with open(O/'tmp/cyl_build.lock', 'w') as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            if not (GEO.BASE/'cylinders').exists(): GEO.build()
    if FAST == Path('/fast') and not (FAST/'cylinders').exists(): shutil.copy2(GEO.BASE/'cylinders', FAST/'cylinders')   # 실행 파일도 메모리에
    if (FAST/'cylinders').exists(): GEO.BASE = FAST; GEO.scope['BASE'] = FAST   # run() 은 scope 의 BASE 를 씀
    for prior in priors:
        g = loadz(JC/'geometry_raw'/f'{tile}__{prior}.npz'); N = len(g['kind'])
        v = np.array(GEO.run(tmp, g['centre'], np.nan_to_num(g['normal']), [.075, .125], FAST/f'cyl_{method}_{tile}_{prior}.bin'))
        ri = np.where((g['kind'] == 2) & (prior == 'LoD2'), 1, 0); hi = np.where(g['kind'] == 1, 1, 0); ii = np.arange(N); a = v[ii, hi, ri, :]
        r = dict(patch_id=g['patch_id'], n=a[:, 0].astype(int), mvs_mean_m=a[:, 1], mvs_median_m=a[:, 2], mvs_sd_m=a[:, 3], raw_n=a[:, 6].astype(int),
                 n5=v[ii, 0, ri, 0].astype(int), n10=v[ii, 1, ri, 0].astype(int))
        bad = ~np.isfinite(g['normal']).all(1); r['n'][bad] = -1; r['n5'][bad] = -1; r['n10'][bad] = -1; r['raw_n'][bad] = -1
        if method == 'none':
            rec[f'{prior}_cyl_equal'] = dict(n=bool(np.array_equal(r['n'], g['n'])), n5=bool(np.array_equal(r['n5'], g['n5'])), n10=bool(np.array_equal(r['n10'], g['n10'])),
                                             mean=bool(np.array_equal(r['mvs_mean_m'], g['mvs_mean_m'], equal_nan=True)))
        res[prior] = r
        for f in FAST.glob(f'cyl_{method}_{tile}_{prior}.*'): f.unlink()
    T.mark('cylinders')
    if method.endswith('_rm') or os.environ.get('MF_CYL_ONLY') == '1':   # 회신 1 4절: 문턱을 줄인 A2 판은 원통 값만(판 '점검'에 n·raw_n 만 씀)
        tmp.unlink(); savez(dest, **{f'{p}__{k}': v for p in res for k, v in res[p].items()}, priors=np.array(priors))
        rec.update(seconds=T.s(), marks=T.marks, GT_read=False, scientific_verdict=None); dump(dest.with_suffix('.json'), rec); lockf.unlink(missing_ok=True); print('PATCH', json.dumps(jsafe(rec)), flush=True); return
    # 고리 u_M R1.5 (none: 저장 값 사용; MF_RING_REPRO=0 이면 재현 표본 생략 — 공용 메모리 한도 때문, issues.md)
    if method == 'none' and os.environ.get('MF_RING_REPRO', '1') == '0':
        for prior in priors:
            d = loadz(JC/'geometry_raw'/f'{tile}__{prior}.npz', ['kind', 'patch_id']); res[prior]['u_M'] = loadz(JC/'ring/base'/f'{tile}__{prior}.npz', ['u_mvs_R1p5'])['u_mvs_R1p5'].astype(float)
            rec[f'{prior}_ring_repro'] = 'skipped (MF_RING_REPRO=0)'; rec[f'{prior}_patches'] = len(d['kind'])
        tmp.unlink(); savez(dest, **{f'{p}__{k}': v for p in res for k, v in res[p].items()}, priors=np.array(priors))
        rec.update(seconds=T.s(), marks=T.marks, GT_read=False, scientific_verdict=None); dump(dest.with_suffix('.json'), rec); lockf.unlink(missing_ok=True); print('PATCH', json.dumps(jsafe(rec)), flush=True); return
    Xf = Xk.astype(np.float64); del Xk; K.G.clear(); K.G.update(X=Xf, V=Vw[keep], data='mvs_a', site=tile, gt=None)
    K.G['tree'] = cKDTree(Xf, leafsize=32, balanced_tree=False, compact_nodes=False); K.G['levels'] = {}; Kf = Kk[keep]
    for k in range(1, 6):
        n = int(np.searchsorted(Kf, 4.0 ** -k))
        if n < 1000: break
        K.G['levels'][k] = (n, cKDTree(Xf[:n], leafsize=32, balanced_tree=False, compact_nodes=False))
    T.mark('ring_setup')
    for prior in priors:
        d = loadz(JC/'geometry_raw'/f'{tile}__{prior}.npz'); N = len(d['kind'])
        pg = loadz(WI/'patch_geometry'/f'{tile}_{prior}.npz', ['patch_id']); pos = {q: i for i, q in enumerate(pg['patch_id'])}
        d['widen0_index'] = np.array([pos[q] for q in d['patch_id']], np.int64)
        ok = d['normal_defined'] & np.isfinite(d['old_normal']).all(1); stored = loadz(JC/'ring/base'/f'{tile}__{prior}.npz', ['u_mvs_R1p5'])['u_mvs_R1p5'].astype(float)
        if method == 'none':
            rng = np.random.default_rng([20261119, tiles().index(tile), 0 if prior == 'LoD2' else 1]); ids = np.sort(rng.choice(np.flatnonzero(ok), min(200, int(ok.sum())), replace=False))
        else: ids = np.flatnonzero(ok)
        o, sec = RING.compute(d, prior, 'mvs_a', [1.5], ids, f'{method}:{tile}:{prior}')
        if method == 'none':
            rep = o[1.5]['u'][ids]; eq = int(np.sum((rep.astype(np.float32) == stored[ids].astype(np.float32)) | (~np.isfinite(rep) & ~np.isfinite(stored[ids]))))
            res[prior]['u_M'] = stored; rec[f'{prior}_ring_repro'] = dict(n=len(ids), equal=eq)
        else:
            res[prior]['u_M'] = o[1.5]['u']; res[prior]['ring_status'] = o[1.5]['status']
        rec[f'{prior}_ring_seconds'] = sec; rec[f'{prior}_patches'] = N
    K.G.clear(); tmp.unlink()
    savez(dest, **{f'{p}__{k}': v for p in res for k, v in res[p].items()}, priors=np.array(priors))
    rec.update(seconds=T.s(), marks=T.marks, GT_read=False, scientific_verdict=None); dump(dest.with_suffix('.json'), rec); lockf.unlink(missing_ok=True); print('PATCH', json.dumps(jsafe(rec)), flush=True)

if __name__ == '__main__':
    for t in sys.argv[2:]: main(sys.argv[1], t)
