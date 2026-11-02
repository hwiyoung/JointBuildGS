"""Original recorded memory and source-code allocation relation, without causal verdict."""
import numpy as np
from common import *
ROOT=OUT/'r8_lod2_cause'
def main():
    inv=json.loads((ROOT/'inventory.json').read_text());rows=[]
    for b in inv['baseline']:
        p=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{b["prior"]}_s0/receipt.json';r=json.loads(p.read_text())
        rows.append(dict(prior=b['prior'],gaussians_30000=b['gaussians_30000'],gpu_index=r['gpu'],gpu_model='확인 불가: original receipt and trace have index only',
            gpu_memory_used_mib=r['gpu_memory_used_mib'],peak_cuda_allocated_GiB=b['memory']['peak_cuda_allocated_bytes']/2**30,
            peak_cuda_reserved_GiB=b['memory']['peak_cuda_reserved_bytes']/2**30,started_at=r['started_at'],finished_at=r['finished_at'],
            sources=b['sources'],note='nvidia-smi sampled device used memory versus cumulative PyTorch peak counters are separate measurements'))
    render=[]
    for p in sorted((ROOT/'renders').glob('*/summary.json')):
        r=json.loads(p.read_text());render.extend([dict(state=r['key'],camera=v['camera'],N=v['total'],B=v['binning_bytes']) for v in r['views']])
    assert len(render)==2436
    ratios=np.array([r['B']/r['N'] for r in render]);rho=float(np.median(ratios));requested=15.69*2**30
    src=ROOT/'rasterizer_source';citations=[]
    for file,lo,hi,meaning in [('cuda_rasterizer/forward.cu',223,250,'Projected bounding rectangle and per-Gaussian tiles_touched'),
        ('cuda_rasterizer/rasterizer_impl.cu',276,286,'Prefix sum yields N, then allocate BinningState for N'),
        ('cuda_rasterizer/rasterizer_impl.cu',181,193,'Two uint32 ID arrays and two uint64 key arrays = 24N bytes, plus CUB sort workspace'),
        ('cuda_rasterizer/rasterizer_impl.h',23,28,'Each chunk member is aligned to128 bytes'),
        ('cuda_rasterizer/rasterizer_impl.h',70,77,'required<T> adds final128 bytes'),
        ('rasterize_points.cu',31,36,'Requested chunk bytes passed directly to tensor.resize_')]:
        p=src/file;citations.append(dict(file=file,first_line=lo,last_line=hi,meaning=meaning,sha256=sha(p),text='\n'.join(p.read_text().splitlines()[lo-1:hi])))
    stop=OUT/'r8/diagnostics/LoD2_stop/summary.json';oom=json.loads(stop.read_text())
    value=dict(at=stamp(),baseline=rows,allocation_formula='B(N)=24*N + CUB_SortPairs_workspace(N) + 128-byte member alignment padding + final128 bytes',
        measured_bytes_per_overlap=dict(min=float(ratios.min()),median=rho,max=float(ratios.max())),
        reported_request_GiB=15.69,approx_N_if_request_is_binning=requested/rho,
        approximation_note='Illustrative conversion using observed bytes/overlap. Not the actual OOM iteration overlap count. Error text rounds GiB to2 decimals; CUB storage and alignment depend on N.',
        oom_exact_overlap_count='확인 불가: failed-iteration tile counts and full model were not stored',
        oom_exact_buffer='The Python traceback ends at CUDA rasterize_gaussians and does not identify the C++ buffer; report the source allocation relation, not a measured OOM buffer identity.',
        oom_error=oom['error'],oom_source=str(stop),oom_source_sha256=sha(stop),source_lines=citations,measurements=render,scientific_verdict=None)
    dump(ROOT/'memory.json',value);print('MEMORY_RELATION',rho,requested/rho,flush=True)
if __name__=='__main__':main()
