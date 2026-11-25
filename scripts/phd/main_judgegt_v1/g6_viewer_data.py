"""3차원 보기 자료(학습 없음, 저장된 값만 읽음). 그림 2~4의 본보기 자리마다 한 장면:
  범위 = 본보기 패치 기준점 XY ± 5 m, Z ± 12 m. 드론 LiDAR 참값 점·영상 깊이 점(구역 점 파일; 참값 점은 모두, 영상 깊이 점은 25만 개 넘으면 무작위로 줄임, 시드 고정),
  그 사전 정보의 정방향 패치(면 위 자리 = 중심 + 사전 정보 높이 × 법선, 칸 축 tangent1) + 패치 값.
나오는 것: /out/viewer/data/<장면>.json(패치·장면 정보), <장면>_gt.bin·_mvs.bin(Float32 xyz, 장면 원점 기준), scenes.json. 사용: GT_STAGE=ga g6_viewer_data.py"""
from common import *
import pandas as pd
from scipy.spatial import cKDTree
HALF, ZH, CAP = 5.0, 12.0, 250_000
def tile_box(t, kind, box):
    X = np.load(WI/'points'/t/('gt_xyz.npy' if kind == 'gt' else 'mvs_a_xyz.npy'), mmap_mode='r'); out = []
    for s in range(0, len(X), 20_000_000):
        q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= box[0]) & (q[:, 0] <= box[1]) & (q[:, 1] >= box[2]) & (q[:, 1] <= box[3]) & (q[:, 2] >= box[4]) & (q[:, 2] <= box[5]); out.append(q[m])
    return np.concatenate(out)
def main():
    c = cfg(); rng = np.random.default_rng(c['seed']); V = O/'viewer/data'; V.mkdir(parents=True, exist_ok=True); FD = D/'figures'
    scenes = []
    for f in sorted(FD.glob('fig[234]_*.json')):
        m = json.loads(f.read_text())
        nn = -1
        for k, e in enumerate(m['examples']):
            if e is None: continue
            nn += 1; prior = e.get('prior_name') or m['prior']; pick = m['picks'][k] if len(m['picks']) == len(m['examples']) else m['picks'][nn]
            scenes.append(dict(fig=f.stem, k=k, prior=prior, e=e, pick=pick))
    by_tile = {}
    for s in scenes: by_tile.setdefault(s['e']['tile'], []).append(s)
    F = {p: pd.read_csv(O/f'forward_{p}_{STAGE}.csv.gz') for p in PRIORS}
    G = {p: loadz(inp('patches', prior=p), ['centre', 'normal', 'tangent1', 'prior_height_m']) for p in PRIORS}
    SURF = {}
    for p in PRIORS:
        i = F[p].patch_index.values; g = G[p]; s = g['centre'][i] + np.nan_to_num(g['prior_height_m'][i])[:, None]*np.nan_to_num(g['normal'][i]); SURF[p] = (s, cKDTree(s[:, :2]))
    index = []
    for t, ss in by_tile.items():
        R = np.array([s['e']['ref'] for s in ss]); lo = R.min(0) - [HALF, HALF, ZH]; hi = R.max(0) + [HALF, HALF, ZH]; box = (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
        P = {k: tile_box(t, k, box) for k in ['gt', 'mvs']}
        for s in ss:
            e = s['e']; ref = np.array(e['ref']); name = f"{s['fig']}_{s['k']:02d}"; o = np.round(ref, 1); info = dict(name=name, origin=o.tolist(), prior=s['prior'], fig=s['fig'], pick=s['pick'], example=e)
            for k in ['gt', 'mvs']:
                X = P[k]; m = (np.abs(X[:, 0] - ref[0]) <= HALF) & (np.abs(X[:, 1] - ref[1]) <= HALF) & (np.abs(X[:, 2] - ref[2]) <= ZH); X = X[m]; n0 = len(X)
                if k == 'mvs' and len(X) > CAP: X = X[np.sort(rng.choice(len(X), CAP, replace=False))]
                (X - o).astype('<f4').tofile(V/f'{name}_{k}.bin'); info[f'{k}_points'] = len(X); info[f'{k}_points_in_box'] = n0
            p = s['prior']; S, tr = SURF[p]; j = np.array(tr.query_ball_point(ref[:2], r=HALF*1.42), int); j = j[(np.abs(S[j, 0] - ref[0]) <= HALF) & (np.abs(S[j, 1] - ref[1]) <= HALF) & (np.abs(S[j, 2] - ref[2]) <= ZH)]
            f = F[p].iloc[j]; g = G[p]; ii = f.patch_index.values
            cols = ['patch_id', 'building', 'surface', 'place', 'answer', 'h_M_m', 'tau_m', 'gt_column', 'gt_band_prior', 'gt_band_image', 'image_cylinder', 'gt_clusters', 'initial_state', 'judgment_jc2', 'judgment_1122', 'area_m2']
            pt = {k: (f[k].round(4).tolist() if f[k].dtype.kind == 'f' else f[k].tolist()) for k in cols}
            pt['initial_state'] = [STATE[int(x)] for x in f.initial_state]; pt['surf'] = np.round(S[j] - o, 4).tolist(); pt['normal'] = np.round(g['normal'][ii], 5).tolist(); pt['t1'] = np.round(g['tangent1'][ii], 5).tolist()
            pt['clusters'] = [[[f[f'cl{q}_n'].iloc[r], round(f[f'cl{q}_median_m'].iloc[r], 3)] for q in range(1, 7) if np.isfinite(f[f'cl{q}_n'].iloc[r])] for r in range(len(f))]
            pt['h_M_m'] = [None if not np.isfinite(x) else x for x in f.h_M_m.round(4)]; pt['example'] = int(np.flatnonzero(f.patch_id.values == e['patch_id'])[0]) if (f.patch_id.values == e['patch_id']).any() else -1
            info['patches'] = pt; info['patch_count'] = len(f); dump(V/f'{name}.json', info)
            index.append(dict(name=name, fig=s['fig'], prior=p, answer=e['answer'], old=s['pick'].get('old'), surface=e['surface'], building=e['building'], place=e['place'], patches=len(f), gt=info['gt_points'], mvs=info['mvs_points']))
            print('SCENE', name, len(f), info['gt_points'], info['mvs_points'], flush=True)
    index.sort(key=lambda r: r['name'])
    dump(V/'scenes.json', dict(at=now(), stage=STAGE, half_m=HALF, z_half_m=ZH, mvs_point_cap=CAP, colours=c['colours'], scenes=index, scientific_verdict=None)); progress(f'3차원 보기 자료: 장면 {len(index)}개')
if __name__ == '__main__': main()
