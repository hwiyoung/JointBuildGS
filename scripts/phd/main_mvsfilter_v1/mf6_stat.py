"""방법 C: 통계적 점군 걸러내기 (PCL StatisticalOutlierRemoval 예제 값: 이웃 50, 표준 편차 1.0배). 참고 줄. 참값 읽지 않음. CPU.
건물마다(151동, LoD2 GroundSurface 윤곽에 5 m 여유) 그 안의 지금 점(같은 화소의 점은 하나로)에 따로 적용:
  점마다 가까운 이웃 50개(자신 뺌)까지의 평균 거리 → 그 건물 점들의 평균 + 1.0 x 표준 편차를 넘으면 지움.
어느 건물에서라도 지워진 화소는 지움. 어느 건물 범위에도 들지 않는 화소는 지우지 않음(걸러내기 범위 밖).
사용: mf6_stat.py"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
from shapely import prepared
from matplotlib.path import Path as MPath
X0, Y0 = 690953., 5336071.

def footprints():
    rows = {r['building']: r for r in json.loads((JC/'stage0/buildings.json').read_text())['rows'] if str(r['in_scope']) == 'True'}
    lod = {b['id']: b for b in json.loads((W/'inputs/lod2_buildings.json').read_text())}
    out = {}
    for b, r in rows.items():
        s = lod[b]['surfaces']; s = eval(s) if isinstance(s, str) else s
        polys = [Polygon([(p[0]-X0, p[1]-Y0) for p in g['ext']]) for g in s.get('ground', [])]
        polys = [p.buffer(0) for p in polys if p.is_valid or p.buffer(0).area > 0]
        if not polys: continue
        out[b] = dict(poly=unary_union(polys).buffer(5.0), tiles=eval(r['tiles']) if isinstance(r['tiles'], str) else r['tiles'])
    return out

def main():
    cf = cfg()['method_C_statistical']; T = Timer(); FP = footprints(); k = cf['k']; sr = cf['std_ratio']
    tmp = O/'tmp/statC'; tmp.mkdir(parents=True, exist_ok=True)
    bytile = {}
    for b, e in FP.items():
        for t in e['tiles']: bytile.setdefault(t, []).append(b)
    parts = {b: [] for b in FP}
    for t, bs in bytile.items():
        P = WI/'points'/t; X = np.load(P/'mvs_a_xyz.npy', mmap_mode='r'); V = np.load(P/'mvs_a_view.npy', mmap_mode='r'); pix = np.load(O/'pixmap'/f'{t}.npy', mmap_mode='r')
        for s in range(0, len(V), 20_000_000):
            x = np.asarray(X[s:s+20_000_000]); v = np.asarray(V[s:s+20_000_000]); p = np.asarray(pix[s:s+20_000_000])
            for b in bs:
                x0, y0, x1, y1 = FP[b]['poly'].bounds; m = (x[:, 0] >= x0) & (x[:, 0] <= x1) & (x[:, 1] >= y0) & (x[:, 1] <= y1)
                if m.any(): parts[b].append((x[m], v[m].astype(np.int64)*(H*Wd) + p[m]))
        print('tile read', t, round(T.s()), flush=True)
    removed = []; REC = []
    for b, e in FP.items():
        if not parts[b]: REC.append(dict(building=b, points=0)); continue
        x = np.concatenate([q[0] for q in parts[b]]); key = np.concatenate([q[1] for q in parts[b]]); parts[b] = None
        key, first = np.unique(key, return_index=True); x = x[first]
        poly = e['poly']; inside = np.zeros(len(x), bool)
        geoms = list(poly.geoms) if hasattr(poly, 'geoms') else [poly]
        for g in geoms:
            path = MPath(np.asarray(g.exterior.coords)); m = path.contains_points(x[:, :2])
            for h in g.interiors: m &= ~MPath(np.asarray(h.coords)).contains_points(x[:, :2])
            inside |= m
        x = x[inside].astype(np.float64); key = key[inside]
        if len(x) <= k: REC.append(dict(building=b, points=int(len(x)), removed=0)); continue
        tree = cKDTree(x); md = np.empty(len(x))
        for s in range(0, len(x), 1_000_000):
            dd, _ = tree.query(x[s:s+1_000_000], k=k + 1, workers=int(os.environ.get('MF_CPUS', '8'))); md[s:s+1_000_000] = dd[:, 1:].mean(1)
        mu, sd = md.mean(), md.std(); out = md > mu + sr*sd
        removed.append(key[out]); REC.append(dict(building=b, points=int(len(x)), removed=int(out.sum()), mean_m=float(mu), std_m=float(sd), threshold_m=float(mu + sr*sd)))
        print('building', b, len(x), int(out.sum()), round(T.s()), flush=True)
    rem = np.unique(np.concatenate(removed)) if removed else np.empty(0, np.int64)
    none = load_mask('none').reshape(-1); assert none[rem].all()
    evaluated = np.zeros_like(none)
    mC = none.copy(); mC[rem] = False
    save_mask('C', mC.reshape(-1, H, Wd))
    rec = dict(at=now(), k=k, std_ratio=sr, buildings=len(FP), pixels_valid=int(none.sum()), pixels_removed=int(len(rem)), removed_pct=100*len(rem)/int(none.sum()),
               per_building=REC, seconds=T.s(), scientific_verdict=None)
    dump(O/'masks/C.json', rec); print('STAT_C', rec['pixels_removed'], rec['removed_pct'], flush=True)
    progress(f'mf6 방법 C 끝: 지운 화소 {len(rem):,} ({rec["removed_pct"]:.2f} % of 유효 화소), {round(T.s())} 초')

if __name__ == '__main__': main()
