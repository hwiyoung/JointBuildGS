"""Score frozen baseline depths against exactly the r7 pixel targets, CPU only."""
import sys
import numpy as np
from common import *
from verify7000_r7 import loadz
def main():
    prior=sys.argv[1];run=OUT/'r7_continue/post'/f'base_{prior}_30000';root=OUT/'r5/baselines'/f'depth_{prior}';maps=OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps'
    ix=json.loads((maps/'index.json').read_text());render=json.loads((root/'coverage.json').read_text());render['views']=render['views'][prior];t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');totals={};views=[]
    assert {v['camera'] for v in render['views']}==set(ix['views'])
    for v in render['views']:
        name=v['camera'];rp=root/'renders'/f'{name}.npz';mp=maps/ix['views'][name]['file'];assert sha(rp)==v['sha256'] and sha(mp)==ix['views'][name]['sha256']
        a=loadz(rp);m=loadz(mp);good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0);has=m['owner']>=0;j=np.maximum(m['owner'],0)
        valid=np.isfinite(a['depth'])&(a['depth']>0);inside=good&valid&(abs(a['depth']-m['depth'])<=np.float32(1.96)*m['sigma'])
        masks=[('all',good),('prior',good&has),('background',good&~has),('prior_roof',good&has&(t['kind'][j]==1)),('prior_wall',good&has&(t['kind'][j]==2))]
        masks += [(f'region_{i}',good&has&(t['region'][j]==i)) for i in [0,5,1,2,3]]
        masks += [(label,good&has&(t['any_replaced'][j]==flag)) for label,flag in [('prior_original',False),('prior_replaced',True)]]
        for key,mask in masks:
            row=totals.setdefault(key,dict(target_pixels=0,inside=0,missing=0));row['target_pixels']+=int(mask.sum());row['inside']+=int((mask&inside).sum());row['missing']+=int((mask&~valid).sum())
        views.append(dict(camera=name,target_pixels=int(good.sum()),inside=int(inside.sum()),missing=int((good&~valid).sum())))
    for row in totals.values():
        n=row['target_pixels'];row.update(fraction=row['inside']/n if n else None,missing_fraction=row['missing']/n if n else None)
    assert totals['all']['target_pixels']==totals['prior']['target_pixels']+totals['background']['target_pixels']
    result=dict(at=stamp(),status='PASS_BASELINE_SAME_R7_PIXEL_TARGETS',prior=prior,iteration=30000,strata=totals,views=views,map_index_sha256=sha(maps/'index.json'),render_receipt_sha256=sha(root/'coverage.json'),scientific_verdict=None)
    dump(run/'coverage.json',result);dump(DOC/'tables'/f'continue_r7_baseline30k_coverage_{prior}.json',result);print('BASELINE_COVERAGE',prior,totals['all'],flush=True)
if __name__=='__main__':main()
