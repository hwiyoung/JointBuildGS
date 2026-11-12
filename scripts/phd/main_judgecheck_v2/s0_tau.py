"""단계 0-2: τ (RESCORE-v1 3.1 규칙, 지우기 없음) 탐색 지역마다 + 일곱 지역 합침. 참값 읽지 않음(잔차는 사전 정보 렌더 깊이 - MVS 깊이)."""
from common import *
import importlib.util
spec = importlib.util.spec_from_file_location('tol', HERE/'inherited/rescore_tolerance.py'); tol = importlib.util.module_from_spec(spec); spec.loader.exec_module(tol)
CURRENT = {'B0': (27.175899025518446, 64.25049530044198, 14.737380246492102), 'R2': (24.70203074282035, 39.23140804711729, 21.185600298468488), 'R1': (85.48075853046029, 100.5505581781268, 13.22454981386836)}
def main():
    cfg(); rows = []; vals = {}; pool = {'LoD2_roof': [], 'LoD2_wall': [], 'ALS_roof': []}
    for region in REGIONS:
        vals[region] = {}
        for prior in ['LoD2', 'ALS']:
            p = DR/'s52/s03'/region/prior/'residual_samples.npz'; z = loadz(p)
            for kind in (['roof', 'wall'] if prior == 'LoD2' else ['roof']):
                x = z[kind].astype(float); b = tol.robust_width(x); key = f'{prior}_{kind}'; vals[region][key] = b['width']; pool[key].append(x[np.isfinite(x)])
                rows.append(dict(region=region, key=key, tau_m=b['width'], n=b['n'], median_m=b['median_before'], nmad_m=b['nmad_before'], source=str(p), sha256=sha(p)))
    vals['none'] = {}
    for key, xs in pool.items():
        b = tol.robust_width(np.concatenate(xs)); vals['none'][key] = b['width']
        rows.append(dict(region='none (seven pooled)', key=key, tau_m=b['width'], n=b['n'], median_m=b['median_before'], nmad_m=b['nmad_before'], source='pooled residual_samples of seven regions'))
    check = []
    for region, cur in CURRENT.items():
        for key, c in zip(['LoD2_roof', 'LoD2_wall', 'ALS_roof'], cur):
            check.append(dict(region=region, key=key, current_cm=c, new_cm=100*vals[region][key], equal=abs(100*vals[region][key]-c) < 1e-9))
    dump(O/'stage0/tau.json', dict(values=vals, rows=rows, current_check=check, rule='RESCORE-v1 3.1 robust_width(k=2.5) without trimming', GT_read=False, scientific_verdict=None))
    print(json.dumps({r: {k: round(100*v, 2) for k, v in d.items()} for r, d in vals.items()}))
    print('CHECK', all(c['equal'] for c in check), [(c['region'], c['key'], round(c['new_cm']-c['current_cm'], 12)) for c in check if not c['equal']])
if __name__ == '__main__': main()
