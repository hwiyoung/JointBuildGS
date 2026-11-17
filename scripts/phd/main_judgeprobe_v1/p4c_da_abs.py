"""확인 다 5.2 덧붙임 (11-17 사용자 결정): 다시점 관측을 촘촘한 절대 기준으로, 고른 사진과 모든 사진 둘로 다시 셈. B0 만.
- 고른 사진: selected_images[:,1] (이미 기하 깊이 지도로 가림 검사 +0.3 m 를 통과한 것), |D - z| <= 0.05/0.1/0.2 m 비율.
- 모든 사진: 학습 사진 819장 가운데 시선이 영상 깊이 면 법선과 60 도 안(JC choose_mvs_views 의 dot >= 0.5)이고 X 가 1024 x 741 안(가장자리 20 px 비움)인 것 전부.
  D - z 의 부호로 셋: 일치 |D - z| <= h, 앞 D < z - h (X 앞에 다른 면 = 가림), 뒤 D > z + h (깊이 지도가 X 보다 멀리 봄 = X 를 지나쳐 봄). h = 0.1, 0.2 m. D 없음(0, NaN)은 따로.
z = 카메라 축 깊이 (JC 와 같은 핀홀 K). 참값 쓰지 않음."""
from common import *
from photo_cameras import Cameras
H = [.05, .1, .2]
def main():
    cfg(); T = Timer(); cam = Cameras(); E = {}
    for prior in ['LoD2', 'ALS']:
        P = loadz(O/f'photo_{prior}.npz', ['region', 'centre_M', 'normal_M', 'selected_M', 'mvs_available'])
        m = np.flatnonzero((P['region'] == 'B0') & P['mvs_available'] & np.isfinite(P['centre_M']).all(1)); N = len(m)
        E[prior] = dict(idx=m, X=P['centre_M'][m], n=P['normal_M'][m], S=P['selected_M'][m], sel=np.full(P['selected_M'][m].shape, np.nan),
                        nall=np.zeros(N, np.int32), nD=np.zeros(N, np.int32), **{f'{k}{h}': np.zeros(N, np.int32) for k in ['agree', 'front', 'behind'] for h in H}, absd_list=[[] for _ in range(0)])
        E[prior]['med_all'] = None; E[prior]['dz'] = []
    for j in range(len(cam.names)):
        dep = cam.depth(j)
        if dep is None: continue
        for p, e in E.items():
            X = e['X']; q = X @ cam.M[j, :3, :3].T + cam.M[j, :3, 3]; z = q[:, 2]
            with np.errstate(invalid='ignore', divide='ignore'):
                uv = q[:, :2]/z[:, None]*[cam.K[0, 0], cam.K[1, 1]] + [cam.K[0, 2], cam.K[1, 2]]
            v = cam.centres[j] - X; v /= np.linalg.norm(v, axis=1)[:, None]; facing = np.einsum('ij,ij->i', v, e['n']) >= .5
            ok = facing & (z > 0) & (uv[:, 0] >= 20) & (uv[:, 0] < 1004) & (uv[:, 1] >= 20) & (uv[:, 1] < 721)
            ii = np.flatnonzero(ok)
            if not len(ii): continue
            px = np.rint(uv[ii]).astype(int); D_ = dep[px[:, 1], px[:, 0]].astype(float); has = np.isfinite(D_) & (D_ > 0); dz = np.where(has, D_ - z[ii], np.nan)
            e['nall'][ii] += 1; e['nD'][ii] += has
            for h in H:
                e[f'agree{h}'][ii] += has & (np.abs(dz) <= h); e[f'front{h}'][ii] += has & (dz < -h); e[f'behind{h}'][ii] += has & (dz > h)
            e['dz'].append((ii[has], dz[has]))
            # 고른 사진
            a = np.argwhere(e['S'] == j)
            if len(a):
                k = a[:, 0]; okk = ok[k] | True; pp = np.rint(uv[k]).astype(int); inb = (z[k] > 0) & (pp[:, 0] >= 0) & (pp[:, 0] < 1024) & (pp[:, 1] >= 0) & (pp[:, 1] < 741)
                Ds = np.full(len(k), np.nan); Ds[inb] = dep[pp[inb, 1], pp[inb, 0]]; Ds[~(Ds > 0)] = np.nan; e['sel'][k, a[:, 1]] = np.abs(Ds - z[k])
        if j % 100 == 0: print('view', j, round(T.s()), flush=True)
    rec = {}
    for p, e in E.items():
        ii = np.concatenate([x[0] for x in e['dz']]); dz = np.concatenate([x[1] for x in e['dz']]); o = np.argsort(ii, kind='stable'); ii, dz = ii[o], dz[o]
        cut = np.searchsorted(ii, np.arange(len(e['idx']) + 1)); med = np.array([np.median(np.abs(dz[a:b])) if b > a else np.nan for a, b in zip(cut[:-1], cut[1:])])
        selm = e['S'] >= 0; nsel = selm.sum(1); out = dict(idx=e['idx'], n_all=e['nall'], n_all_with_D=e['nD'], mv_all_median_absdiff=med)
        with np.errstate(invalid='ignore', divide='ignore'):
            for h in H:
                t = str(h).replace('.', 'p')
                out[f'mv_sel_share_abs{t}'] = np.where(nsel > 0, ((e['sel'] <= h) & selm).sum(1)/nsel, np.nan)
                for k in ['agree', 'front', 'behind']: out[f'mv_all_{k}_{t}'] = np.where(e['nD'] > 0, e[f'{k}{h}']/e['nD'], np.nan)
        savez(O/f'da_mv2_{p}.npz', **out)
        rec[p] = dict(points=len(e['idx']), pairs_all=int(e['nall'].sum()), pairs_all_with_D=int(e['nD'].sum()), median_views_all=float(np.median(e['nall'])), median_sel_share_abs0p1=float(np.nanmedian(out['mv_sel_share_abs0p1'])),
                      median_all_agree_0p1=float(np.nanmedian(out['mv_all_agree_0p1'])), median_all_behind_0p1=float(np.nanmedian(out['mv_all_behind_0p1'])), median_all_absdiff_m=float(np.nanmedian(med)))
    dump(O/'da_mv2.json', dict(at=now(), rows=rec, seconds=T.s(), scientific_verdict=None)); print('DA2', json.dumps(rec), flush=True)
    progress(f'확인 다 5.2 덧붙임(절대 기준·모든 사진) 셈 끝 ({round(T.s())} 초)')
if __name__ == '__main__': main()
