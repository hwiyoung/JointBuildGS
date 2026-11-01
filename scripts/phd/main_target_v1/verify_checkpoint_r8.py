"""Recount saved 7000 evidence on CPU; no optimization or criterion changes."""
import sys
import numpy as np
from common import *

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def main():
    prior=sys.argv[1];iteration=int(sys.argv[2]);assert iteration in [7000,15000,30000];site='B173nb_b10';run=OUT/'r8/runs'/f'tg_{site}_{prior}_s0_r8';model=run/'model'
    root=model/f'check{iteration}';coverage=json.loads((root/'coverage.json').read_text())
    maps=OUT/'r8/stage1'/f'{site}_{prior}'/'maps';index=json.loads((maps/'index.json').read_text())
    target=loadz(OUT/'r7/targets'/f'{site}_{prior}.npz')
    totals={};hashes={};roundoff=0;views=[]
    assert {v['camera'] for v in coverage['views']}==set(index['views'])
    for v in coverage['views']:
        name=v['camera'];p=root/'renders'/f'{name}.npz';m=loadz(maps/index['views'][name]['file']);a=loadz(p)
        assert sha(maps/index['views'][name]['file'])==index['views'][name]['sha256']
        good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
        rendered=np.isfinite(a['depth'])&(a['depth']>0)
        hit=good&rendered&(np.abs(a['depth']-m['depth'])<=np.float32(1.96)*m['sigma'])
        hit64=good&rendered&(np.abs(a['depth'].astype('f8')-m['depth'].astype('f8'))<=1.96*m['sigma'].astype('f8'))
        roundoff+=int((hit!=hit64).sum())
        assert int(hit.sum())==v['inside'] and int(good.sum())==v['target_pixels']
        owner=m['owner'];patch=np.maximum(owner,0);has=owner>=0
        masks=[('all',good),('prior',good&has),('background',good&~has),
            ('prior_roof',good&has&(target['kind'][patch]==1)),('prior_wall',good&has&(target['kind'][patch]==2))]
        masks += [(f'region_{i}',good&has&(target['region'][patch]==i)) for i in [0,5,1,2,3]]
        masks += [(label,good&has&(target['any_replaced'][patch]==flag)) for label,flag in [('prior_original',False),('prior_replaced',True)]]
        for label,sel in masks:
            row=totals.setdefault(label,dict(target_pixels=0,inside=0,missing=0))
            row['target_pixels']+=int(sel.sum());row['inside']+=int((sel&hit).sum());row['missing']+=int((sel&~rendered).sum())
        # Origin channels background, released and patch partition rendered alpha.
        f=a['origin_fraction'];vis=a['alpha']>1e-5
        assert np.isfinite(f).all() and ((f>=0)&(f<=1)).all()
        assert np.max(np.abs(f[vis].sum(1)-1),initial=0)<2e-4
        assert np.isfinite(a['near_origin_fraction']).all()
        assert np.max(a['near_origin_fraction']-f,initial=0)<2e-4
        hashes[name]=sha(p);views.append(dict(camera=name,inside=int(hit.sum()),target_pixels=int(good.sum())))
    assert totals['all']['inside']==coverage['inside'] and totals['all']['target_pixels']==coverage['target_pixels']
    for row in totals.values():
        n=row['target_pixels'];row['fraction']=row['inside']/n if n else None;row['missing_fraction']=row['missing']/n if n else None
    assert totals['all']['fraction']==coverage['fraction']
    s=loadz(model/f'target_monitor/snapshot_{iteration}.npz');initial=loadz(model/'target_monitor/snapshot_0.npz')
    ids=s['init_id'];assert ((ids>=0)&(ids<len(s['anchor']))).all()
    assert np.array_equal(s['origin'],initial['origin'][ids])
    for key in ['anchor','normal','sigma','region','initial_scale','initial_large_background']:assert np.array_equal(s[key],initial[key],equal_nan=True)
    large=s['initial_large_background'][ids];desc=loadz(root/'large_background_descendants.npz');summary=json.loads((root/'large_background_descendants.json').read_text())
    for key in ['init_id','xyz','scale','opacity']:assert np.array_equal(desc[key],s[key][large])
    ancestors,counts=np.unique(ids[large],return_counts=True)
    assert summary['surviving_gaussians']==int(large.sum()) and summary['surviving_original_ancestors']==len(ancestors)
    assert summary['counts_by_ancestor']==dict(zip(map(str,ancestors.tolist()),counts.tolist()))
    assert summary['initial_large_background_count']==int(s['initial_large_background'].sum())
    bound=s['target_tag']==1;ix=s['target_index'][bound]
    delta=s['xyz'][bound].astype('f8')-s['patch_anchor'][ix].astype('f8');normal=s['patch_normal'][ix].astype('f8')
    excess=np.abs((delta*normal).sum(1))-(np.float32(1.96)*s['patch_sigma'][ix]).astype('f8')
    assert np.isfinite(s['xyz']).all() and float(excess.max(initial=0))<=3e-5
    assert ((s['target_tag']==0)==(s['origin']==0)).all()
    assert (s['target_released_at'][s['target_tag']==2]>=0).all()
    assert (s['target_released_at'][s['target_tag']==1]==-1).all()
    # Snapshot precedes scheduled densification; do not substitute it for absent health_7000.
    six=json.loads((OUT/'r8/runs'/f'tg_{site}_{prior}_s0_r8/model/target_monitor/health_6000.json').read_text());opacity=np.sort(s['opacity'])[(len(ids)-1)//2]
    curve=[json.loads(line) for line in (model/'target_monitor/curve.jsonl').read_text().splitlines()]
    health=dict(state=f'saved {iteration} model before scheduled densification',gaussians=len(ids),count_at_6000=six['gaussians'],
        count_ratio=len(ids)/six['gaussians'],opacity_torch_median=float(opacity),prior_opacity_numpy_median=float(np.median(s['opacity'][s['origin']==1])),
        max_normal_excess_m=float(excess.max(initial=0)),logged_loss_finite=all(np.isfinite(r['loss']) for r in curve),last_logged_iteration=curve[-1]['iteration'],
        scheduled_post_densification_health_available=(model/f'target_monitor/health_{iteration}.json').exists())
    record=dict(at=stamp(),status='PASS_R8_SAVED_EVIDENCE_RECOUNT',iteration=iteration,prior=prior,views=len(views),coverage=coverage['fraction'],
        strata=totals,float64_comparison_roundoff_pixels=roundoff,snapshot_health=health,
        ancestry_array_identity=True,render_sha256=hashes,snapshot_sha256=sha(model/f'target_monitor/snapshot_{iteration}.npz'),
        coverage_sha256=sha(root/'coverage.json'),scientific_verdict=None)
    dump(run/f'verification{iteration}.json',record);dump(DOC/'tables'/f'continue_r7_verification{iteration}_{prior}.json',record)
    print('SAVED_EVIDENCE_PASS',prior,coverage['fraction'],flush=True)

if __name__=='__main__':main()
