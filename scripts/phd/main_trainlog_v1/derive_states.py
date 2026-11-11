"""Derive PROCFIG-v1 npz columns for every saved in-scope state (order 2.2), CPU.
Same rules as scripts/phd/main_procfig_v1/measure.py; group33 from PROCFIG work/patch_groups.npz (GT-selected display groups)."""
import sys
from common import *
sys.path.insert(0, str(R))
from src.phd.prior_propagation_v6.orientation import axes_of_quat as quat_to_axes
from shapely.geometry import shape
import shapely

def scope_mask(P, c):
    p = shape(c['scope']['buffered_footprint'])
    return shapely.contains_xy(p, P[:, 0], P[:, 1]) & (P[:, 2] >= c['scope']['z_min']) & (P[:, 2] <= c['scope']['z_max'])

def inputs(c):
    t = loadz(FT/'targets'/f'{STEM}.npz'); s = loadz(FT/'stage1'/STEM/'seeds.npz')
    valid = np.flatnonzero((t['region'] >= 0) & np.isfinite(t['target']).all(1) & np.isfinite(t['normal']).all(1) & np.isfinite(t['sigma']) & (t['sigma'] > 0))
    group = loadz(PF/'work/patch_groups.npz', ['group'])['group']; bg = s['origin'] == 0
    seedgroup = np.zeros(len(s['origin']), 'i1'); seedgroup[~bg] = group[s['patch'][~bg]]; seedgroup[~scope_mask(s['xyz'], c)] = 0
    return t, s, valid, group, seedgroup

def derive(z, t, s, valid, seedgroup, up):
    g = dict(z); axes = quat_to_axes(g['rotation']); g['normal'] = axes[2].astype('f4'); wall = abs(g['normal'] @ up) < .5
    n = len(g['xyz']); current = np.full(n, -1, 'i8'); att = g['target_tag'] == 1; current[att] = valid[g['target_index'][att]]
    judge = np.full(n, -1, 'i1'); judge[att] = t['judge_region'][current[att]]
    h = np.full(n, np.nan); sigma = h.copy(); tx = np.full((n, 3), np.nan, 'f4'); jj = current[att]
    h[att] = np.sum((g['xyz'][att].astype(float)-t['target'][jj].astype('f4'))*t['normal'][jj].astype('f4'), axis=1)
    sigma[att] = t['sigma'][jj].astype('f4'); tx[att] = t['target'][jj]
    g.update(current_patch=current, initial_patch=s['patch'][g['init_id']], judgment=judge, group33=seedgroup[g['init_id']], wall=wall,
             target_xyz=tx, target_sigma=sigma.astype('f4'), normal_offset=h.astype('f4'))
    return {k: (v.astype('f4') if np.issubdtype(v.dtype, np.floating) else v) for k, v in g.items()}

def main(root=None):
    c = cfg(); root = Path(root) if root else O/'runs'/SITE/RUN/'attempt1/model/trainlog'
    t, s, valid, group, seedgroup = inputs(c); up = np.array(c['coordinates']['up']); out = root.parent.parent.parent/'derived'/'gaussians'
    saves = [json.loads(l) for l in (root/'saves.jsonl').read_text().splitlines()]; rec = []
    for sv in saves:
        z = loadz(root/'states'/f'{sv["name"]}.npz'); d = derive(z, t, s, valid, seedgroup, up)
        savez(out/f'{sv["name"]}.npz', **d)
        rec.append(dict(name=sv['name'], iteration=sv['iteration'], n=len(d['xyz']), wall=int(d['wall'].sum()), wrong_lineage=int((d['group33'] == 1).sum()), sha256=sha(out/f'{sv["name"]}.npz')))
        print('DERIVED', sv['name'], len(d['xyz']), flush=True)
    dump(out.parent/'derived_receipt.json', dict(at=now(), states=rec, rules='PROCFIG-v1 measure.py columns; group33 = PROCFIG work/patch_groups.npz group[seeds.patch], 0 for background and seeds outside scope at 0', scientific_verdict=None))
if __name__ == '__main__': main(*sys.argv[1:])
