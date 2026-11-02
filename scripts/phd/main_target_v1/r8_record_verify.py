"""Build and test observation-only CUDA changes without optimization steps."""
import sys,os
sys.path.insert(0,'/source');os.environ['MAX_JOBS']='2'
from argparse import ArgumentParser
import numpy as np
import torch
from torch.utils.cpp_extension import load
import diff_surfel_rasterization as raster
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state
from cause_r8_render import ObservedRasterizer
ROOT=OUT/'r8_recorded_continue'
@torch.no_grad()
def main():
    lock=json.loads((CFG/'r8_record_prepare.lock.json').read_text())
    for p,h in lock['files'].items():assert sha(p)==h,p
    src=ROOT/'runtime/rasterizer';build=ROOT/'runtime/build';build.mkdir(exist_ok=False)
    mod=load(name='jbgs_r8_record_guard',sources=[str(src/p) for p in ['cuda_rasterizer/rasterizer_impl.cu','cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','rasterize_points.cu','ext.cpp']],extra_cuda_cflags=['-I'+str(src/'third_party/glm'),'-O3'],extra_cflags=['-O3'],build_directory=str(build),verbose=True)
    assert not mod.jbgs_guard_exceeds(50,100,.5)
    assert mod.jbgs_guard_exceeds(51,100,.5)
    assert not mod.jbgs_guard_exceeds(999,100,-1)
    model=OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model'
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10/scene_LoD2'),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=7000,shuffle=False)
    cams=sorted(scene.getTrainCameras(),key=lambda c:c.image_name);assert len(cams)==203
    pipe=pp.extract(args);bg=torch.zeros(3,device='cuda');original=raster._C;observed=ObservedRasterizer(original);rows=[]
    for i in [0,101,202]:
        cam=cams[i];raster._C=observed;expected=render(cam,g,pipe,bg);baseline=observed.last
        for fraction in [-1,.5]:
            mod.jbgs_set_guard(fraction);raster._C=mod;actual=render(cam,g,pipe,bg)
            keys=[k for k,v in actual.items() if torch.is_tensor(v)]
            for key in keys:assert torch.equal(actual[key],expected[key]),(cam.image_name,fraction,key)
            stats=mod.jbgs_get_guard();assert stats[1]==baseline['total'] and stats[2]==baseline['binning_bytes'] and not stats[5]
            rows.append(dict(camera=cam.image_name,guard=fraction,all_tensor_outputs_byte_equal=True,tile_overlap=stats[1],binning_bytes=stats[2]))
            del actual
        mod.jbgs_set_guard(0)
        try:render(cam,g,pipe,bg);raise AssertionError('guard did not stop')
        except RuntimeError as e:assert 'JBGS_BINNING_GUARD_STOP_BEFORE_ALLOCATION' in str(e)
        assert np.array_equal(mod.jbgs_get_guard_tiles().numpy(),baseline['tiles'])
        assert mod.jbgs_get_guard()[5]==1
        del expected
        print('RECORD_PARITY',cam.image_name,flush=True)
    # Backward and all CUDA math files must remain exact source copies.
    frozen=Path('/opt/geogs-source/submodules/diff-surfel-rasterization')
    changed=[str(p.relative_to(src)) for p in src.rglob('*') if p.is_file() and (frozen/p.relative_to(src)).is_file() and sha(p)!=sha(frozen/p.relative_to(src))]
    assert sorted(changed)==['cuda_rasterizer/rasterizer_impl.cu','ext.cpp'],changed
    result=dict(at=stamp(),status='PASS',strict_half_threshold=True,forced_stop_before_allocation=True,forced_stop_tiles_byte_equal=True,
        renders=rows,changed_cuda_files=changed,backward_code_byte_equal=True,optimization_steps=0,scientific_verdict=None)
    dump(ROOT/'verification/result.json',result)
    files={str(build/'jbgs_r8_record_guard.so'):sha(build/'jbgs_r8_record_guard.so'),str(ROOT/'verification/result.json'):sha(ROOT/'verification/result.json')}
    dump(CFG/'r8_record_runtime.lock.json',dict(at=stamp(),files=files,prepare_lock_sha256=sha(CFG/'r8_record_prepare.lock.json'),scientific_verdict=None))
    print('PASS_RECORDING_PREFLIGHT',flush=True)
if __name__=='__main__':main()
