"""5.1 ① M3C2 재료(판단 없음, 참값 안 읽음). 패치마다(10동):
  판단 원통(축 = 패치 중심·법선, 반지름 LoD2 지붕 0.075 / 벽 0.125 / 항공 LiDAR 0.075) 안 영상 깊이 점 모두(바깥 첫 면 규칙 없음)를
  반길이 후보 셋(지붕 3·5·10, 벽 2·3·5 m)마다: 점 수, 평균, 중앙값, 표준편차. d = 값 − 사전 정보 높이(항공 LiDAR).
  본 길이(지붕 10, 벽 5) 원통 안 점의 (영상, 화소) 목록 -> ③ 시작 점.
  항공 LiDAR: 판단의 사전 정보 원통(반지름 0.75 m, ±10 m, 원래 자리 = 중심 − 지역 이동) 안 항공 LiDAR 점 수와 표준편차 -> 원문 한계식.
  한계 L 의 항(u_M, sigma_P, sigma_W, r)은 JUDGECHECK-v2 저장값(JUDGEPROBE patch_*.npz) 그대로.
사용: GT_STAGE=ga3 g4_step1.py"""
from common import *
KEYS = ['tile', 'kind', 'area', 'centre', 'normal', 'prior_height_m', 'building', 'tiles', 'u_M', 'sigma_P', 'sigma_W', 'r_m', 'L_m', 'j_region', 'n', 'mvs_mean_m']
def main():
    c = cfg(); S1 = c['judgment']['step1_m3c2']; build(); B = buildings(); T = Timer(); names = json.loads(inp('image_split').read_text())['train']
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'step1_{prior}.npz'
        if dest.exists(): print('exists', dest); continue
        P = loadz(inp('patches', prior=prior), KEYS); tiles = list(P['tiles']); N = len(P['kind']); ids = np.flatnonzero(np.isin(P['building'], list(B))); wall = P['kind'] == 2
        rad = np.where(wall & (prior == 'LoD2'), S1['radius_m']['LoD2_wall'][0], S1['radius_m'][f'{prior}_roof'][0])
        Hs = np.where(wall[:, None], np.array(S1['half_length_m']['candidates']['wall'], float), np.array(S1['half_length_m']['candidates']['roof'], float))
        Hmain = np.where(wall, S1['half_length_m']['main']['wall'], S1['half_length_m']['main']['roof']).astype(float)
        cy = np.full((N, 12), np.nan); als = np.full((N, 2), np.nan); starts = []; owner = []
        shift = {b: np.array(r['als_shift_m'], float) for b, r in B.items()}
        for ti in np.unique(P['tile'][ids]):
            t0 = T.s(); m = ids[P['tile'][ids] == ti]; t = tiles[ti]; nor = np.nan_to_num(P['normal'][m]); cen = P['centre'][m]
            cy[m] = run('cylk', inp('image_points', tile=t), np.c_[cen, nor, rad[m], Hs[m]], f'cylk_{prior}_{t}')
            o, pr = run_ids(inp('image_points', tile=t), np.c_[cen, nor, rad[m], Hmain[m]], f'ids_{prior}_{t}')
            vw = np.load(inp('image_point_view', tile=t), mmap_mode='r'); px = np.load(inp('image_point_pixel', tile=t), mmap_mode='r')
            if len(pr): starts.append(np.c_[np.asarray(vw[pr[:, 1]]).astype(np.int32), np.asarray(px[pr[:, 1]]).astype(np.int32)]); owner.append(m[pr[:, 0]].astype(np.int64))
            if prior == 'ALS':
                raw = cen - np.array([shift[b] for b in P['building'][m]])
                a = run('cylk', WI/'points'/t/'als_xyz.npy', np.c_[raw, nor, np.full(len(m), .75), np.tile([10., 10., 10.], (len(m), 1))], f'als_{t}'); als[m] = a[:, [0, 3]]
            print('STEP1', prior, t, len(m), len(pr), round(T.s() - t0, 1), flush=True)
        ph = np.nan_to_num(P['prior_height_m'])
        d_mean = cy[:, 1::4] - ph[:, None]; d_med = cy[:, 2::4] - ph[:, None]
        st = np.concatenate(starts) if starts else np.empty((0, 2), np.int32); ow = np.concatenate(owner) if owner else np.empty(0, np.int64)
        Lchk = 1.96*(np.sqrt(P['u_M']**2 + P['sigma_P']**2 + P['sigma_W']**2) + np.abs(P['r_m'])); okL = np.isfinite(P['L_m'][ids])
        savez(dest, patch_index=ids, Hs=Hs[ids], n=cy[ids][:, 0::4], d_mean=d_mean[ids], d_med=d_med[ids], sd=cy[ids][:, 3::4], u_M=P['u_M'][ids], sigma_P=P['sigma_P'][ids], sigma_W=P['sigma_W'][ids],
              r_m=P['r_m'][ids], L_m=P['L_m'][ids], als_n=als[ids][:, 0], als_sd=als[ids][:, 1], jc2=P['j_region'][ids, 4], starts=st, start_owner=ow, prior_height=P['prior_height_m'][ids],
              cur_n=P['n'][ids], cur_mean=P['mvs_mean_m'][ids])
        rec = dict(at=now(), prior=prior, patches=len(ids), starts=len(st), L_recomputed_equal=int(np.isclose(Lchk[ids][okL], P['L_m'][ids][okL]).sum()), L_finite=int(okL.sum()), seconds=T.s(), scientific_verdict=None)
        dump(dest.with_suffix('.json'), rec); progress(f'① 재료 {PN[prior]}: {rec}'); del P
if __name__ == '__main__': main()
