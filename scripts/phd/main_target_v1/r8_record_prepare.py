"""Prepare observation-only runtime copies; never modify frozen r22 or its checkpoint."""
import shutil,difflib,torch
from common import *
R=OUT/'r8_recorded_continue'
CPP=r'''
// PHD-MAIN-TARGET-v1: observation and pre-allocation stop only.
#include <stdexcept>
#include <vector>
static double jbgs_guard_fraction = -1.0;
static std::vector<int64_t> jbgs_guard_values(6, 0);
static std::vector<int> jbgs_guard_tile_values;
void jbgs_set_guard(double fraction) { jbgs_guard_fraction = fraction; }
std::vector<int64_t> jbgs_get_guard() { return jbgs_guard_values; }
int* jbgs_guard_tile_data() { return jbgs_guard_tile_values.data(); }
int64_t jbgs_guard_tile_size() { return jbgs_guard_tile_values.size(); }
bool jbgs_guard_exceeds(int64_t bytes, int64_t free, double fraction) {
    return fraction >= 0 && double(bytes) > fraction * double(free);
}
'''
CHECK=r'''
    size_t jbgs_free, jbgs_total;
    CHECK_CUDA(cudaMemGetInfo(&jbgs_free, &jbgs_total), debug);
    bool jbgs_stop = jbgs_guard_exceeds(binning_chunk_size, jbgs_free, jbgs_guard_fraction);
    jbgs_guard_values = {int64_t(P), int64_t(num_rendered), int64_t(binning_chunk_size),
                         int64_t(jbgs_free), int64_t(jbgs_total), int64_t(jbgs_stop)};
    if (jbgs_stop) {
        jbgs_guard_tile_values.resize(P);
        CHECK_CUDA(cudaMemcpy(jbgs_guard_tile_values.data(), geomState.tiles_touched,
                             P * sizeof(uint32_t), cudaMemcpyDeviceToHost), debug);
        throw std::runtime_error("JBGS_BINNING_GUARD_STOP_BEFORE_ALLOCATION");
    }
'''
EXT=r'''
void jbgs_set_guard(double fraction);
std::vector<int64_t> jbgs_get_guard();
int* jbgs_guard_tile_data();
int64_t jbgs_guard_tile_size();
bool jbgs_guard_exceeds(int64_t bytes, int64_t free, double fraction);
torch::Tensor jbgs_get_guard_tiles() {
    return torch::from_blob(jbgs_guard_tile_data(), {jbgs_guard_tile_size()},
           torch::TensorOptions().dtype(torch::kInt32).device(torch::kCPU)).clone();
}
'''
def main():
    R.mkdir(exist_ok=False);runtime=R/'runtime';runtime.mkdir()
    src=Path('/opt/geogs-source/submodules/diff-surfel-rasterization');dst=runtime/'rasterizer'
    shutil.copytree(src,dst,ignore=shutil.ignore_patterns('build','*.so','__pycache__','.git'))
    p=dst/'cuda_rasterizer/rasterizer_impl.cu';old=p.read_text();new=old.replace('// Forward rendering procedure for differentiable rasterization',CPP+'\n// Forward rendering procedure for differentiable rasterization')
    needle='\tsize_t binning_chunk_size = required<BinningState>(num_rendered);'
    assert new.count(needle)==1;new=new.replace(needle,needle+'\n'+CHECK);p.write_text(new)
    diffs=[''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original/rasterizer_impl.cu',tofile='recording/rasterizer_impl.cu'))]
    p=dst/'ext.cpp';old=p.read_text();new=old.replace('PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {',EXT+'\nPYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {\n  m.def("jbgs_set_guard", &jbgs_set_guard);\n  m.def("jbgs_get_guard", &jbgs_get_guard);\n  m.def("jbgs_get_guard_tiles", &jbgs_get_guard_tiles);\n  m.def("jbgs_guard_exceeds", &jbgs_guard_exceeds);')
    assert new!=old;p.write_text(new);diffs.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original/ext.cpp',tofile='recording/ext.cpp')))
    p=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r22/train.py';old=p.read_text();new=old.replace('import jbgs_state','import jbgs_state\nimport r8_record_hooks as recording',1)
    needle='    for iteration in range(first_iter, opt.iterations + 1):'
    assert new.count(needle)==1;new=new.replace(needle,needle+'\n        recording.begin_iteration(locals())')
    needle='        render_pkg = render(viewpoint_cam, gaussians, pipe, background)'
    assert new.count(needle)==1;new=new.replace(needle,'        render_pkg = recording.training_render(locals(), render, viewpoint_cam, gaussians, pipe, background)')
    (runtime/'train_recorded.py').write_text(new);diffs.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='r22/train.py',tofile='runtime/train_recorded.py')))
    (runtime/'recording_only.patch').write_text('\n'.join(diffs))
    checkpoint=OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8/model/jbgs_complete/iteration_7000/checkpoint.pth'
    saved=torch.load(checkpoint,map_location='cpu');assert saved['iteration']==7000
    config=dict(task_id='PHD-MAIN-TARGET-v1',at=stamp(),authority='2026-11-02 user: continue r8 LoD2 with records and guard',
        original_revision='r8',source='/repo/src/phd/forks/GeoGS-conf-guided-v1-r22',checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint),
        model=str(R/'runs/tg_B173nb_b10_LoD2_s0_r8/model'),save_iterations=[6000,7000]+list(range(8000,15001,1000))+[30000],
        capture_iterations=[7000]+list(range(8000,15001,1000))+[30000],additional_readout_suppressed=list(range(8000,15000,1000)),
        pre_densification_gradient='after add_densification_stats and immediately before densify_and_prune at8000..14000; snapshot-time accumulator at15000/30000 where densification is disabled',
        every100='both pre-training-forward and after-iteration counts by4 provenance x4 horizontal x4 height; forward overlap and exact BinningState bytes; GPU memory',
        provenance=['background','patch','released_at100_descendants','other_released'],
        boundaries=str(OUT/'r8_lod2_cause/boundaries.json'),boundary_sha256=sha(OUT/'r8_lod2_cause/boundaries.json'),
        guard=dict(fraction=.5,strict_greater=True,free='cudaMemGetInfo device free immediately before BinningState allocation; cached reserved bytes not added',
            scope='every forward, including ordinary scheduled evaluation; unchanged CUDA math and backward',automatic_retry=False),
        health='original TargetR8.observe unchanged, including3x n6000 every1000 and opacity reset grace',
        densify_grad_threshold=saved['optimization']['densify_grad_threshold'],
        count_at_6000=saved['target_r6']['n6000'],training_ends=30000,other_six='NOT_STARTED',scientific_verdict=None)
    dump(CFG/'r8_record_continue.json',config)
    files={str(p):sha(p) for p in runtime.rglob('*') if p.is_file()}
    for p in Path(__file__).parent.glob('r8_record_*.py'):files[str(p)]=sha(p)
    oldlock=json.loads((CFG/'target_v1.runtime.r8.lock.json').read_text())
    for p,h in oldlock['files'].items():assert sha(REPO/p)==h;files[str(REPO/p)]=h
    files[str(checkpoint)]=config['checkpoint_sha256'];files[config['boundaries']]=config['boundary_sha256']
    for p in [CFG/'target_v1.r8.json',CFG/'target_v1.runtime.r8.lock.json',CFG/'r8_record_continue.json']:files[str(p)]=sha(p)
    dump(CFG/'r8_record_prepare.lock.json',dict(at=stamp(),files=files,image='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be',scientific_verdict=None))
    print('R8_RECORD_PREPARED',config['checkpoint_sha256'],flush=True)
if __name__=='__main__':main()
