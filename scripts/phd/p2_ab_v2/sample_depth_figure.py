"""Scientific same-pixel diagnostic figure, without changing any image/depth source."""
import argparse
from pathlib import Path
import platform
import shutil
import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.phd.p2_ab_v2.sample_build import read,write,record


def run(config_path):
    cfg=read(config_path);root=Path(cfg['artifact_root']);out=root/cfg['output_relative_root'];out.mkdir(parents=True,exist_ok=False)
    common=root/cfg['common_relative_root'];views={v['image_id']:v for v in read(common/'views.json')['views']}
    source_manifest=read(common/'sample_manifest.json');inputs=[record(common/'sample_manifest.json'),record(common/'views.json')];outputs=[]
    for iid in cfg['image_ids']:
        view=views[iid];src=root/cfg['global_audit_relative_root']/f'view_{iid}_global_comparison.npz';inputs.append(record(src));inputs.append(record(view['path'],view['sha256']))
        source=np.load(src);rgb=cv2.cvtColor(cv2.imread(view['path']),cv2.COLOR_BGR2RGB)
        scale=min(1,cfg['display_maximum_dimension_px']/max(rgb.shape[:2]));height,width=[int(round(x*scale)) for x in rgb.shape[:2]]
        rgb=cv2.resize(rgb,(width,height),interpolation=cv2.INTER_AREA);K=np.array(view['K']);K[0]*=width/view['width'];K[1]*=height/view['height']
        yy,xx=np.mgrid[:height,:width];p=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@(source['K_depth']@np.linalg.inv(K)).T
        uv=(p[...,:2]/p[...,2:3]).astype(np.float32)
        mapped={}
        for key in ['p2_mvs_z','global_mvs_z','colmap_z']:
            a=source[key].copy();a[~np.isfinite(a)|(a<=0)]=np.nan
            mapped[key]=cv2.remap(a,uv[...,0],uv[...,1],cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=float('nan'))
        support=np.isfinite(mapped['p2_mvs_z']);front=support&np.isfinite(mapped['global_mvs_z'])&(mapped['global_mvs_z']+cfg['foreground_gap_display_m']<mapped['p2_mvs_z'])
        pool=np.concatenate([a[support&np.isfinite(a)] for a in mapped.values()]);vmin,vmax=np.percentile(pool,cfg['depth_display_percentiles'])
        fig,axes=plt.subplots(1,4,figsize=(18,5),layout='constrained')
        axes[0].imshow(rgb);axes[0].contour(support.astype(float),levels=[.5],colors='white',linewidths=.6);axes[0].contour(front.astype(float),levels=[.5],colors='red',linewidths=.7)
        axes[0].set_title('Original RGB crop\nwhite: P2 projection, red: global foreground')
        for ax,key,label in zip(axes[1:],mapped,['P2-only MVS','Global native MVS','COLMAP geometric depth']):
            a=np.where(support,mapped[key],np.nan);im=ax.imshow(a,cmap='viridis',vmin=vmin,vmax=vmax);ax.set_title(label+'\nsame camera-Z scale / same crop pixels')
        for ax in axes:ax.set_axis_off()
        fig.colorbar(im,ax=axes[1:],shrink=.7,label='Camera Z (m); white = absent or outside P2 projection')
        fig.suptitle(f'View {iid}: P2 is a bounded surface; nearer scene geometry may occlude it. Development diagnostic only.',fontsize=12)
        dest=out/f'view_{iid}_depth_context.png';fig.savefig(dest,dpi=140);plt.close(fig);outputs.append(record(dest));print(dest,flush=True)
    write(out/'figure_receipt.json',{'task_id':cfg['task_id'],'scientific_verdict':None,'inputs':inputs,'outputs':outputs,
         'config':record(config_path),'source':record(__file__),'git_commit':source_manifest['git_commit'],'docker_image_id':source_manifest['docker_image_id'],
         'versions':{'python':platform.python_version(),'numpy':np.__version__,'opencv':cv2.__version__,'matplotlib':matplotlib.__version__},
         'reference_accessed':False,'display_only':True,'selection_or_depth_correction_performed':False})
    for p in [Path(__file__),config_path]:shutil.copyfile(p,out/p.name)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);run(Path(parser.parse_args().config))
