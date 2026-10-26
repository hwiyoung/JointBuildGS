"""Development pilot diagnostics, no truth-dependent decisions."""
from common import *
from run_measure import selected_geometry
def main():
    rows=[]
    for prior in ['LoD2','ALS']:
        gg=[];ss=[]
        for t in load(W/'inputs/tiles.json'):
            f=O/'work/pilot'/f'{t["id"]}__{prior}_selection.npz'
            if f.exists():
                g,_=selected_geometry('pilot',t['id'],prior);gg.append(g);ss.append(npz(f))
        g={k:np.concatenate([v[k] for v in gg]) for k in gg[0]};s={k:np.concatenate([v[k] for v in ss]) for k in ss[0]}
        for b in EXAMPLES:
            m=(g['building']==b)&(g['kind']==1);rows.append(dict(prior=prior,building=b,points=int(m.sum()),valid_geometry=int(g['geometry_valid'][m].sum()),at_least_three_views=int((s['selected_count'][m]>=3).sum()),angle_normal_z_median=float(np.median(g['normal'][m,2])) if m.any() else None))
    benchmark=[]
    for f in sorted((O/'benchmark').glob('*.npz')):
        d=npz(f);m=(abs(d['mvs_p'])<.05)&(d['raw_u_mvs']<.03)&(d['texture']>=5)&(d['selected_count']>=3)
        benchmark.append(dict(file=f.name,points=len(m),gate_eligible=int(m.sum()),within10cm=int((m&(abs(d['h_max'])<=.100001)).sum()),texture_median=np.nanmedian(d['texture']),finite_curve_fraction=np.isfinite(d['curve'][:,:141]).mean(),hmax_abs_median=np.nanmedian(abs(d['h_max']))))
    dump(O/'pilot_inventory.json',dict(rows=rows,benchmark=benchmark));print(json.dumps(clean(dict(rows=rows,benchmark=benchmark)),ensure_ascii=False))
if __name__=='__main__':main()
