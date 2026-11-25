"""5.3 ③ 다시점 검증 재료(참값 안 읽음). ③에 갈 수 있는 패치(맞댈 후보 가운데 하나라도 ①이 다르다, 또는 ①이 값 없음이고 ② 규칙 하나라도 ③으로)만.
시작 점: ①에서 온 패치 = 본 길이 원통 안 영상 점의 (영상, 화소)(후보 길이에도 같은 점을 씀), ②에서 온 패치 = 지나감(δ 1 %)으로 센 화소.
점마다 judgevis fuse: COLMAP StereoFusion 규칙(깊이 1 %, 되비춤 2 화소, 법선 10°, 겹침 50장, 넓혀 가기 100, 화소 5개)으로 일관됨, 그리고 A2 = 같은 세 조건을 한 번에 만족하는 겹침 영상 수.
패치마다: 점 수, COLMAP 일관된 점 수, A2 일관된 점 수(자기 영상 포함 5장 이상 = 다른 영상 4장 이상, 지금 a2_count 와 같은 셈). 사용: GT_STAGE=ga3 g6_step3.py"""
from common import *
import judge_lib as JL
def main():
    c = cfg(); build_vis(); T = Timer(); S1c = c['judgment']['step1_m3c2']; thr = {k: v for k, v in S1c['size_boundary_m'].items() if k != 'kind'}
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'step3_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        S = loadz(O/'work'/STAGE/f'step1_{prior}.npz'); C = loadz(O/'work'/STAGE/f'step2_{prior}.npz'); assert np.array_equal(S['patch_index'], C['patch_index'])
        kind = loadz(inp('patches', prior=prior), ['kind'])['kind'][S['patch_index']]; N = len(kind); pos = -np.ones(int(S['patch_index'].max()) + 1, np.int64); pos[S['patch_index']] = np.arange(N)
        anydiff = np.zeros(N, bool); anynone = np.zeros(N, bool)
        for h in [0, 1, 2]:
            for rep in ['mean', 'median']:
                for size in [False, True]:
                    for Lv in ['pm', 'orig']:
                        r = JL.step1(S, prior, kind, h, rep, size, Lv, False, thr); anydiff |= r == JL.DIFF; anynone |= r == JL.NONE
        go2 = np.zeros(N, bool)
        for rule in ['pixel', 'centre', 'one', 'two']:
            for dl in [1, 5]: go2 |= JL.step2(C['counts'], rule, dl) == 1
        need1 = anydiff; need2 = anynone & go2
        own1 = pos[S['start_owner']]; m1 = need1[own1]; st1 = S['starts'][m1]; o1 = own1[m1]
        pp = C['pass_pix']; m2 = need2[pp[:, 0]]; st2 = pp[m2][:, 1:]; o2 = pp[m2][:, 0]
        allst = np.r_[st1, st2].astype(np.int32); key = allst[:, 0].astype(np.int64)*(1024*741) + allst[:, 1]; uk, inv = np.unique(key, return_inverse=True)
        us = np.c_[(uk // (1024*741)).astype(np.int32), (uk % (1024*741)).astype(np.int32)]
        sb = O/'tmp'/f'fuse_{STAGE}_{prior}.bin'; ob = O/'tmp'/f'fuse_{STAGE}_{prior}.out'; np.ascontiguousarray(us, '<i4').tofile(sb)
        print('FUSE', prior, 'patches1', int(need1.sum()), 'patches2', int(need2.sum()), 'starts', len(allst), 'unique', len(us), flush=True)
        subprocess.run([str(VBIN), 'fuse', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(VIS/'overlap.bin'), str(sb), str(len(us)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS=os.environ.get('GT_THREADS', '30')))
        R = np.fromfile(ob, '<i4').reshape(-1, 3); sb.unlink(); ob.unlink(); pr = R[inv]; cons = pr[:, 0] == 1; a2 = (pr[:, 2] + 1) >= 5
        n1 = len(st1); out = {}
        for tag, o, sl in [('from1', o1, slice(0, n1)), ('from2', o2, slice(n1, None))]:
            out[f'{tag}_total'] = np.bincount(o, minlength=N); out[f'{tag}_cons'] = np.bincount(o, weights=cons[sl], minlength=N); out[f'{tag}_a2'] = np.bincount(o, weights=a2[sl], minlength=N)
        savez(dest, patch_index=S['patch_index'], need1=need1, need2=need2, **out)
        rec = dict(at=now(), prior=prior, patches_from1=int(need1.sum()), patches_from2=int(need2.sum()), starts=len(allst), unique_pixels=len(us), consistent_share=float(cons.mean()) if len(cons) else None,
                   a2_share=float(a2.mean()) if len(a2) else None, cluster_size_hist=np.bincount(np.minimum(R[:, 1], 5), minlength=6).tolist(), seconds=T.s(), scientific_verdict=None)
        dump(dest.with_suffix('.json'), rec); progress(f'③ 재료 {PN[prior]}: {rec}'); print('STEP3', rec, flush=True)
if __name__ == '__main__': main()
