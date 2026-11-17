"""확인 다 5.2 (발주 5절): B0 탐색 지역 사진 점마다 영상 깊이 면 중심 X 를 그 면의 고른 사진(selected_images[:,1])에 비춰 기하 깊이 지도 값 D 와 비교.
z = 카메라 축 깊이 (WIDEN0 자세, 1024 x 741 K, JC photo_cameras.choose_mvs_views 와 같은 투영). 관측: |D - z|/z <= 0.5, 1, 2 % 인 사진 비율, |D - z| 중앙값."""
from common import *
from photo_cameras import Cameras
def main():
    cfg(); T = Timer(); cam = Cameras(); out = {}
    for prior in ['LoD2', 'ALS']:
        P = loadz(O/f'photo_{prior}.npz', ['region', 'centre_M', 'selected_M', 'mvs_available', 'tile', 'source_index'])
        m = np.flatnonzero((P['region'] == 'B0') & P['mvs_available'] & np.isfinite(P['centre_M']).all(1)); X = P['centre_M'][m]; S = P['selected_M'][m]
        absd = np.full(S.shape, np.nan); rel = np.full(S.shape, np.nan)
        out[prior] = dict(idx=m, X=X, S=S, absd=absd, rel=rel)
    for j in range(len(cam.names)):
        jobs = [(p, np.argwhere(out[p]['S'] == j)) for p in out]
        if not any(len(a) for _, a in jobs): continue
        dep = cam.depth(j)
        if dep is None: continue
        for p, a in jobs:
            if not len(a): continue
            X = out[p]['X'][a[:, 0]]; q = X @ cam.M[j, :3, :3].T + cam.M[j, :3, 3]; z = q[:, 2]
            uv = q[:, :2]/z[:, None]*[cam.K[0, 0], cam.K[1, 1]] + [cam.K[0, 2], cam.K[1, 2]]; px = np.rint(uv).astype(int)
            ok = (z > 0) & (px[:, 0] >= 0) & (px[:, 0] < 1024) & (px[:, 1] >= 0) & (px[:, 1] < 741)
            D_ = np.full(len(z), np.nan); D_[ok] = dep[px[ok, 1], px[ok, 0]]; D_[~(D_ > 0)] = np.nan
            out[p]['absd'][a[:, 0], a[:, 1]] = np.abs(D_ - z); out[p]['rel'][a[:, 0], a[:, 1]] = np.abs(D_ - z)/z
    rec = dict(at=now(), seconds=None, rows={})
    for p, e in out.items():
        sel = e['S'] >= 0; nv = sel.sum(1)
        with np.errstate(invalid='ignore', divide='ignore'):
            res = {f'mv_share_{tag}': np.where(nv > 0, ((e['rel'] <= v) & sel).sum(1)/nv, np.nan) for tag, v in [('0p5', .005), ('1', .01), ('2', .02)]}
        res['mv_median_absdiff'] = np.array([np.nanmedian(r[s]) if s.any() and np.isfinite(r[s]).any() else np.nan for r, s in zip(e['absd'], sel)])
        res['mv_missing_D_share'] = np.where(nv > 0, (sel & ~np.isfinite(e['absd'])).sum(1)/np.maximum(nv, 1), np.nan)
        savez(O/f'da_mv_{p}.npz', idx=e['idx'], n_views=nv, **res)
        rec['rows'][p] = dict(points=len(e['idx']), pairs=int(sel.sum()), median_share_1=float(np.nanmedian(res['mv_share_1'])), median_absdiff_m=float(np.nanmedian(res['mv_median_absdiff'])))
    rec['seconds'] = T.s(); dump(O/'da_mv.json', rec); print('DA', json.dumps(rec), flush=True)
    progress(f'확인 다 5.2 B0 다시점 셈 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
