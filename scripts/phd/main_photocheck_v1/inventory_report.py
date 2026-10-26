"""Geometry/distribution accounting, without publishing sealed classifications."""
import argparse
from common import *
from evaluate import write_table,join
def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);a=ap.parse_args();rows=[];excluded=[]
    for prior in ['LoD2','ALS']:
        d,p=join(prior,a.stage);roof=p['kind']==1
        for k in ['patch_count','selected_count','eligible_images','parallax','texture']:
            v=p[k][roof].astype(float);area=p['area'][roof];valid=np.isfinite(v)
            rows.append(dict(prior=prior,measure=k,points=len(v),finite_points=int(valid.sum()),missing_points=int((~valid).sum()),area_m2=area.sum(),missing_area_m2=area[~valid].sum(),min=float(np.min(v[valid])) if valid.any() else None,q25=float(np.quantile(v[valid],.25)) if valid.any() else None,median=float(np.median(v[valid])) if valid.any() else None,q75=float(np.quantile(v[valid],.75)) if valid.any() else None,max=float(np.max(v[valid])) if valid.any() else None))
        counts=[]
        for count in np.unique(p['patch_count'][roof]):
            m=roof&(p['patch_count']==count);counts.append(dict(prior=prior,patches_per_point=int(count),points=int(m.sum()),patches=int(p['patch_count'][m].sum()),area_m2=p['area'][m].sum()))
        write_table(prior+'_point_group_counts',counts,a.stage)
        fallback=[]
        for f in (O/'geometry').glob(f'*__{prior}.json'):
            rec=load(f)
            for r in rec['surface_audit']:
                if r['tangent_fallback']:fallback.append(dict(prior=prior,tile=rec['tile'],**r))
        write_table(prior+'_grid_fallback',fallback,a.stage)
        # The previous export excludes unassigned records before roof/wall public export;
        # preserve exactly its all-kind count rather than inventing a roof-only split.
        previous=[]
        for f in (W/'holdout/internal/patch_geometry').glob(f'*_{prior}.json'):
            r=load(f);previous.append(r)
        excluded.append(dict(prior=prior,source='W/holdout/internal/patch_geometry/*.json: aggregate unassigned input support only',patches=sum(r['unmatched_count'] for r in previous),area_m2=sum(r['unmatched_area_m2'] for r in previous),kind_scope='all inherited kinds; roof-only excluded split unavailable',included_in_current_points=False))
    write_table('point_distributions',rows,a.stage);write_table('inherited_unassigned',excluded,a.stage);print('distribution and exclusion tables complete',a.stage)
if __name__=='__main__':main()
