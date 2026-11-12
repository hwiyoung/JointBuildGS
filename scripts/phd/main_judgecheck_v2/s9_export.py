"""낼 것 (발주 8절): 탐색 지역(일곱 + none) x 사전 정보마다 core_points / gt_points / photo_points / training_regions.
번호표: 영역 0 일치 1 사전정보 사용 2 영상 깊이 사용 3 제거 4 결측 9 미판정; 근거 0 사진 지지 1 사진 반박 2 기본 판정 9 해당 없음;
광도 0 지지 1 반박 2 둘 다 낮음 3 둘 다 높음 4 MVS 면 없음 5 조각 부족 6 무늬 없음 7 사진 부족 9 셈 안 함; 자리 0 면 안쪽 1 면 경계 2 건물 가장자리;
아홉 조합 = 사전 정보(맞음 0 틀림 1 없음 2) x 3 + 영상 깊이(같은 차례); 지금 정의 경우 0 두 자료 모두 유효 1 사전정보 오류 2 영상 깊이 오류 3 그 밖 4 영상 깊이 결측;
참값 종류 1 지붕 2 벽 3 땅. 판 차례 = jc2_judge.VARIANTS."""
from common import *
import pandas as pd
import jc2_judge as J
SENS = ['ring_1.0', 'ring_3.0', 'z_1.645', 'z_2.576', 'centre_shift', 'building_r', 'same_face_ring']
def main():
    cfg(); T = Timer(); cl = pd.read_csv(O/'analysis/clusters.csv') if (O/'analysis/clusters.csv').exists() else None; recs = []
    for prior in ['LoD2', 'ALS']:
        parts = []
        for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            t = p.stem.split('__')[0]
            g = loadz(p, ['patch_id', 'building', 'region', 'group', 'split', 'kind', 'roof_type', 'surf', 'area', 'centre', 'raw_centre', 'normal', 'shift_m', 'n', 'n5', 'n10', 'mvs_mean_m', 'mvs_median_m', 'mvs_sd_m', 'prior_height_m', 'prior_n', 'd_m'])
            b = loadz(O/'geometry/base'/p.name); j = loadz(O/'judge/base'/p.name); si = loadz(O/'sight'/p.name, ['free5', 'free10', 'votes'])
            e = dict(g); e['tile'] = np.full(len(g['kind']), t)
            e.update(u_M=b['u_M'], sigma_P=b['sigma_P'], sigma_W=b['sigma_W'], r_m=b['r_m'], L_m=b['L_m'], geometry=b['geometry'], agreement_for_calibration=b['agreement_for_calibration'],
                     free5=si['free5'], free10=si['free10'], sight_votes=si['votes'], photo_code=j['photo_code'], photo_point=j['photo_point'], s_P=j['s_P'], s_M=j['s_M'], t=j['t'],
                     region_v=j['region'], reason_v=j['reason'], target_h_v=j['target_h'])
            e['place'] = loadz(O/'place'/p.name, ['place'])['place']; e['face'] = loadz(O/'place'/p.name, ['face'])['face']; e['textureless'] = loadz(O/'texture'/p.name, ['textureless'])['textureless']
            for v in SENS:
                gv = O/'geometry'/v/p.name; jv = O/'judge'/v/p.name
                if gv.exists() and jv.exists():
                    c = loadz(gv, ['u_M', 'sigma_P', 'L_m', 'geometry']); jj = loadz(jv, ['region'])
                    tag = v.replace('.', 'p'); e[f'sens_{tag}_u_M'] = c['u_M']; e[f'sens_{tag}_sigma_P'] = c['sigma_P']; e[f'sens_{tag}_L_m'] = c['L_m']; e[f'sens_{tag}_geometry'] = c['geometry']; e[f'sens_{tag}_region'] = jj['region'][J.VARIANTS.index('method')]
            parts.append(e)
        keys = set.intersection(*[set(x) for x in parts]); A = {k: np.concatenate([x[k] for x in parts], axis=-1 if k in ('region_v', 'reason_v', 'target_h_v') else 0) for k in keys}
        gt = loadz(O/'analysis'/f'gt_{prior}.npz'); cnt = np.bincount(gt['gid'][gt['paired']], minlength=len(A['kind'])); A['gt_points_in_column'] = cnt[:len(A['kind'])]
        A['variants'] = np.array(J.VARIANTS)
        for reg in REGIONS + ['none']:
            m = A['region'] == reg
            if not m.any(): continue
            out = {k: (v[..., m] if k in ('region_v', 'reason_v', 'target_h_v') else v[m]) for k, v in A.items() if k != 'variants'}; out['variants'] = A['variants']
            savez(O/'core_points'/f'{reg}__{prior}.npz', **out)
            # 학습용 판정 파일 (JUDGEAPPLY-v1 6.5 형식, 본값)
            a = out['region_v'][J.VARIANTS.index('method')]; h = out['target_h_v'][J.VARIANTS.index('method')]; hr = h.copy()
            vm = out['u_M']**2 + out['sigma_W']**2; vp = out['sigma_P']**2
            with np.errstate(divide='ignore', invalid='ignore'): w = vm/(vp + vm)
            hr[a == 0] = h[a == 0] + w[a == 0]*out['r_m'][a == 0]; keep = np.isin(a, [1, 4]); hr[keep] = h[keep] + out['r_m'][keep]
            tr = np.full(len(a), -1, np.int8)
            for ja, tg in [(0, 1), (1, 2), (2, 3), (3, 5), (4, 0)]: tr[a == ja] = tg
            savez(O/'training_regions'/f'{reg}__{prior}.npz', patch_id=out['patch_id'], centre=out['centre'], normal=out['normal'], kind=out['kind'], area=out['area'], building=out['building'], surf=out['surf'],
                  in_eval=np.ones(len(a), bool), region=tr, judge_region=a, reason=out['reason_v'][J.VARIANTS.index('method')], h_no_r=h, h_with_r=hr, target_no_r=out['centre'] + h[:, None]*out['normal'],
                  target_with_r=out['centre'] + hr[:, None]*out['normal'], u=out['u_M'], sigma_p=out['sigma_P'], u_M=out['u_M'], sigma_P=out['sigma_P'], sigma_W=out['sigma_W'], r=out['r_m'], surface_exists=np.isin(a, [0, 1, 2, 4]))
            recs.append(dict(prior=prior, region=reg, patches=int(m.sum()), area_m2=float(A['area'][m].sum())))
        # 참값 점마다
        gid_region = A['region']
        for reg in REGIONS + ['none']:
            m = gt['paired'] & (gt['region'] == reg) if reg != 'none' else gt['paired'] & ((gt['region'] == 'none') | (gt['region'] == ''))
            if not m.any(): continue
            Ng = len(gt['src']); o = {}
            for k, v in gt.items():
                if v.ndim == 2 and v.shape == (len(J.VARIANTS), Ng): o[k] = v[:, m]
                elif v.ndim >= 1 and v.shape[0] == Ng: o[k] = v[m]
            o['row_number'] = np.flatnonzero(m); o['variants'] = np.array(J.VARIANTS)
            savez(O/'gt_points'/f'{reg}__{prior}.npz', **o)
        um = ~gt['paired']; savez(O/'gt_points'/f'unpaired__{prior}.npz', **{k: v[um] for k, v in gt.items() if v.ndim >= 1 and v.shape[0] == len(gt['src'])})
        print('EXPORT', prior, round(T.mark(prior)), flush=True)
    # 사진 점마다
    for p in sorted((O/'photo_prepared').glob('*.npz')):
        t = p.stem; q = loadz(p, ['point_id', 'prior', 'kind', 'area', 'all_within', 'dbar', 'r_m', 'centres', 'normals', 'available', 'selected_images', 'prior_height_m', 'prior_n', 'mvs_fit_count', 'mvs_fit_nmad_m', 'mvs_normal_angle_deg', 'mvs_fit_reason'])
        sc = O/'photo_scores'/t/'scores.npz'
        if sc.exists():
            s = loadz(sc, ['point_id', 'score', 'texture', 'valid_image_count']); assert np.array_equal(s['point_id'], q['point_id']); q.update(s_P=s['score'][:, 0], s_M=s['score'][:, 1], texture=s['texture'], valid_image_count=s['valid_image_count'])
        savez(O/'photo_points'/f'{t}.npz', **q)
    dump(O/'export.json', dict(at=now(), rows=recs, seconds=T.mark('end'), scientific_verdict=None)); print('EXPORT_DONE', round(T.mark('end')))
if __name__ == '__main__': main()
