"""단계 0-1: 건물 목록, 묶음, 탐색 지역, 정합 이동, 자료 연결 확인 (참값 읽지 않음)."""
from common import *
from matplotlib.path import Path as MPath
SHIFT = np.array([690953.0, 5336071.0])
def regions():
    out = {}
    for r in REGIONS:
        j = json.loads((DR/'s02'/r/'range.json').read_text())
        s = json.loads((DR/'s52/s03'/r/'ALS/summary.json').read_text())['registration']['shift_applied']
        sl = json.loads((DR/'s52/s03'/r/'LoD2/summary.json').read_text())['registration']['shift_applied']
        out[r] = dict(polygon_local=j['polygon_local'], area_m2=j.get('area_m2'), als_shift=s, lod2_shift=sl)
    return out
def patches(tile, prior, keys):
    parts = []
    for split, root in [('development', W/'patch_values'), ('holdout', W/'holdout/patch_values')]:
        p = root/f'{tile}__{prior}__R1.5.npz'
        if p.exists():
            z = loadz(p, keys); z['split'] = np.full(len(z[keys[0]]), split); parts.append(z)
    if not parts: return None
    return {k: np.concatenate([q[k] for q in parts]) for k in parts[0]}
def main():
    T = Timer(); reg = regions(); paths = {r: MPath(np.asarray(v['polygon_local'])) for r, v in reg.items()}
    lod2 = json.loads((W/'inputs/lod2_buildings.json').read_text()); split = json.loads((W/'building_split.json').read_text())
    holdout = set(split['holdout']); dev = set(split['development'])
    keys = ['patch_id', 'building', 'kind', 'area', 'raw_centre', 'centre', 'holdout']
    B = {}; tiles_rows = []
    for tile in tiles():
        for prior in ['LoD2', 'ALS']:
            z = patches(tile, prior, keys)
            if z is None: continue
            xy = z['raw_centre'][:, :2]; inreg = np.stack([paths[r].contains_points(xy) for r in REGIONS], 1)
            moved = np.linalg.norm(z['centre'] - z['raw_centre'], axis=1) > 0
            tiles_rows.append(dict(tile=tile, prior=prior, patches=len(xy), widen0_moved=int(moved.sum()), unattached=int((z['building'] == '').sum())))
            for b in np.unique(z['building']):
                m = z['building'] == b; e = B.setdefault(str(b), dict(LoD2_patches=0, ALS_patches=0, LoD2_area=0., ALS_area=0., LoD2_roof_area=0., LoD2_wall_area=0., region_area={r: 0. for r in REGIONS}, tiles=set()))
                e[f'{prior}_patches'] += int(m.sum()); e[f'{prior}_area'] += float(z['area'][m].sum()); e['tiles'].add(tile)
                if prior == 'LoD2':
                    e['LoD2_roof_area'] += float(z['area'][m & (z['kind'] == 1)].sum()); e['LoD2_wall_area'] += float(z['area'][m & (z['kind'] == 2)].sum())
                for k, r in enumerate(REGIONS): e['region_area'][r] += float(z['area'][m & inreg[:, k]].sum())
    unatt = B.pop('', None)
    # 세 실험 지역의 평가 범위에 걸친 건물 = JUDGEAPPLY 핵심점(평가 범위 패치)의 건물
    exp_b = {}
    for site in SITES:
        for prior in ['LoD2', 'ALS']:
            z = loadz(JA/'core_points'/f'{site}__{prior}.npz', ['building'])
            for b in set(z['building'].tolist()) - {''}: exp_b.setdefault(b, set()).add(site)
    rows = []
    for b, e in sorted(B.items()):
        ra = e['region_area']; best = max(REGIONS, key=lambda r: ra[r]); region = best if ra[best] > 0 else 'none'
        both = e['LoD2_patches'] > 0 and e['ALS_patches'] > 0
        rows.append(dict(building=b, in_scope=both, group='experiment' if b in exp_b else 'rest', experiment_sites=sorted(exp_b.get(b, [])),
                         old_split='holdout' if b in holdout else 'development' if b in dev else 'none', search_region=region,
                         region_area_m2=ra, LoD2_patches=e['LoD2_patches'], ALS_patches=e['ALS_patches'], LoD2_area_m2=e['LoD2_area'], ALS_area_m2=e['ALS_area'],
                         LoD2_roof_area_m2=e['LoD2_roof_area'], LoD2_wall_area_m2=e['LoD2_wall_area'], tiles=sorted(e['tiles']),
                         als_shift_m=reg[region]['als_shift'] if region != 'none' else [0., 0., 0.]))
    sc = [r for r in rows if r['in_scope']]
    summ = dict(at=now(), buildings_total=len(rows), in_scope=len(sc), LoD2_only=[r['building'] for r in rows if r['LoD2_patches'] and not r['ALS_patches']],
                ALS_only=[r['building'] for r in rows if r['ALS_patches'] and not r['LoD2_patches']], unattached_patches=unatt and dict(LoD2=unatt['LoD2_patches'], ALS=unatt['ALS_patches'], LoD2_area=unatt['LoD2_area'], ALS_area=unatt['ALS_area']),
                experiment_buildings=sorted(r['building'] for r in sc if r['group'] == 'experiment'), experiment_from_JA=sorted(exp_b),
                region_counts={r: sum(x['search_region'] == r for x in sc) for r in REGIONS + ['none']},
                none_region=dict(buildings=[x['building'] for x in sc if x['search_region'] == 'none'], LoD2_area_m2=sum(x['LoD2_area_m2'] for x in sc if x['search_region'] == 'none'), ALS_area_m2=sum(x['ALS_area_m2'] for x in sc if x['search_region'] == 'none')),
                regions=reg, tiles=tiles_rows, seconds=T.mark('end'), GT_read=False, scientific_verdict=None)
    dump(O/'stage0/buildings.json', dict(rows=rows, summary=summ))
    print(json.dumps({k: summ[k] for k in ['buildings_total', 'in_scope', 'LoD2_only', 'ALS_only', 'unattached_patches', 'experiment_buildings', 'region_counts']}, ensure_ascii=False))
    print('NONE', summ['none_region']); print('EXPJA', summ['experiment_from_JA'])
if __name__ == '__main__': main()
