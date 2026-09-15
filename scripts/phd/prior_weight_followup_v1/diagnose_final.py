"""CPU comparison of frozen final depth maps; descriptive input fit only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from PIL import Image

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(x):
    x=np.asarray(x,dtype=np.float64); a=np.abs(x)
    return dict(n=x.size,mae=float(a.mean()),median=float(np.median(a)),p95=float(np.quantile(a,.95)),
                within_10cm=float((a<=.1).mean()),over_1m=float((a>1).mean()),over_10m=float((a>10).mean())) if x.size else dict(n=0)

def main():
    assert Path('/.dockerenv').exists()
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);args=ap.parse_args()
    cfg=read(args.config);p=Path('/payload');out=Path('/out');v=p/cfg['viewer'];b=p/cfg['bundle']
    sys.path.insert(0,'/repo/src/phd/geogs_mvs_pgsr_v1')
    from mvs_depth import load_view_depth
    m=read(v/'prior_weights_v1/manifest.json')
    result=dict(scientific_verdict=None,scope='Same valid training-view pixels; camera-Z expected depth, not independent surface accuracy',
                source_sha256=sha(__file__),config_sha256=sha(args.config),inputs={},views=[])
    def record(path):result['inputs'][str(path)]=sha(path);return path
    for region in ['P1','P2','P3']:
        run=b/region;rc=read(record(run/'config.json'));gate=read(record(run/'gate.json'));assert gate['status']=='PASS'
        root=p/cfg['mvs_root']/region;binding=read(record(root/'bindings.json'))
        assert sha(root/'bindings.json')==rc['binding_sha256']
        masks=read(record(run/'mask/manifest.json')) if region!='P1' else None
        r=next(x for x in m['regions'] if x['id']==region)
        for view in r['views']:
            if view['split']!='train':continue
            name=view['image_name'];camera=next(x for x in binding['train'] if x['name']==name)
            target,valid,_=load_view_depth(camera,verify_rgb=False,depth_path=record(root/camera['local_depth']))
            mp=run/'mask/r1_mask.npz' if region=='P1' else run/'mask'/next(x['path'] for x in masks['views'] if x['camera']==Path(name).stem)
            labels=np.load(record(mp))['region_id'];pred={}
            for role,key in [('old','alpha_4'),('new','prior_0005_alpha4')]:
                item=view['conditions'][key];png=v/item['rgb']['url'].removeprefix('/data/')
                path=png.parent.parent/'vis'/('depth_'+png.stem+'.tiff')
                assert sha(path)==item['source_depth_sha256'];pred[role]=np.asarray(Image.open(record(path)),dtype=np.float32)
            if region=='P1':
                paths=list((p/cfg['global_root']).glob('evaluation/attempt.*/extractions/P1.mvs.D0005_Pnative/model/train/ours_30000/vis/depth_00000.tiff'))
                if len(paths)==1:pred['historical_global']=np.asarray(Image.open(record(paths[0])),dtype=np.float32)
            prior_path=p/cfg['base_root']/f'inputs/{region}/prior/raw_depth/{Path(name).stem}.npy'
            prior=cv2.resize(np.load(record(prior_path)),(camera['width'],camera['height']),interpolation=cv2.INTER_LINEAR)
            common=valid & np.logical_and.reduce([np.isfinite(x)&(x>0) for x in pred.values()])
            row=dict(region=region,camera=name,subsets={})
            for label in [1,2,3]:
                s=common&(labels==label);both=s&np.isfinite(prior)&(prior>0)
                row['subsets']['R'+str(label)]=dict(valid_input=int((valid&(labels==label)).sum()),
                    missing_by_condition={k:int((valid&(labels==label)&(~np.isfinite(x)|(x<=0))).sum()) for k,x in pred.items()},
                    fit_mvs={k:stats(x[s]-target[s]) for k,x in pred.items()},
                    fit_prior={k:stats(x[both]-prior[both]) for k,x in pred.items()},
                    change=stats(pred['new'][s]-pred['old'][s]))
            result['views'].append(row)
            # Figures show the exact fixed masks and signed change at their original pixels.
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            rgb=np.asarray(Image.open(v/view['original']['url'].removeprefix('/data/')))
            fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
            axes[0].imshow(rgb);axes[0].contour(labels==1,levels=[.5],colors=['red'],linewidths=.5)
            axes[0].set_title(region+' '+Path(name).stem[-6:]+' / R1 outline')
            a=axes[1].imshow(np.where(common,pred['new']-pred['old'],np.nan),vmin=-1,vmax=1,cmap='coolwarm')
            axes[1].set_title('New - old expected depth (m; clipped +/-1)');fig.colorbar(a,ax=axes[1],shrink=.7)
            a=axes[2].imshow(np.where(common,np.abs(pred['new']-target)-np.abs(pred['old']-target),np.nan),vmin=-1,vmax=1,cmap='coolwarm')
            axes[2].set_title('Change of |GS - MVS| (blue = smaller)');fig.colorbar(a,ax=axes[2],shrink=.7)
            for ax in axes:ax.axis('off')
            fig.savefig(out/(region+'_'+Path(name).stem[-6:]+'.png'),dpi=140);plt.close(fig)
    result.update(runtime=cfg['runtime'],python=sys.version,numpy=np.__version__,opencv=cv2.__version__)
    (out/'response.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    for r in result['views']:
        s=r['subsets']['R1'];print(r['region'],r['camera'],'MVS',s['fit_mvs'],'change',s['change'])

if __name__=='__main__':main()
