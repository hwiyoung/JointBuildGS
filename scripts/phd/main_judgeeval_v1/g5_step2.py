"""5.2 ② 가시성 분석 재료(판단 없음, 참값 안 읽음). 10동의 모든 사전 정보 패치(①의 값 없음만이 아니라 모두: 후보마다 값 없음이 달라서).
패치 칸(사전 정보 면 위 0.25 x 0.25 m, 축 tangent1·n x tangent1)을 학습 영상 819장마다 투영, 칸 안 화소마다 시선이 사전 정보 면과 만나는 거리 Z 와 기하 깊이 지도 D:
  못 봄(D 없음) / 지나감 D > Z + δ / 막힘 D < Z − δ / 일치 |D − Z| <= δ, δ = 1 %·5 % Z (Merrell 외 2007). 화면 밖·카메라 뒤 영상은 표를 내지 않음.
중심 한 점 판: 패치 중심이 투영된 화소 하나로 영상마다 같은 분류.
나오는 것: work/<stage>/step2_<prior>.npz (화소 수 넷 x δ 둘, 지나감·표 낸 영상 수, 중심 판 영상 수 넷 x δ 둘), 지나감(1 %) 화소 목록(③ 시작 점).
사용: GT_STAGE=ga3 g5_step2.py"""
from common import *
def main():
    c = cfg(); build_vis(); B = buildings(); T = Timer()
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'step2_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'tangent1', 'prior_height_m', 'building']); ids = np.flatnonzero(np.isin(P['building'], list(B)))
        n = P['normal'][ids]; ph = P['prior_height_m'][ids]; good = np.isfinite(n).all(1) & np.isfinite(ph); g = np.flatnonzero(good)
        s = P['centre'][ids] + np.nan_to_num(ph)[:, None]*np.nan_to_num(n); u = P['tangent1'][ids] - np.einsum('ij,ij->i', P['tangent1'][ids], np.nan_to_num(n))[:, None]*np.nan_to_num(n)
        un = np.linalg.norm(u, axis=1); u = u/np.where(un > 1e-9, un, 1)[:, None]
        pb = O/'tmp'/f'vis_{STAGE}_{prior}.bin'; np.ascontiguousarray(np.c_[s, n, u, np.full(len(ids), c['truth']['column']['cell_half_m'][0])][g], '<f8').tofile(pb)
        ob = O/'tmp'/f'vis_{STAGE}_{prior}.out'; pp = O/'tmp'/f'vis_{STAGE}_{prior}.pass'
        subprocess.run([str(VBIN), 'vis', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(pb), str(len(g)), str(ob), str(pp)], check=True, env=dict(os.environ, OMP_NUM_THREADS=os.environ.get('GT_THREADS', '30')))
        out = np.full((len(ids), 20), np.nan); out[g] = np.fromfile(ob, '<f8').reshape(-1, 20); pas = np.fromfile(pp, '<i4').reshape(-1, 3); pas[:, 0] = g[pas[:, 0]]   # 패치 번호 -> ids 안 차례
        savez(dest, patch_index=ids, counts=out, good=good, pass_pix=pas); pb.unlink(); ob.unlink(); pp.unlink()
        rec = dict(at=now(), prior=prior, patches=len(ids), good=int(good.sum()), pass_pixels=len(pas), seconds=T.s(), columns=['d1 unseen', 'd1 pass', 'd1 block', 'd1 agree', 'd1 img_pass', 'd1 img_vote', 'd5 unseen', 'd5 pass', 'd5 block', 'd5 agree', 'd5 img_pass', 'd5 img_vote',
                   'c1 unseen', 'c1 pass', 'c1 block', 'c1 agree', 'c5 unseen', 'c5 pass', 'c5 block', 'c5 agree'], scientific_verdict=None)
        dump(dest.with_suffix('.json'), rec); progress(f'② 재료 {PN[prior]}: 패치 {len(ids):,}, 지나감 화소 {len(pas):,}, {T.s():.0f} s'); print('STEP2', rec, flush=True)
if __name__ == '__main__': main()
