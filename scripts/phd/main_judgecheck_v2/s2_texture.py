"""무늬 없음 (발주 2.4, GTJUDGE-v1 preservation.py:37-54 규칙을 패치 중심에). 참값 쓰지 않음.
학습 영상(WIDEN0 819장) 가운데 패치 중심(c + h_P n)에서 카메라를 향한 시선이 위쪽(p0 checkpoint 030 gravity up)과 20 도 안인 영상,
원본 해상도 투영 [1, w-1) x [1, h-1), PIL 회색/255 의 np.gradient 크기 < 0.02137(p0 W3 texture_gradient_low_max)이면 낮음.
낮은 영상 수 x 2 >= 본 영상 수 이고 본 영상이 있으면 무늬 없음. 본 영상이 없으면 확인 불가(-1)."""
from common import *
from scipy.spatial import cKDTree
from PIL import Image
import io, zipfile, csv
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras
def main():
    cfg(); T = Timer(); cam = Cameras()
    up = np.array(json.loads((PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json').read_text())['payload']['gravity']['up']); up /= np.linalg.norm(up)
    tf = R/'docs/evidence/p0-audit/w3-quality-integration/tables/W3_failure_surface_cause_thresholds.csv'
    with tf.open() as f: thr = float(next(x for x in csv.DictReader(f) if x['threshold'] == 'texture_gradient_low_max')['value'])
    files = sorted((O/'geometry_raw').glob('*__*.npz')); parts = []; offs = []; n0 = 0
    for p in files:
        g = loadz(p, ['centre', 'normal', 'prior_height_m'])
        q = g['centre'] + np.nan_to_num(g['prior_height_m'])[:, None]*np.nan_to_num(g['normal']); ok = np.isfinite(g['normal']).all(1) & np.isfinite(g['prior_height_m'])
        q[~ok] = g['centre'][~ok]; parts.append(q); offs.append((p.name, n0, n0 + len(q))); n0 += len(q)
    Q = np.concatenate(parts); N = len(Q); low = np.zeros(N, np.int32); seen = np.zeros(N, np.int32); best = np.full(N, -1, np.int32); bestcos = np.full(N, -1.)
    xy = cKDTree(Q[:, :2]); zmin = Q[:, 2].min(); c20 = np.cos(np.deg2rad(20.)); used = 0
    z = zipfile.ZipFile(PH.parent/'p0-audit/data/raw/uav/Images.zip')
    for j, name in enumerate(cam.names):
        C = cam.centres[j]; rad = np.tan(np.deg2rad(20.))*max(C[2] - zmin, 0) + 1.
        cand = np.asarray(xy.query_ball_point(C[:2], rad), int)
        if not len(cand): continue
        vec = C - Q[cand]; length = np.linalg.norm(vec, axis=1); cos = vec @ up/length; qq = cand[cos >= c20]; cq = cos[cos >= c20]
        if not len(qq): continue
        uv, _, guard = cam.project(Q[qq], j); px = np.rint(uv).astype('i8')
        inside = guard & (px[:, 0] >= 1) & (px[:, 0] < cam.w - 1) & (px[:, 1] >= 1) & (px[:, 1] < cam.h - 1); qq, px, cq = qq[inside], px[inside], cq[inside]
        if not len(qq): continue
        im = Image.open(io.BytesIO(z.read(cam.members[j]))).convert('RGB'); gray = np.asarray(im.convert('L'), dtype='f4')/255.; gy, gx = np.gradient(gray)
        grad = np.hypot(gx[px[:, 1], px[:, 0]], gy[px[:, 1], px[:, 0]]); del gray, gx, gy, im
        seen[qq] += 1; low[qq] += (grad < thr).astype(np.int32); upd = cq > bestcos[qq]; best[qq[upd]] = j; bestcos[qq[upd]] = cq[upd]; used += 1
        if j % 50 == 0: print('TEXTURE', j, len(cam.names), used, round(T.mark('x')), flush=True)
    tl = np.where(seen > 0, (2*low >= seen).astype(np.int8), np.int8(-1))
    for name, l, r in offs: savez(O/'texture'/name, textureless=tl[l:r], near_nadir_views=seen[l:r], low_views=low[l:r], best_camera=best[l:r])
    dump(O/'texture/texture.json', dict(at=now(), threshold=thr, threshold_source=str(tf), threshold_sha256=sha(tf), images_used=used, patches=N, textureless=int((tl == 1).sum()), textured=int((tl == 0).sum()), unavailable=int((tl == -1).sum()),
         rule='GTJUDGE preservation.py texture rule at the patch prior-surface point; 819 WIDEN0 training views; no occlusion test (as the source)', seconds=T.mark('end'), GT_read=False, scientific_verdict=None))
    print('TEXTURE_DONE', N, int((tl == 1).sum()), int((tl == -1).sum()), round(T.mark('end')), flush=True)
if __name__ == '__main__': main()
