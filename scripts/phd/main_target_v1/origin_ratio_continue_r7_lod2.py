"""Requested contribution-weighted draw share and outside-pixel max-contributor share."""
import sys
import numpy as np
from common import *
from verify7000_r7 import loadz
def main():
    prior=sys.argv[1];iteration=int(sys.argv[2]);run=OUT/'r7_continue/lod2_retry/runs'/f'tg_B173nb_b10_{prior}_s0_r7';maps=OUT/'r7/stage1'/f'B173nb_b10_{prior}/maps';ix=json.loads((maps/'index.json').read_text());fail=json.loads((OUT/'r7_continue/failures'/f'{prior}_{iteration}'/'summary.json').read_text())
    contribution=np.zeros(3);normalized=np.zeros(3);n=0;alpha=0.;views=[]
    for name,meta in sorted(ix['views'].items()):
        m=loadz(maps/meta['file']);a=loadz(run/f'model/check{iteration}/renders'/f'{name}.npz');sel=(m['owner']>=0)&np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
        f=a['origin_fraction'][sel].astype('f8');w=a['alpha'][sel].astype('f8');assert np.isfinite(f).all() and np.isfinite(w).all()
        c=(f*w[:,None]).sum(0);contribution+=c;normalized+=f.sum(0);n+=int(sel.sum());alpha+=float(w.sum());views.append(dict(camera=name,prior_pixels=int(sel.sum()),alpha_sum=float(w.sum()),alphaT_sum=c.tolist()))
    assert n==fail['totals']['prior_pixels'];assert abs(contribution.sum()-alpha)<=max(1e-3,alpha*3e-5)
    counts=np.asarray(fail['cross_counts']).sum(0);outside=fail['totals']['outside'];wrong=np.array([counts[2],counts[3],counts[0]+counts[1]])
    rows=[]
    for i,label in enumerate(['background','released','patch']):
        draw=contribution[i]/contribution.sum() if contribution.sum() else None;bad=wrong[i]/outside if outside else None
        rows.append(dict(origin=label,alphaT_sum=float(contribution[i]),draw_share=float(draw) if draw is not None else None,outside_max_pixels=int(wrong[i]),outside_max_share=float(bad) if bad is not None else None,wrong_share_over_draw_share=float(bad/draw) if draw else None,mean_alpha_normalized_contribution=float(normalized[i]/n) if n else None))
    result=dict(at=stamp(),iteration=iteration,prior=prior,status='PASS_CONTRIBUTION_DENOMINATORS',rows=rows,building_target_pixels=n,total_alpha_sum=alpha,outside_pixels=outside,unavailable_max_pixels=int(counts[4]),views=views,definition='draw=sum(alpha*T) on valid prior-owner target pixels, normalized across current tags; wrong=outside-width max-contributor pixels / all outside-width prior pixels; ratio=wrong share/draw share',scientific_verdict=None)
    dump(run/f'origin_ratio_{iteration}.json',result);dump(DOC/'tables'/f'continue_r7_origin_ratio_{prior}_{iteration}.json',result);print('ORIGIN_RATIO',prior,rows,flush=True)
if __name__=='__main__':main()
