"""Render-only observation of the original CUDA tuple and tile counts; no extension changes."""
import sys,time
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

ROOT=OUT/'r8_lod2_cause'
class ObservedRasterizer:
    def __init__(self,original): self.original=original;self.last=None
    def __getattr__(self,name):return getattr(self.original,name)
    def rasterize_gaussians(self,*args):
        out=self.original.rasterize_gaussians(*args)
        n=int(args[1].shape[0]); geom=out[4];assert geom.data_ptr()%128==0
        offset=0
        # Exact GeometryState::fromChunk order through tiles_touched, types in pinned header.
        for bytes_per_gaussian in [4,3,4,8,36,16,12]:
            offset=(offset+127)//128*128;offset+=n*bytes_per_gaussian
        offset=(offset+127)//128*128
        tiles=geom[offset:offset+n*4].view(torch.int32).cpu().numpy().copy()
        assert int(tiles.astype('i8').sum())==int(out[0]) and tiles.min()>=0
        self.last=dict(total=int(out[0]),tiles=tiles,geom_bytes=out[4].numel(),binning_bytes=out[5].numel(),image_bytes=out[6].numel(),
            geom_tiles_offset=offset,visible_gaussians=int((tiles>0).sum()))
        return out

@torch.no_grad()
def main():
    key=sys.argv[1];config=json.loads((CFG/'cause_r8_lod2.json').read_text());lock=json.loads((CFG/'cause_r8_lod2.lock.r1.json').read_text())
    assert sha(CFG/'cause_r8_lod2.json')==lock['config_sha256']
    for path in [str(Path(__file__)),str(Path(__file__).with_name('cause_r8_inventory.py'))]:assert sha(path)==lock['files'][path]
    row=next(r for r in config['rows'] if r['key']==key);assert sha(row['ply'])==lock['files'][row['ply']]
    for p in Path('/source').rglob('*.py'):
        if '__pycache__' not in p.parts:
            assert sha(p)==lock['files'][row['source']+'/'+str(p.relative_to('/source'))],str(p)
    # The installed extension and the inspected source are bound to the same immutable image.
    original=raster._C;observed=ObservedRasterizer(original)
    dest=ROOT/'renders'/key;dest.mkdir(parents=True,exist_ok=False);(dest/'tiles').mkdir()
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{row["prior"]}'),'-m',row['model'],'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=row['iteration'],shuffle=False)
    pipe=pp.extract(args);assert pipe.depth_ratio==0;bg=torch.zeros(3,device='cuda')
    with np.load(ROOT/'states'/key/'arrays.npz') as a:
        assert np.array_equal(g.init_id.cpu().numpy(),a['init_id'])
        assert np.array_equal(g.get_xyz.cpu().numpy(),a['xyz'],equal_nan=True)
    index=json.loads((OUT/'r7/stage1'/f'B173nb_b10_{row["prior"]}/maps/index.json').read_text())
    cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name)
    assert len(cams)==203 and {c.image_name for c in cams}==set(index['views'])
    summaries=[]
    for i,cam in enumerate(cams):
        torch.cuda.reset_peak_memory_stats();start=time.monotonic();raster._C=observed
        pkg=render(cam,g,pipe,bg);torch.cuda.synchronize();record=observed.last;tiles=record.pop('tiles')
        depth=pkg['surf_depth'].squeeze().cpu().numpy();alpha=pkg['rend_alpha'].squeeze().cpu().numpy()
        savedpath=Path(row['renders'])/(cam.image_name+'.npz')
        with np.load(savedpath) as saved:
            assert np.array_equal(depth,saved['depth'],equal_nan=True),('depth replay',key,cam.image_name)
            alpha_saved='alpha' in saved
            if alpha_saved:assert np.array_equal(alpha,saved['alpha'],equal_nan=True),('alpha replay',key,cam.image_name)
        if i==0:
            raster._C=original;check=render(cam,g,pipe,bg)
            for name in ['render','surf_depth','rend_alpha','rend_dist','rend_normal']:
                assert torch.equal(pkg[name],check[name]),('observer parity',name)
            del check
        path=dest/'tiles'/(cam.image_name+'.npz');np.savez_compressed(path,tiles=tiles)
        record.update(camera=cam.image_name,index=i,width=cam.image_width,height=cam.image_height,
            camera_center=cam.camera_center.cpu().tolist(),tile_sha256=sha(path),saved_render_sha256=sha(savedpath),
            depth_byte_equal=True,alpha_byte_equal=True if alpha_saved else None,
            alpha_note=None if alpha_saved else 'Previous baseline30 depth archive has no alpha; unmodified forward observer parity verified on first view',
            peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),seconds=time.monotonic()-start)
        summaries.append(record);dump(dest/'progress.json',dict(key=key,completed=len(summaries),views=203,last=record,scientific_verdict=None))
        if i%20==0:print('RENDER_LOAD',key,i+1,203,record['total'],flush=True)
        del pkg,depth,alpha,tiles
    dump(dest/'summary.json',dict(at=stamp(),key=key,views=summaries,top5=sorted(summaries,key=lambda r:(-r['total'],r['camera']))[:5],
         gpu=torch.cuda.get_device_name(),extension=str(original.__file__),extension_sha256=sha(original.__file__),
         optimization_steps=0,original_cuda_unmodified=True,first_view_observer_parity=True,scientific_verdict=None))
    print('RENDER_LOAD_COMPLETE',key,flush=True)

if __name__=='__main__':main()
