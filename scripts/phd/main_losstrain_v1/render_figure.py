"""9.3: one frozen photo pose, fixed crop, and prior-only camera-depth colour range."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
from inputs import OUT,PRIORS,save,sha
from side_tables import VARS
from result_figures import LABELS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prior',choices=PRIORS,required=True);a=ap.parse_args();site='B173nb_b10'
    cp=Path('/config/figure_camera_v1.json');cfg=json.loads(cp.read_text());cam=cfg['selected']
    x0,y0,x1,y1=cam['crop_xyxy_px'];crop=(int(np.floor(x0)),int(np.floor(y0)),int(np.ceil(x1)),int(np.ceil(y1)))
    depths=(np.array(cfg['box_prior_only_xyz'])@np.array(cam['R']).T+np.array(cam['t']))[:,2]
    lo,hi=float(depths.min()),float(depths.max())
    items=[('판정 끔',OUT/'photo'/site/f'nojudge_{a.prior}_s0')]
    items += [(LABELS[v],OUT/'runs'/site/f'{v}_{a.prior}_s0/post') for v in VARS if (OUT/'runs'/site/f'{v}_{a.prior}_s0/post/frozen_depth.npz').exists()]
    assert all((p/'frozen_depth.npz').exists() for _,p in items),'baseline frozen view must be measured first'
    fig,axs=plt.subplots(2,len(items)+1,figsize=(3.0*(len(items)+1),5.5),squeeze=False)
    records=[];cmap=plt.get_cmap('viridis').copy();cmap.set_bad('#dddddd')
    for i,(name,path) in enumerate(items):
        meta=json.loads((path/'frozen_render.json').read_text());assert meta['camera']['name']==cam['name']
        rgb=np.asarray(Image.open(path/'frozen_rgb.png').convert('RGB'))[crop[1]:crop[3],crop[0]:crop[2]]
        with np.load(path/'frozen_depth.npz') as z:depth=z['depth'][crop[1]:crop[3],crop[0]:crop[2]].astype(float)
        depth[(depth<=0)|~np.isfinite(depth)]=np.nan
        axs[0,i].imshow(rgb);im=axs[1,i].imshow(depth,cmap=cmap,vmin=lo,vmax=hi)
        axs[0,i].set_title(name);records.append(dict(name=name,root=str(path),render_metadata=meta,
            rgb_sha256=sha(path/'frozen_rgb.png'),depth_sha256=sha(path/'frozen_depth.npz')))
    photo=items[0][1]/'frozen_photo.png';image=np.asarray(Image.open(photo).convert('RGB'))[crop[1]:crop[3],crop[0]:crop[2]]
    axs[0,-1].imshow(image);axs[0,-1].set_title('같은 시점 학습 사진');axs[1,-1].text(.5,.5,'사진에는 깊이 값 없음',ha='center',va='center',transform=axs[1,-1].transAxes)
    for ax in axs.ravel():ax.set_xticks([]);ax.set_yticks([])
    axs[0,0].set_ylabel('색');axs[1,0].set_ylabel('시선 깊이')
    title=f'B173 날개 · {a.prior}: 같은 사진 시점에서 색과 깊이를 비교한다'
    fig.suptitle(title,x=.035,ha='left',fontsize=13)
    fig.text(.04,.02,f'{cam["name"]} · {crop[2]-crop[0]}×{crop[3]-crop[1]} 화소 · 깊이 색 범위 {lo:.2f}–{hi:.2f} m · 회색: 깊이 없음',fontsize=9)
    fig.subplots_adjust(top=.87,bottom=.12,left=.035,right=.96,wspace=.06,hspace=.05)
    bar=fig.colorbar(im,ax=axs[1,:-1],orientation='horizontal',fraction=.04,pad=.02);bar.set_label('카메라에서 표면까지 깊이 (m)')
    dest=Path('/docs/figures');key='render_B173nb_b10_'+a.prior;fig.savefig(dest/(key+'.png'),dpi=300);plt.close(fig)
    save(dest/(key+'.json'),dict(title=title,camera_source=str(cp),camera_sha256=sha(cp),camera=cam,crop_xyxy=crop,
        depth_range_m=[lo,hi],depth_range_rule='camera-z extrema of the prior-only ROI box frozen before training; unchanged across arms',
        panels=records,photo=str(photo),photo_sha256=sha(photo),visual_review='PENDING',scientific_verdict=None))
    print(key,'written',flush=True)

if __name__=='__main__':main()
