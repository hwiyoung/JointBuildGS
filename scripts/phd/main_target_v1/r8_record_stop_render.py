"""Inference-only 203-view load measurement of the saved stop state; no optimizer."""
import sys,gc
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
import diff_surfel_rasterization as raster
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from common import *
from r8_record_hooks import load_extension
from cause_r8_render import ObservedRasterizer
ROOT=OUT/'r8_recorded_continue'
@torch.no_grad()
def main():
    lock=json.loads((CFG/'r8_record_diagnostics.lock.json').read_text())
    assert sha(__file__)==lock['files'][__file__]
    stop=json.loads((ROOT/'STOP_LoD2.json').read_text());src=Path(stop['stop_dir']);dest=ROOT/'stop_diagnostic/renders';dest.mkdir(exist_ok=False);(dest/'tiles').mkdir()
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    original=OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model'
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',str(original),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False)
    g.load_ply(str(src/'point_cloud.ply'));pipe=pp.extract(args);bg=torch.zeros(3,device='cuda')
    a=np.load(ROOT/'stop_diagnostic/arrays.npz');group=a['group'];assert np.array_equal(g.get_xyz.cpu().numpy(),a['xyz']);a.close()
    # Saved-state inference has no Adam/gradient tensors. This is a capacity check
    # for readout allocation only; the stopped training guard remains exactly .5.
    mod=load_extension();observed=ObservedRasterizer(mod);raster._C=observed;mod.jbgs_set_guard(.95)
    cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name);assert len(cams)==203;rows=[];cross=[]
    for i,cam in enumerate(cams):
        torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
        try:
            pkg=render(cam,g,pipe,bg);record=observed.last;tiles=record['tiles'];rendered=True
            if cam.image_name==stop['camera']:
                np.savez_compressed(dest/'stopped_camera_render.npz',rgb=pkg['render'].cpu().numpy(),depth=pkg['surf_depth'].cpu().numpy(),alpha=pkg['rend_alpha'].cpu().numpy())
            del pkg
        except RuntimeError as error:
            if 'JBGS_BINNING_GUARD_STOP_BEFORE_ALLOCATION' not in str(error):raise
            tiles=mod.jbgs_get_guard_tiles().numpy();rendered=False
        stats=mod.jbgs_get_guard();assert int(tiles.astype('i8').sum())==stats[1]
        if cam.image_name==stop['camera'] and (src/'guard_tiles.npz').exists():
            with np.load(src/'guard_tiles.npz') as saved:assert np.array_equal(tiles,saved['tiles'])
        grouped=np.bincount(group,weights=tiles,minlength=64).astype('i8');assert int(grouped.sum())==stats[1]
        path=dest/'tiles'/(cam.image_name+'.npz');np.savez_compressed(path,tiles=tiles)
        row=dict(view_index=i,camera=cam.image_name,overlaps=stats[1],binning_bytes=stats[2],free_bytes_before_binning=stats[3],full_render_completed=rendered,
            measurement='exact original CUDA preprocessing and tile sum; full forward' if rendered else 'exact original CUDA preprocessing and tile sum; binning not allocated due to readout capacity check (95 percent free)',
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),tile_sha256=sha(path))
        rows.append(row)
        for j in range(64):cross.append(dict(camera=cam.image_name,tag=j//16,xy_bin=j%16//4,height_bin=j%4,overlaps=int(grouped[j])))
        dump(dest/'progress.json',dict(completed=i+1,total=203,last=row,scientific_verdict=None))
        if i%20==0:print('STOP_RENDER_LOAD',i+1,stats[1],rendered,flush=True)
        del tiles;gc.collect()
    dump(dest/'summary.json',dict(at=stamp(),views=rows,top5=sorted(rows,key=lambda r:(-r['overlaps'],r['camera']))[:5],full_renders=sum(r['full_render_completed'] for r in rows),exact_tile_measurements=203,optimization_steps=0,
        readout_allocation_capacity_fraction=.95,training_guard_fraction_unchanged=.5,stopped_view_individual_tiles_replayed=True,scientific_verdict=None))
    dump(dest/'cross.json',dict(rows=cross,scientific_verdict=None));print('STOP_RENDER_COMPLETE',flush=True)
if __name__=='__main__':main()
