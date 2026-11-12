"""r, σ_W, L, 기하 결과 (발주 2.2, 6.1). 참값 읽지 않음.
  s2_calibrate.py <variant>   variant: base ring_1.0 ring_3.0 z_1.645 z_2.576 centre_shift building_r same_face_ring
일치(정하기용): n>=4, d·u·σ_P 유한, |d| <= 1.96 sqrt(u^2+σ_P^2). r = 탐색 지역 x 사전 정보 x 지붕/벽 중앙값(밖 지역은 일곱 지역 합침).
σ_W = 전 건물 ALS 지붕, 일치 100개 이상 건물의 (중앙값 d - 지역 r)의 NMAD."""
from common import *
import jc2_judge as J
VAR = {'base': dict(ring='R1p5', z=1.96), 'ring_1.0': dict(ring='R1p0', z=1.96), 'ring_3.0': dict(ring='R3p0', z=1.96), 'z_1.645': dict(ring='R1p5', z=1.645),
       'z_2.576': dict(ring='R1p5', z=2.576), 'centre_shift': dict(ring='R1p5', z=1.96, centre=True), 'building_r': dict(ring='R1p5', z=1.96, building_r=True),
       'same_face_ring': dict(ring='face', z=1.96)}
def ring_values(tile, prior, g, ring):
    N = len(g['kind'])
    if ring == 'R1p5':
        b = loadz(O/'ring/base'/f'{tile}__{prior}.npz'); u = b['u_mvs_R1p5'].astype(float)
        sp = b['sigma_P_R1p5'].astype(float) if prior == 'ALS' else g['sigma_P_lod2_m']
    elif ring in ('R1p0', 'R3p0'):
        s = loadz(O/'ring/sens'/f'{tile}__{prior}.npz'); u = s[f'u_mvs_{ring}'].astype(float)
        sp = s[f'sigma_P_{ring}'].astype(float) if prior == 'ALS' else g['sigma_P_lod2_m']
    else:
        s = loadz(O/'ring/face'/f'{tile}__{prior}.npz'); u = s['u_mvs_face'].astype(float)
        sp = s['sigma_P_face'].astype(float) if prior == 'ALS' else g['sigma_P_lod2_m']
    return u, sp
def main(variant):
    cfg(); v = VAR[variant]; T = Timer(); data = []
    for p in sorted((O/'geometry_raw').glob('*__*.npz')):
        tile, prior = p.stem.split('__'); g = loadz(p, ['patch_id', 'kind', 'building', 'region', 'area', 'n', 'd_m', 'sigma_P_lod2_m'])
        u, sp = ring_values(tile, prior, g, v['ring'])
        good = (g['n'] >= 4) & np.isfinite(g['d_m']) & np.isfinite(u) & np.isfinite(sp)
        with np.errstate(invalid='ignore'): agree = good & (np.abs(g['d_m']) <= 1.96*np.hypot(u, sp))
        data.append(dict(tile=tile, prior=prior, g=g, u=u, sp=sp, agree=agree))
    # r per region x prior x kind; none -> pooled seven
    r = {}; rows = []
    for prior in ['LoD2', 'ALS']:
        for kind in ([1, 2] if prior == 'LoD2' else [1]):
            pooled = []
            for reg in REGIONS:
                x = np.concatenate([e['g']['d_m'][e['agree'] & (e['g']['kind'] == kind) & (e['g']['region'] == reg)] for e in data if e['prior'] == prior])
                r[(reg, prior, kind)] = float(np.median(x)) if len(x) else float('nan'); pooled.append(x)
                rows.append(dict(region=reg, prior=prior, kind=kind, agreement_count=len(x), r_m=r[(reg, prior, kind)]))
            x = np.concatenate(pooled); r[('none', prior, kind)] = float(np.median(x)) if len(x) else float('nan')
            rows.append(dict(region='none (seven pooled)', prior=prior, kind=kind, agreement_count=len(x), r_m=r[('none', prior, kind)]))
    # building r (for building_r variant and misalignment table)
    bd = {}
    for e in data:
        g = e['g']
        for kind in np.unique(g['kind']):
            m = e['agree'] & (g['kind'] == kind)
            for b in np.unique(g['building'][m]):
                bd.setdefault((b, e['prior'], int(kind)), []).append(g['d_m'][m & (g['building'] == b)])
    bmed = {k: (float(np.median(np.concatenate(x))), int(sum(len(y) for y in x))) for k, x in bd.items()}
    regof = {}
    for e in data:
        for b, rg in zip(e['g']['building'], e['g']['region']): regof[b] = rg
    resid = []; brows = []
    for (b, prior, kind), (med, cnt) in sorted(bmed.items()):
        rr = r[(regof[b], prior, kind)]; brows.append(dict(building=b, prior=prior, kind=kind, region=regof[b], agreement_count=cnt, median_d_m=med, region_r_m=rr, residual_m=med - rr))
        if prior == 'ALS' and kind == 1 and cnt >= 100: resid.append(med - rr)
    sw = nmad(np.array(resid))
    out = O/'geometry'/variant
    for e in data:
        g = e['g']; N = len(g['kind'])
        rm = np.array([r[(rg, e['prior'], int(k))] for rg, k in zip(g['region'], g['kind'])])
        if v.get('building_r'):
            br = np.array([bmed.get((b, e['prior'], int(k)), (np.nan, 0)) for b, k in zip(g['building'], g['kind'])])
            rm = np.where(br[:, 1] >= 100, br[:, 0], rm)
        root = np.sqrt(e['u']**2 + e['sp']**2 + sw**2)
        if v.get('centre'):
            L = v['z']*root; dd = g['d_m'] - rm
        else:
            L = v['z']*(root + np.abs(rm)); dd = g['d_m']
        geom = J.geometry_code(g['n'], dd, L)
        savez(out/f"{e['tile']}__{e['prior']}.npz", patch_id=g['patch_id'], u_M=e['u'], sigma_P=e['sp'], sigma_W=np.full(N, sw), r_m=rm, L_m=L, d_for_check=dd, geometry=geom, agreement_for_calibration=e['agree'])
    rec = dict(at=now(), variant=variant, rule=v, sigma_W_m=sw, sigma_W_buildings=len(resid), sigma_W_reference_m=0.021387115582349275, r_rows=rows, building_rows=brows,
               building_count_by_region={rg: sum(1 for b in brows if b['prior'] == 'ALS' and b['kind'] == 1 and b['agreement_count'] >= 100 and b['region'] == rg) for rg in REGIONS + ['none']},
               seconds=T.mark('end'), GT_read=False, scientific_verdict=None)
    dump(O/'calib'/f'{variant}.json', rec)
    print('CALIB', variant, 'sigma_W', sw, 'buildings', len(resid)); print(json.dumps([(x['region'], x['prior'], x['kind'], x['agreement_count'], round(100*x['r_m'], 2) if np.isfinite(x['r_m']) else None) for x in rows]))
if __name__ == '__main__': main(sys.argv[1])
