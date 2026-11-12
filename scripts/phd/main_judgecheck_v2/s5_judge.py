"""판정 (발주 2.2, 2.6, 6.1). 참값 쓰지 않음(정답 판정은 s6 에서 참값으로 따로).
  s5_judge.py <variant>   variant = s2_calibrate.VAR 의 열쇠
광도 점수는 한 번 셈해 저장한 것(photo_scores)을 모든 판이 다시 쓴다. t 는 그 판의 한계 안(구성 패치가 모두 한계 안) 사진 점으로 다시 정한다.
t: 탐색 지역 x 사전 정보 x 지붕/벽, 넓이 가중 아래 5 %, 5000개 넘으면 무작위 5000개(씨앗 20261112), 밖 지역은 일곱 지역 합침."""
from common import *
import jc2_judge as J
def main(variant):
    cfg(); T = Timer(); seed = 20261112
    tiles_ = [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob('*__LoD2.npz'))] + [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob('*__ALS.npz'))]
    tiles_ = sorted(set(tiles_)); pts = {'LoD2': [], 'ALS': []}
    # 1. 사진 점 (구역마다) - 이 판의 한계 안 여부
    for tile in tiles_:
        pp = O/'photo_prepared'/f'{tile}.npz'; sc = O/'photo_scores'/tile/'scores.npz'
        if not pp.exists(): continue
        g = loadz(pp, ['point_id', 'prior', 'kind', 'area', 'source_index', 'available', 'selected_images']); s = loadz(sc) if sc.exists() else None
        for prior in ['LoD2', 'ALS']:
            m = g['prior'] == prior
            if not m.any(): continue
            grp = loadz(O/'photo_groups'/f'{tile}__{prior}.npz', ['patch_point', 'region']); geo = loadz(O/'geometry'/variant/f'{tile}__{prior}.npz', ['geometry'])
            P = len(grp['region']); allw = np.bincount(grp['patch_point'], weights=(geo['geometry'] != 0).astype(float), minlength=P) == 0
            si = g['source_index'][m]; e = dict(tile=tile, prior=prior, kind=g['kind'][m], area=g['area'][m], source_index=si, region=grp['region'][si], all_within=allw[si],
                                               mvs_available=g['available'][m][:, 1], n_selected=(g['selected_images'][m] >= 0).sum(-1))
            if s is not None and np.array_equal(s['point_id'], g['point_id']):
                e.update(s_P=s['score'][m][:, 0], s_M=s['score'][m][:, 1], texture=s['texture'][m], scored=np.ones(int(m.sum()), bool))
            else:
                k = int(m.sum()); e.update(s_P=np.full(k, np.nan), s_M=np.full(k, np.nan), texture=np.full((k, 2), np.nan), scored=np.zeros(k, bool))
            pts[prior].append(e)
    # 2. t
    trows = []; tval = {}
    for prior in ['LoD2', 'ALS']:
        if not pts[prior]: continue
        A = {k: np.concatenate([e[k] for e in pts[prior]]) for k in ['kind', 'area', 'region', 'all_within', 's_P']}
        for kind in ([1, 2] if prior == 'LoD2' else [1]):
            for reg in REGIONS + ['none']:
                base = (A['kind'] == kind) & A['all_within']
                pool = base & (A['region'] == reg) if reg != 'none' else base & (A['region'] != 'none')
                rs = [seed, REGIONS.index(reg) if reg != 'none' else 7, 0 if prior == 'LoD2' else 1, kind]
                t, t10, ch = J.threshold(A['s_P'], A['area'], pool, rs)
                tval[(reg, prior, kind)] = t
                trows.append(dict(region=reg, prior=prior, kind=kind, t=t, t10=t10, pool_count=int(pool.sum()), sample_count=len(ch), finite_count=int(np.isfinite(A['s_P'][ch]).sum()), sample_area_m2=float(A['area'][ch].sum()), seed=rs))
    # 3. 판정 (구역마다)
    out = O/'judge'/variant; summ = []
    pmap = {}
    for prior in ['LoD2', 'ALS']:
        for e in pts[prior]: pmap[(e['tile'], prior)] = e
    for tile in tiles_:
        for prior in ['LoD2', 'ALS']:
            gp = O/'geometry_raw'/f'{tile}__{prior}.npz'
            if not gp.exists(): continue
            g = loadz(gp, ['patch_id', 'kind', 'area', 'n', 'd_m', 'prior_height_m', 'mvs_mean_m', 'normal', 'building', 'region', 'centre'])
            cb = loadz(O/'geometry'/variant/f'{tile}__{prior}.npz'); si = loadz(O/'sight'/f'{tile}__{prior}.npz', ['free5', 'free10', 'patch_id'])
            assert np.array_equal(si['patch_id'], g['patch_id']) and np.array_equal(cb['patch_id'], g['patch_id'])
            grp = loadz(O/'photo_groups'/f'{tile}__{prior}.npz', ['patch_point']); P = int(grp['patch_point'].max()) + 1
            pcode_pt = np.full(P, 9, np.int8); spt = np.full((P, 2), np.nan); tpt = np.full(P, np.nan)
            e = pmap.get((tile, prior))
            if e is not None:
                tt = np.array([tval[(r if r in REGIONS else 'none', prior, int(k))] for r, k in zip(e['region'], e['kind'])])
                pc = J.photo_code(e['s_P'], e['s_M'], tt, e['mvs_available'], e['texture'], e['n_selected']); pc[~e['scored']] = 9
                pcode_pt[e['source_index']] = pc; spt[e['source_index'], 0] = e['s_P']; spt[e['source_index'], 1] = e['s_M']; tpt[e['source_index']] = tt
            pcode = pcode_pt[grp['patch_point']]
            free = np.where(g['kind'] == 1, si['free10'], si['free5'])
            reg, why = J.decide(prior, g['n'], cb['geometry'], g['prior_height_m'], g['mvs_mean_m'], np.isfinite(g['normal']).all(1), cb['u_M'], pcode, free)
            if variant == 'base':
                face = loadz(O/'place'/f'{tile}__{prior}.npz', ['face'])['face']
                grpkey = np.char.add(np.char.add(g['building'].astype(str), '|'), face.astype(str))
                ch, comps = J.alt_da(prior, reg[J.VARIANTS.index('method')], why[J.VARIANTS.index('method')], g['centre'], g['area'], grpkey)
                k = J.VARIANTS.index('alt_da'); reg[k, ch] = 2 if prior == 'ALS' else 1; why[k, ch] = 2
            H = np.stack([J.target_height(reg[j], g['prior_height_m'], g['mvs_mean_m'], cb['u_M'], cb['sigma_P'], cb['sigma_W']) for j in range(len(J.VARIANTS))])
            savez(out/f'{tile}__{prior}.npz', patch_id=g['patch_id'], region=reg, reason=why, target_h=H, photo_code=pcode, photo_point=grp['patch_point'], s_P=spt[grp['patch_point'], 0], s_M=spt[grp['patch_point'], 1], t=tpt[grp['patch_point']])
            summ.append(dict(tile=tile, prior=prior, patches=len(g['kind']), method_area={str(c): float(g['area'][reg[J.VARIANTS.index('method')] == c].sum()) for c in [0, 1, 2, 3, 4, 9]}))
    dump(O/'judge'/f'{variant}.json', dict(at=now(), variant=variant, t_rows=trows, tiles=summ, seconds=T.mark('end'), GT_read=False, scientific_verdict=None))
    print('JUDGE', variant, round(T.mark('end')), json.dumps([(r['region'], r['prior'], r['kind'], r['pool_count'], None if not np.isfinite(r['t']) else round(r['t'], 4)) for r in trows]))
if __name__ == '__main__': main(sys.argv[1])
