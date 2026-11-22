"""Order 3 (scene-wide part): where the pixel weights sit in the training maps (CPU). usage: tp3_weight.py <stem> <run ft|gtt>
Per training view: sigma_ref, target pixels (owner >= 0, weight > 0) and their mean weight, the weight formula check
(weight == clip(sigma_ref/sigma, .1, 10) and == clip((sigma_ref/sigma)^2, .1, 10)), pixels at the upper clip (weight >= 10 - 1e-5) and lower clip
(0 < weight <= 0.1 + 1e-6), split by the owner's method judgment region (FINALTRAIN target judge_region) and the image-depth target pixels
(owner < 0, weight > 0). Writes /tp/weight/<run>_<stem>.json (per view rows and totals)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
from concurrent.futures import ProcessPoolExecutor
G = {}
CLS = [0, 1, 2, 3, 4, 9, -2]   # judgment regions; -2 = image depth target

def one(nm):
    mm = G['views'][nm]; m = loadz(G['maps']/mm['file']); w = m['weight']; o = m['owner']; s = m['sigma']; ref = float(mm.get('sigma_ref', G['ref']))
    t = (o >= 0) & (w > 0); bg = (o < 0) & (w > 0); cls = np.where(o >= 0, G['jreg'][np.clip(o, 0, None)], -2)
    r = dict(view=nm, sigma_ref=ref, target_pixels=int(t.sum()), image_depth_pixels=int(bg.sum()), target_mean_weight=float(w[t].mean()) if t.any() else None,
             target_sigma_median=float(np.median(s[t])) if t.any() else None,
             formula_power1=bool(np.allclose(w[t], np.clip(ref/s[t], .1, 10), atol=1e-5)) if t.any() else None,
             formula_power2=bool(np.allclose(w[t], np.clip((ref/s[t])**2, .1, 10), atol=1e-5)) if t.any() else None,
             image_depth_weights=sorted(set(np.unique(w[bg]).round(6).tolist()))[:5])
    for c in CLS:
        mk = (cls == c) & (w > 0); r[f'n_{c}'] = int(mk.sum()); r[f'hi_{c}'] = int((mk & (w >= 10-1e-5)).sum()); r[f'lo_{c}'] = int((mk & (w <= .1+1e-6)).sum())
        r[f'wsum_{c}'] = float(w[mk].sum())
    return r

def main(stem, run):
    t0 = time.monotonic(); G['maps'] = maps_of(stem, run); idx = json.loads((G['maps']/'index.json').read_text()); G['views'] = idx['views']; G['ref'] = idx.get('sigma_ref')
    G['jreg'] = loadz(FT/'targets'/f'{stem}.npz', ['judge_region'])['judge_region'] if run == 'ft' else np.full(10**6, -1, 'i1')
    with ProcessPoolExecutor(int(os.environ.get('TP_WORKERS', 16))) as ex: rows = list(ex.map(one, list(idx['views']), chunksize=4))
    tot = {k: sum(r[k] for r in rows) for k in rows[0] if k[:2] in ('n_', 'hi', 'lo', 'ws')}
    rec = dict(at=now(), stem=stem, run=run, views=len(rows), index_weight_power=idx.get('weight_power'), index_sigma_ref=idx.get('sigma_ref'), totals=tot,
               sigma_ref_min=min(r['sigma_ref'] for r in rows), sigma_ref_median=float(np.median([r['sigma_ref'] for r in rows])), sigma_ref_max=max(r['sigma_ref'] for r in rows),
               formula_power1_all=all(r['formula_power1'] in (True, None) for r in rows), formula_power2_all=all(r['formula_power2'] in (True, None) for r in rows),
               rows=rows, seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'weight'/f'{run}_{stem}.json', rec); print('TP3', stem, run, json.dumps({k: v for k, v in rec.items() if k != 'rows'}, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
