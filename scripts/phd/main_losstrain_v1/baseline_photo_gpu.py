"""Read-only all-training-view PSNR and the frozen wing view of existing models."""
import json
import sys
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/source')
sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1')
import gpu_s1 as G
from utils.image_utils import psnr

def main():
    site,prior,result=sys.argv[1:]
    assert result in [f'nojudge_{prior}_s0',f'prop_{prior}_s0',f'prop_{prior}_s1']
    dest=Path('/o/photo')/site/result;dest.mkdir(parents=True,exist_ok=False)
    model=Path('/ph/main_stage3_v1/PHD-MAIN-STAGE3-v1/runs')/site/result/'model' if result.startswith('nojudge') else G.model_dir(site,result)
    _,pipe,g,scene=G.load(site,prior,model);rows=[];bg=torch.tensor([0.,0.,0.],device='cuda')
    frozen=json.loads(Path('/repo/configs/phd/main_losstrain_v1/figure_camera_v1.json').read_text())['selected']
    with torch.no_grad():
        for cam in scene.getTrainCameras():
            pkg=G.render(cam,g,pipe,bg);im=pkg['render'].clamp(0,1);gt=cam.original_image[0:3].cuda().clamp(0,1)
            rows.append(dict(view=cam.image_name,psnr_db=float(psnr(im[None],gt[None]).mean())))
            if site=='B173nb_b10' and cam.image_name==frozen['name']:
                for name,arr in [('rgb',im),('photo',gt)]:
                    rgb=(arr.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)
                    G.cv2.imwrite(str(dest/('frozen_'+name+'.png')),G.cv2.cvtColor(rgb,G.cv2.COLOR_RGB2BGR))
                np.savez_compressed(dest/'frozen_depth.npz',depth=pkg['surf_depth'].squeeze(0).cpu().numpy(),alpha=pkg['rend_alpha'].squeeze(0).cpu().numpy())
                (dest/'frozen_render.json').write_text(json.dumps(dict(camera=frozen,model=str(model),iteration=30000,scientific_verdict=None),indent=2)+'\n')
    (dest/'train_quality.json').write_text(json.dumps(dict(site=site,prior=prior,result=result,model=str(model),views=len(rows),
        mean_psnr_db=float(np.mean([x['psnr_db'] for x in rows])),per_view=rows,
        definition='per-image RGB MSE PSNR, arithmetic mean of every training view',optimizer_steps=0,scientific_verdict=None),indent=2)+'\n')
    print(site,prior,result,'photo readout PASS',flush=True)

if __name__=='__main__':main()
