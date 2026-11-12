"""확인 5 (다): 네 경우 밖(아홉 조합 4~8) 참값 점 모임과 참값이 없는 사전 정보 패치 모임, 모임마다 사실과 기하 유형. 원인 이름은 붙이지 않는다.
모임: 같은 건물 안에서 0.6 m 안으로 잇기(참값 점은 좌표, 패치는 중심). 1 m2 미만은 수와 넓이만.
윤곽: 그 건물의 LoD2 GroundSurface (위에서 본 사전 정보 건물 윤곽; 공유 기준). 점의 절반 넘게가 윤곽 밖이면 '윤곽 밖'."""
from common import *
import pandas as pd
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Polygon, Point
from shapely import contains_xy
from shapely.ops import unary_union
import jc2_judge as J
from s7_tables import write, area, JUD
TYPES = ['윤곽 밖의 새 면', '윤곽 안의 사전 정보 없음', '두 자료가 같은 쪽으로 어긋남', '두 자료가 다른 쪽으로 어긋남', '사전 정보 틀림·영상 깊이 없음', '참값이 지나 본 사전 정보 면', '참값이 관측하지 못한 사전 정보 면']
def footprints():
    out = {}
    for b in json.loads((W/'inputs/lod2_buildings.json').read_text()):
        polys = []
        for s in b['surfaces'].get('ground', []):
            ext = np.asarray(s['ext'])[:, :2] - [690953., 5336071.]; holes = [np.asarray(h)[:, :2] - [690953., 5336071.] for h in s.get('holes', [])]
            try: polys.append(Polygon(ext, holes).buffer(0))
            except Exception: pass
        if polys: out[b['id']] = unary_union(polys)
    return out
def components(P, r=.6):
    if len(P) == 1: return 1, np.zeros(1, int)
    pairs = cKDTree(P).query_pairs(r, output_type='ndarray'); g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(P), len(P)))
    return connected_components(g, directed=False)
def patch_arrays(prior):
    tiles_ = [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))]; A = []
    for t in tiles_:
        g = loadz(O/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'centre', 'kind', 'area', 'building']); j = loadz(O/'judge/base'/f'{t}__{prior}.npz', ['region', 'photo_point'])
        pp = O/'photo_prepared'/f'{t}.npz'; grp = loadz(O/'photo_groups'/f'{t}__{prior}.npz', ['patch_point']); P = int(grp['patch_point'].max()) + 1
        nm = np.full(P, np.nan); tex = np.full(P, np.nan)
        if pp.exists():
            q = loadz(pp, ['prior', 'source_index', 'mvs_fit_nmad_m', 'point_id']); m = q['prior'] == prior; nm[q['source_index'][m]] = q['mvs_fit_nmad_m'][m]
            sc = O/'photo_scores'/t/'scores.npz'
            if sc.exists():
                s = loadz(sc, ['texture', 'point_id'])
                if np.array_equal(s['point_id'], q['point_id']): tex[q['source_index'][m]] = np.nanmax(s['texture'][m], 1) if m.any() else []
        A.append(dict(patch_id=g['patch_id'], centre=g['centre'], kind=g['kind'], area=g['area'], building=g['building'], region=j['region'][J.VARIANTS.index('method')], mvs_nmad=nm[grp['patch_point']], texture=tex[grp['patch_point']]))
    return {k: np.concatenate([a[k] for a in A]) for k in A[0]}
def inner_counts(prior):
    tot = {}; inn = {}
    for p in (O/'truth/rest').glob('*.npz'):
        z = loadz(p); k = f'{prior}__patch_patch_id'
        if k not in z: continue
        for s, a, b in zip(z[k], z[f'{prior}__patch_pair_count'], z[f'{prior}__patch_inner_count']): tot[s] = tot.get(s, 0) + int(a); inn[s] = inn.get(s, 0) + int(b)
    return tot, inn
def main():
    cfg(); T = Timer(); FP = footprints(); allc = []; tsum = []; whole = []
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz'); PA = patch_arrays(prior); mi = J.VARIANTS.index('method'); paired = d['paired']
        out4 = np.flatnonzero(paired & (d['nine'] >= 4)); rows = []
        gpid = np.full(len(d['src']), -1); look = {s: i for i, s in enumerate(PA['patch_id'])}; gpid[paired] = [look[s] for s in d['patch_id'][paired]]
        for b in sorted(set(d['building'][out4])):
            ix = out4[d['building'][out4] == b]; k, lab = components(d['xyz'][ix]); fp = FP.get(b)
            inside = contains_xy(fp, d['xyz'][ix, 0], d['xyz'][ix, 1]) if fp is not None else np.zeros(len(ix), bool)
            for c in range(k):
                m = ix[lab == c]; inn = inside[lab == c]; a = area(d['cell'][m]); n9 = np.bincount(d['nine'][m], minlength=9); maj = int(n9.argmax())
                sp = d['s_P'][m]; smv = d['s_M'][m]; pi = gpid[m]
                r = dict(prior=prior, cluster_source='참값 점', building=b, group=d['group'][m][0], n=len(m), area_m2=a, gt_kind=['', '지붕', '벽', '땅'][int(np.bincount(d['gt_kind'][m], minlength=4).argmax())],
                         outside_footprint_pct=100*float((~inn).mean()), hag_median_m=float(np.nanmedian(d['hag'][m])) if 'hag' in d else np.nan, nine_majority=maj,
                         prior_state=['맞음', '틀림', '없음'][int(np.bincount(d['state_P'][m], minlength=3).argmax())], s_P_median_m=float(np.nanmedian(sp)) if np.isfinite(sp).any() else np.nan,
                         image_state=['맞음', '틀림', '없음'][int(np.bincount(d['state_M'][m], minlength=3).argmax())], s_M_median_m=float(np.nanmedian(smv)) if np.isfinite(smv).any() else np.nan,
                         mvs_plane_nmad_median_m=float(np.nanmedian(PA['mvs_nmad'][pi])) if np.isfinite(PA['mvs_nmad'][pi]).any() else np.nan,
                         same_sign_pct=100*float((np.sign(sp) == np.sign(smv))[np.isfinite(sp) & np.isfinite(smv)].mean()) if (np.isfinite(sp) & np.isfinite(smv)).any() else np.nan,
                         sP_minus_sM_median_m=float(np.nanmedian(sp - smv)) if (np.isfinite(sp) & np.isfinite(smv)).any() else np.nan,
                         target_ok_pct=100*float(d['target_ok_v'][mi][m].mean()), texture_median=float(np.nanmedian(PA['texture'][pi])) if np.isfinite(PA['texture'][pi]).any() else np.nan,
                         saturated_pct=np.nan, centre_x=float(d['xyz'][m, 0].mean()), centre_y=float(d['xyz'][m, 1].mean()), centre_z=float(d['xyz'][m, 2].mean()), member_rows=','.join(map(str, m[:5000])) if a >= 1 else '')
                for j, jn in JUD.items(): r[f'method_{jn}_pct'] = 100*float((d['region_v'][mi][m] == j).mean())
                if maj in (6, 7, 8): r['geometry_type'] = TYPES[0] if r['outside_footprint_pct'] > 50 else TYPES[1]
                elif maj == 4: r['geometry_type'] = TYPES[2] if r['same_sign_pct'] >= 50 else TYPES[3]
                elif maj == 5: r['geometry_type'] = TYPES[4]
                rows.append(r)
        # 참값 없는 패치
        tot, inn = inner_counts(prior); has = np.zeros(len(PA['patch_id']), bool); has[np.unique(gpid[paired])] = True
        nog = np.flatnonzero(~has)
        for b in sorted(set(PA['building'][nog])):
            ix = nog[PA['building'][nog] == b]; k, lab = components(PA['centre'][ix])
            for c in range(k):
                m = ix[lab == c]; a = float(PA['area'][m].sum()); ic = np.array([inn.get(s, 0) for s in PA['patch_id'][m]])
                r = dict(prior=prior, cluster_source='참값 없는 패치', building=b, group='', n=len(m), area_m2=a, gt_kind=['', '지붕', '벽'][int(np.bincount(PA['kind'][m], minlength=3).argmax())],
                         inner_truth_patches_pct=100*float((ic > 0).mean()), geometry_type=TYPES[5] if (ic > 0).mean() >= .5 else TYPES[6], mvs_plane_nmad_median_m=float(np.nanmedian(PA['mvs_nmad'][m])) if np.isfinite(PA['mvs_nmad'][m]).any() else np.nan,
                         texture_median=float(np.nanmedian(PA['texture'][m])) if np.isfinite(PA['texture'][m]).any() else np.nan, centre_x=float(PA['centre'][m, 0].mean()), centre_y=float(PA['centre'][m, 1].mean()), centre_z=float(PA['centre'][m, 2].mean()), member_rows='', member_patches=','.join(PA['patch_id'][m[:3000]]) if a >= 1 else '')
                for j, jn in JUD.items(): r[f'method_{jn}_pct'] = 100*float(PA['area'][m][PA['region'][m] == j].sum()/a) if a else np.nan
                rows.append(r)
        df = pd.DataFrame(rows); df['size'] = np.where(df['area_m2'] >= 1, '1 m2 이상', '1 m2 미만'); allc.append(df)
        big = df[df['size'] == '1 m2 이상']
        for tname in TYPES:
            t = big[big['geometry_type'] == tname]
            tsum.append(dict(prior=prior, geometry_type=tname, clusters=len(t), area_m2=float(t['area_m2'].sum()), buildings=int(t['building'].nunique()), target_ok_pct_area_weighted=float(np.average(t['target_ok_pct'], weights=t['area_m2'])) if len(t) and t['target_ok_pct'].notna().any() else np.nan,
                             **{f'method_{jn}_pct_area_weighted': float(np.average(t[f'method_{jn}_pct'].fillna(0), weights=t['area_m2'])) if len(t) else np.nan for jn in JUD.values()}))
        sm = df[df['size'] == '1 m2 미만']; tsum.append(dict(prior=prior, geometry_type='(1 m2 미만 모임, 유형 안 붙임)', clusters=len(sm), area_m2=float(sm['area_m2'].sum()), buildings=int(sm['building'].nunique())))
        for b in sorted(set(d['building'][paired])):
            bm = paired & (d['building'] == b); s = float(np.isin(d['state_P'][bm], [1, 2]).mean())
            if s > .5: whole.append(dict(prior=prior, building=b, group=d['group'][bm][0], gt_points=int(bm.sum()), prior_wrong_or_none_pct=100*s, area_m2=area(d['cell'][bm])))
        print('CLUSTERS', prior, len(df), int((df['size'] == '1 m2 이상').sum()), round(T.mark(prior)), flush=True)
    C = pd.concat(allc, ignore_index=True); C.insert(0, 'cluster_id', np.arange(len(C)))
    C.to_csv(O/'analysis/clusters.csv', index=False)
    write('c5_clusters', C.drop(columns=['member_rows', 'member_patches'], errors='ignore'), note='모임마다의 사실(원인 이름 없음). 1 m2 미만은 size 열로 구분.', md_rows=lambda x: x[x['size'] == '1 m2 이상'].sort_values('area_m2', ascending=False).head(20),
          md_cols=['cluster_id', 'prior', 'cluster_source', 'building', 'area_m2', 'gt_kind', 'geometry_type', 'prior_state', 'image_state', 's_P_median_m', 's_M_median_m'])
    write('c5_geometry_types', pd.DataFrame(tsum), note='기하 유형마다 모임 수·넓이·건물 수·판정 비율·목표 맞음 %(넓이 가중). 원인 이름 없음.')
    write('c5_whole_building_changed', pd.DataFrame(whole), note='참값 점의 절반 넘게가 사전 정보 틀림·없음인 건물.')
    dump(O/'analysis/clusters.json', dict(at=now(), seconds=T.mark('end'), scientific_verdict=None))
if __name__ == '__main__': main()
