"""Review saved pair evidence and add conditional-residual maps, without rerunning MVS."""
import hashlib,json,sys,warnings
from pathlib import Path
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm
sys.path.insert(0,'/repo/scripts/phd/prior_weight_followup_v1')
from build_depth_evidence import stats,median
O=Path('/out');P=Path('/payload');cfg=json.loads((O/'config.json').read_text())
assert Path('/.dockerenv').exists()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((O/'manifest.json').read_text());manifest['parent_manifest_sha256']=sha(O/'manifest.json');manifest['review_script_sha256']=sha(__file__)
checks=[]
for c in manifest['cases']:
    folder=O/c['id'];d=dict(np.load(folder/'maps.npz'));pairs=np.load(folder/'pairs.npz');names=pairs['source_names'];zs=pairs['z_residual'];rt=pairs['roundtrip_rgb_px'];angle=pairs['ray_angle_deg']
    binding=json.loads((P/cfg['global']/'inputs_v2'/c['region']/'bindings.json').read_text());train={v['name'] for v in binding['train']};ref=next(v for v in binding['train'] if v['name']==c['camera'])
    assert c['camera'] not in names and len(set(names))==len(names)
    shape=tuple(d['shape']);valid=d['valid'];labels=d['labels'];depth=d['depth'];prior=d['prior'];rgb_uv=np.floor(d['rgb_uv']+.5).astype(int)
    photo_path=P/cfg['base']/('inputs/'+c['region']+'/scene/images/'+c['camera']);photo=np.asarray(Image.open(photo_path).convert('RGB'))[np.clip(rgb_uv[:,1],0,ref['height']-1),np.clip(rgb_uv[:,0],0,ref['width']-1)].reshape(*shape,3)
    for pool in cfg['source_pools']:
        sel=np.array([n in train for n in names]) if pool=='regional_train' else np.ones(len(names),bool)
        z=zs[sel];roundtrip=rt[sel];angles=angle[sel];known=np.isfinite(z)
        prefix=pool+'__';support=known&(np.abs(z)<=cfg['primary_depth_tolerance_m'])&(roundtrip<=cfg['roundtrip_tolerance_rgb_px'])
        assert np.array_equal(support.sum(0),d[prefix+'support']);assert np.array_equal(known.sum(0),d[prefix+'available'])
        matched=median(np.where(support,np.abs(z),np.nan));d[prefix+'consistent_median_abs_z']=matched
        for subset,row in c['pools'][pool]['subsets'].items():
            mask=valid if subset=='all_valid' else valid&(labels==int(subset[1:]));row['metrics']['consistent_median_abs_z']=stats(matched[mask])
        target=valid&(labels==1);coverage=support[:,target].mean(1)
        c['pools'][pool]['R1_source_coverage']={str(q):int((coverage>=q).sum()) for q in [.05,.1,.5]}
        panels=[('Photo / R1 cyan, R2 green',photo,None,0,1,False),('MVS camera-Z (m)',depth,'viridis',None,None,False),('Available other-depth count\nnonlinear count scale',d[prefix+'available'],'viridis',0,300,True),('Consistent other-view count\nnonlinear count scale',d[prefix+'support'],'viridis',0,100,True),('Median |residual| of CONSISTENT views (m)\nconditional on 0.25m and 2px gates',matched,'magma',0,.25,False),('Max consistent ray angle (degrees)',d[prefix+'max_supported_angle'],'viridis',0,120,False),('Possible occluder count\nnonlinear count scale',d[prefix+'occlusion_candidates'],'magma',0,250,True),('Median |residual| of ALL available views (m)\nincludes occlusion; not accuracy',d[prefix+'median_abs_z'],'magma',0,60,False),('MVS - prior camera-Z (m)\nnot source authority',np.where(valid&(prior>0),depth-prior,np.nan),'coolwarm',-5,5,False)]
        fig,axes=plt.subplots(3,3,figsize=(16,13),constrained_layout=True)
        for ax,(title,values,cmap,lo,hi,log) in zip(axes.flat,panels):
            if cmap is None:ax.imshow(values)
            else:
                cm=plt.get_cmap(cmap).copy();cm.set_bad('#c6cbd2');arr=np.where(valid,values,np.nan).reshape(shape)
                if log:
                    im=ax.imshow(arr,cmap=cm,norm=SymLogNorm(linthresh=1,vmin=lo,vmax=hi));bar=fig.colorbar(im,ax=ax,shrink=.7);bar.set_ticks([0,1,5,20,100]+([hi] if hi>100 else []))
                else:im=ax.imshow(arr,cmap=cm,vmin=lo,vmax=hi);fig.colorbar(im,ax=ax,shrink=.7)
            for k,color in [(1,'cyan'),(2,'lime')]:
                mask=(labels==k).reshape(shape)
                if mask.any() and not mask.all():ax.contour(mask,levels=[.5],colors=[color],linewidths=.45)
            ax.set_title(title,fontsize=10);ax.axis('off')
        fig.suptitle(c['id']+' / '+pool+' / input-only diagnostics',fontsize=14);fig.savefig(folder/(pool+'_review.png'),dpi=125);plt.close(fig)
        # Complementary boundary map remains visible separately from agreement diagnostics.
        fig,ax=plt.subplots(figsize=(8,6),constrained_layout=True);cm=plt.get_cmap('magma').copy();cm.set_bad('#c6cbd2');im=ax.imshow(np.where(valid,d['boundary_jump'],np.nan).reshape(shape),cmap=cm,vmin=0,vmax=1);fig.colorbar(im,ax=ax,label='4-neighbor native depth jump (m, display capped at 1m)');ax.set_title(c['id']+' / genuine edges can also have high depth jumps');ax.axis('off')
        if pool=='regional_train':fig.savefig(folder/'boundary.png',dpi=120)
        plt.close(fig)
    np.savez_compressed(folder/'review_maps.npz',**d)
    c.update(figure_suffix='_review',maps_file='review_maps.npz',summary_file='review_summary.json',review_maps_sha256=sha(folder/'review_maps.npz'))
    (folder/'review_summary.json').write_text(json.dumps(c,ensure_ascii=False,indent=2,allow_nan=False))
    checks.append(dict(case=c['id'],pair_count=len(names),recomputed_counts_match=True,no_self_view=True,train_excludes_evaluation=True))
    print(c['id'],{p:{'median_support':c['pools'][p]['subsets']['R1']['metrics']['support']['median'],'zero_support_fraction':c['pools'][p]['subsets']['R1']['zero_support_fraction'],'matched_residual_median':c['pools'][p]['subsets']['R1']['metrics']['consistent_median_abs_z']['median'],'cover_10pct':c['pools'][p]['R1_source_coverage']['0.1']} for p in cfg['source_pools']},flush=True)
manifest['review_note']='Counts use nonlinear display scales. Matched residual is conditional on the diagnostic 0.25m/2px gate; not calibrated confidence. Original all-view residuals and figures are preserved.'
(O/'review_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False))
(O/'validation.json').write_text(json.dumps(dict(status='PASS_SAVED_PAIR_REVIEW',checks=checks,scientific_verdict=None),indent=2))
