"""Reuse unchanged stage-1 post/render/floater/virtual-mesh functions on lt_* outputs.

Mount this task's runs as /out/stage1 and original stage-1 defs as /out/defs (ro).
The successful attempt's model is read; post/gpu outputs belong to its run root.
"""
import json
import sys
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1')
import gpu_s1 as G

def model_dir(site,result):
    root=Path('/out/stage1')/site/result
    record=json.loads((root/'PASS.json').read_text())
    return root/f"attempt_{record['attempt']}"/'model'

def main():
    mode,site,result,prior=sys.argv[1:]
    assert result.startswith('lt_') and mode in ['post','run']
    G.model_dir=model_dir;G.scene_prior=lambda s,r:prior
    if mode=='post':
        execution=Path('/repo/configs/phd/main_losstrain_v1/post_execution_v1.json')
        if execution.exists() and json.loads(execution.read_text())['tsdf_execution']=='spatial_tiles_same_geometry':
            import tiled_post
            original=G.GaussianExtractor.extract_mesh_bounded
            def bounded(ext, **kwargs):
                return tiled_post.extract(ext,G.box_of(site),Path('/out/stage1')/site/result/'post/tiled_tsdf',
                                          site,result,prior,**kwargs)
            G.GaussianExtractor.extract_mesh_bounded=bounded
            try:G.post(site,result)
            finally:G.GaussianExtractor.extract_mesh_bounded=original
        else:G.post(site,result)
        torch.cuda.empty_cache()
        from utils.image_utils import psnr
        _,pipe,g,scene=G.load(site,prior,model_dir(site,result))
        rows=[];bg=torch.tensor([0.,0.,0.],device='cuda')
        frozen=json.loads(Path('/repo/configs/phd/main_losstrain_v1/figure_camera_v1.json').read_text())['selected']
        with torch.no_grad():
            for cam in scene.getTrainCameras():
                pkg=G.render(cam,g,pipe,bg)
                im=pkg['render'].clamp(0,1);gt=cam.original_image[0:3].cuda().clamp(0,1)
                rows.append(dict(view=cam.image_name,psnr_db=float(psnr(im[None],gt[None]).mean())))
                if site=='B173nb_b10' and cam.image_name==frozen['name']:
                    directory=Path('/out/stage1')/site/result/'post'
                    rgb=(im.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)
                    photo=(gt.permute(1,2,0).cpu().numpy()*255).astype(np.uint8)
                    G.cv2.imwrite(str(directory/'frozen_rgb.png'),G.cv2.cvtColor(rgb,G.cv2.COLOR_RGB2BGR))
                    G.cv2.imwrite(str(directory/'frozen_photo.png'),G.cv2.cvtColor(photo,G.cv2.COLOR_RGB2BGR))
                    np.savez_compressed(directory/'frozen_depth.npz',depth=pkg['surf_depth'].squeeze(0).cpu().numpy(),alpha=pkg['rend_alpha'].squeeze(0).cpu().numpy())
                    (directory/'frozen_render.json').write_text(json.dumps(dict(camera=frozen,model=str(model_dir(site,result)),iteration=30000,scientific_verdict=None),indent=2)+'\n')
        dest=Path('/out/stage1')/site/result/'post/train_quality.json'
        dest.write_text(json.dumps(dict(views=len(rows),mean_psnr_db=float(np.mean([x['psnr_db'] for x in rows])),per_view=rows,
            definition='per-image RGB MSE PSNR, arithmetic mean of every training view',scientific_verdict=None),indent=2)+'\n')
    else:G.run_steps(site,result)

if __name__=='__main__':
    try:
        from post_admission import admit
        from post_memory_policy import policy_for
        mode,site,result,_=sys.argv[1:]
        with admit(Path('/out/stage1')/site/result/(mode+'_resource_admission.json'),minimum_gib=policy_for(Path('/o'))['host_available_GiB']):
            main()
    except torch.cuda.OutOfMemoryError:
        import subprocess
        _,site,result,_=sys.argv[1:]
        frames=[];tb=sys.exc_info()[2]
        while tb is not None:frames.append(tb.tb_frame);tb=tb.tb_next
        cams=[f.f_locals[k] for f in frames for k in ['cam','viewpoint_camera'] if k in f.f_locals]
        gs=[f.f_locals[k] for f in frames for k in ['g','pc'] if k in f.f_locals and hasattr(f.f_locals[k],'get_xyz')]
        # The failing rasterization may not return radii; do not use another view.
        record=dict(stage=sys.argv[1],iteration=30000,view=getattr(cams[-1],'image_name',None) if cams else None,
            gaussians=len(gs[-1].get_xyz) if gs else None,radii_p99=None,radii_max=None,
            radii_unavailable_reason='failing render/postprocessing did not return a verified current-view radii array',
            torch_allocated_bytes=torch.cuda.memory_allocated(),torch_reserved_bytes=torch.cuda.memory_reserved(),
            torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            nvidia_smi=subprocess.run(['nvidia-smi'],capture_output=True,text=True).stdout,scientific_verdict=None)
        (Path('/out/stage1')/site/result/(sys.argv[1]+'_oom.json')).write_text(json.dumps(record,indent=2)+'\n')
        raise
