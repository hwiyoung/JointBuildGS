"""Report-only partition of the existing 0+2 seed fates into cells 0 and 2.
Reuse saved per-seed categories exactly; no geometry, loss or scoring change.
"""
import argparse,json
from pathlib import Path
import numpy as np
from inputs import OUT,save,sha
from fates import model_path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('site');ap.add_argument('prior');ap.add_argument('results',nargs='+');a=ap.parse_args()
    evaluation=OUT/'direct_stage1_v2'/(a.site+'__'+a.prior)/'evaluation.npz'
    with np.load(evaluation) as e:cell=e['cell'];ok=e['in_eval']&e['scoring_allowed'];area=e['area']
    names=['removed','old_place','current_surface','neither']
    for result in a.results:
        base=OUT/'fates'/a.site/(a.prior+'__'+result+'.json');parent=json.loads(base.read_text());assert parent['status']=='PASS'
        saved=base.with_name(base.stem+'__prior_correct_0_2.npz')
        with np.load(saved) as z:sid=z['init_id'];cat=z['category'];last=z['init_last_seen']
        initial=model_path(a.site,result)/'monitor/init_points.npz'
        with np.load(initial) as z:loc=z['location'].astype(np.int64);planted=z['planted'].astype(bool);origin=z['origin']
        locations=loc[planted][sid];assert (locations>=0).all()
        selected_cells=cell[locations];assert np.isin(selected_cells,[0,2]).all()
        dest=OUT/'fate_cell_split'/a.site/base.name;rows={}
        for number in [0,2]:
            mask=selected_cells==number;region=ok&(cell==number)
            seated=(origin==1)&(loc>=0)&region[np.maximum(loc,0)]
            assert int((seated&planted).sum())==int(mask.sum())
            subset=cat[mask];removed_last=last[mask][subset==0]
            rows['cell_'+str(number)]=dict(patches=int(region.sum()),area_m2=float(area[region].sum()),
                seeds_seated=int(seated.sum()),seeds_planted=int(mask.sum()),not_planted=int((seated&~planted).sum()),
                counts={k:int((subset==i).sum()) for i,k in enumerate(names)},
                shares={k:float((subset==i).mean()) if len(subset) else None for i,k in enumerate(names)},
                last_alive_of_removed=dict(zip(['min','median','max'],map(float,np.percentile(removed_last,[0,50,100])))) if len(removed_last) else None)
            dest.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(dest.with_name(dest.stem+'__cell_'+str(number)+'.npz'),init_id=sid[mask],category=subset,init_last_seen=last[mask])
        combined=parent['regions']['prior_correct_0_2']
        for k in names:assert sum(r['counts'][k] for r in rows.values())==combined['counts'][k]
        assert sum(r['seeds_planted'] for r in rows.values())==combined['seeds_planted']
        payload=dict(site=a.site,prior=a.prior,result=result,status='PASS',regions=rows,
            definition=parent['definition'],source_parent=str(base),source_parent_sha256=sha(base),
            source_per_seed=str(saved),source_per_seed_sha256=sha(saved),initial_sha256=sha(initial),evaluation_sha256=sha(evaluation),
            partition_counts_equal_combined=True,categories_reused_without_recomputation=True,scientific_verdict=None)
        save(dest,payload);save(Path('/docs/tables/fate_cell_split')/a.site/dest.name,payload)
        print(result,'cell 0 + cell 2 == combined: PASS',flush=True)

if __name__=='__main__':main()
