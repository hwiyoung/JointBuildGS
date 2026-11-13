"""확인 5 (다) 모임마다 '밝기가 포화된 화소의 비율'. 앞선 작업에 정의가 없어 새로 정함(issues.md 한 줄):
광도 일관성 검사 조각(사진 준비의 두 평면, 0.5 m 정사각 25×25 표본, 남긴 화소 mask, 높이 0)을 고른 학습 영상마다 원래 해상도 RGB 영상에 투영하고,
가장 가까운 화소의 세 채널 가운데 하나라도 255인 표본을 포화로 센다. 조각 네 모서리와 모든 표본이 영상 안이고 남긴 화소가 313개 이상인 영상만 센다(광도 점수와 같은 조건).
모임의 사진 점 = 모임 구성원(참값 점 모임은 짝 패치, 패치 모임은 패치; analysis/clusters.csv 에 저장한 구성원: 참값 점 5,000개·패치 3,000개까지)의 사진 점.
모임 값 = 100 × 포화 표본 수 합 / 남긴 표본 수 합. 1 m² 이상 모임만. 영상은 한 장에 한 번 읽는다. 참값은 모임 구성원을 고르는 데만 쓰였다(모임 자체가 참값으로 만든 것).
  s7_saturation.py -> analysis/cluster_saturation.csv, analysis/clusters.csv 의 saturated_pct 칸, tables/c5_clusters 다시 씀"""
from common import *
import pandas as pd, cv2, zipfile
sys.path.insert(0, str(HERE/'inherited'))
import photo_cameras as PCM
from photo_cameras import Cameras
from s7_tables import write
OFF = np.stack(np.meshgrid(np.arange(25)*.02-.24, np.arange(25)*.02-.24, indexing='xy'), -1).reshape(625, 2)
CORNER = np.array([[-.25, -.25], [.25, -.25], [.25, .25], [-.25, .25]])
def main():
    cfg(); T = Timer(); cam = Cameras(); C = pd.read_csv(O/'analysis/clusters.csv', low_memory=False)
    big = C[C['size'] == '1 m2 이상']; members = {}; need = {}
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz', ['patch_id']); pmap = {}
        for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            t = p.stem.split('__')[0]; pp = O/'photo_prepared'/f'{t}.npz'
            if not pp.exists(): continue
            g = loadz(p, ['patch_id']); grp = loadz(O/'photo_groups'/f'{t}__{prior}.npz', ['patch_point'])['patch_point']
            q = loadz(pp, ['prior', 'source_index']); m = np.flatnonzero(q['prior'] == prior)
            if not len(m): continue
            inv = np.full(int(max(grp.max(), q['source_index'][m].max())) + 1, -1, np.int64); inv[q['source_index'][m]] = m
            rows = np.where(grp >= 0, inv[np.maximum(grp, 0)], -1)
            for s, r in zip(g['patch_id'], rows):
                if r >= 0: pmap[s] = (t, int(r))
        for r in big[big.prior == prior].itertuples(index=False):
            if r.cluster_source == '참값 점':
                mem = np.array([int(x) for x in str(r.member_rows).split(',') if x not in ('', 'nan')], np.int64); pids = set(d['patch_id'][mem].tolist()) if len(mem) else set()
            else: pids = set(x for x in str(r.member_patches).split(',') if x not in ('', 'nan'))
            pts = sorted({pmap[s] for s in pids if s in pmap}); members[(prior, int(r.cluster_id))] = pts
            for t, row in pts: need.setdefault(t, set()).add(row)
    print('SAT_NEED', sum(len(v) for v in need.values()), 'points', len(members), 'clusters', round(T.mark('map')), flush=True)
    # 할 일: (구역, 점, 평면, 영상, mask 행)
    tasks = []; geo = {}
    for t, rows in need.items():
        rows = np.array(sorted(rows)); g = loadz(O/'photo_prepared'/f'{t}.npz', ['centres', 'normals', 'tangent1', 'tangent2', 'selected_images', 'available', 'row_plane', 'row_height', 'plane_row_ptr', 'mask_bits'])
        geo[t] = g; ptr = g['plane_row_ptr']; sel = g['selected_images']; av = g['available']
        for n in rows:
            for k in range(2):
                if not av[n, k]: continue
                pi = 2*n + k; rr = [x for x in range(ptr[pi], ptr[pi+1]) if g['row_height'][x] == 0]
                if not rr: continue
                for j in sel[n, k]:
                    if j >= 0: tasks.append((t, int(n), k, int(j), rr[0]))
    print('SAT_TASKS', len(tasks), round(T.mark('tasks')), flush=True)
    acc = {}; zf = zipfile.ZipFile(PCM.RAW/'raw/uav/Images.zip'); by_cam = {}
    for i, x in enumerate(tasks): by_cam.setdefault(x[3], []).append(i)
    for ci, (j, idx) in enumerate(sorted(by_cam.items())):
        im = cv2.imdecode(np.frombuffer(zf.read(cam.members[j]), np.uint8), cv2.IMREAD_COLOR); assert im.shape[:2] == (cam.h, cam.w)
        satimg = (im == 255).any(-1); del im
        for b in range(0, len(idx), 4000):
            sub = [tasks[i] for i in idx[b:b+4000]]
            c = np.array([geo[t]['centres'][n, k] for t, n, k, _, _ in sub], float); a = np.array([geo[t]['tangent1'][n, k] for t, n, k, _, _ in sub], float); e = np.array([geo[t]['tangent2'][n, k] for t, n, k, _, _ in sub], float)
            mask = np.unpackbits(np.stack([geo[t]['mask_bits'][rr] for t, _, _, _, rr in sub]), axis=1, count=625).astype(bool)
            X = c[:, None] + OFF[None, :, 0, None]*a[:, None] + OFF[None, :, 1, None]*e[:, None]; uv, z, ok = cam.project(X, j)
            Xc = c[:, None] + CORNER[None, :, 0, None]*a[:, None] + CORNER[None, :, 1, None]*e[:, None]; cuv, cz, cok = cam.project(Xc, j)
            good = cok.all(1) & (cuv[..., 0] >= 0).all(1) & (cuv[..., 0] < cam.w - 1).all(1) & (cuv[..., 1] >= 0).all(1) & (cuv[..., 1] < cam.h - 1).all(1) & ok.all(1)
            good &= (uv[..., 0] >= 0).all(1) & (uv[..., 0] <= cam.w - 1).all(1) & (uv[..., 1] >= 0).all(1) & (uv[..., 1] <= cam.h - 1).all(1) & (mask.sum(1) >= 313)
            ix = np.clip(np.rint(np.nan_to_num(uv[..., 0])), 0, cam.w - 1).astype(np.int64); iy = np.clip(np.rint(np.nan_to_num(uv[..., 1])), 0, cam.h - 1).astype(np.int64)
            sat = satimg[iy, ix] & mask
            for (t, n, k, _, _), gd, s_, m_ in zip(sub, good, sat.sum(1), mask.sum(1)):
                if not gd: continue
                v = acc.setdefault((t, n), [0, 0, 0]); v[0] += int(s_); v[1] += int(m_); v[2] += 1
        if ci % 50 == 0: print('SAT_CAM', ci + 1, len(by_cam), round(T.mark('cam')), flush=True)
    out = []
    for (prior, cid), pts in members.items():
        s = sum(acc.get(p, [0, 0, 0])[0] for p in pts); r = sum(acc.get(p, [0, 0, 0])[1] for p in pts); v = sum(acc.get(p, [0, 0, 0])[2] for p in pts)
        out.append(dict(cluster_id=cid, prior=prior, photo_points=len(pts), photo_points_with_view=sum(1 for p in pts if acc.get(p, [0, 0, 0])[2] > 0), views=v, retained_samples=r, saturated_samples=s, saturated_pct=100*s/r if r else np.nan))
    S = pd.DataFrame(out); S.to_csv(O/'analysis/cluster_saturation.csv', index=False)
    key = dict(zip(zip(S.prior, S.cluster_id), S.saturated_pct)); C['saturated_pct'] = [key.get((p, int(c)), np.nan) for p, c in zip(C.prior, C.cluster_id)]
    tmp = O/'analysis/clusters.csv.tmp'; C.to_csv(tmp, index=False); os.replace(tmp, O/'analysis/clusters.csv')
    write('c5_clusters', C.drop(columns=['member_rows', 'member_patches'], errors='ignore'), note='모임마다의 사실(원인 이름 없음). 1 m2 미만은 size 열로 구분. saturated_pct = s7_saturation.py(밝기 포화 표본 비율).', md_rows=lambda x: x[x['size'] == '1 m2 이상'].sort_values('area_m2', ascending=False).head(20),
          md_cols=['cluster_id', 'prior', 'cluster_source', 'building', 'area_m2', 'gt_kind', 'geometry_type', 'prior_state', 'image_state', 's_P_median_m', 's_M_median_m'])
    dump(O/'analysis/cluster_saturation.json', dict(at=now(), clusters=len(S), with_value=int(S.saturated_pct.notna().sum()), tasks=len(tasks), cameras=len(by_cam), seconds=T.mark('end'), rule=__doc__, scientific_verdict=None))
    print('SAT_DONE', len(S), int(S.saturated_pct.notna().sum()), flush=True)
if __name__ == '__main__': main()
