"""Check JPEG cache on every curve of the existing 200-point precision sample."""
import json
import numpy as np
from numpy.core import _multiarray_umath as memory
import photo_score_reply2 as P
from photo_stream_cache_reply2 import StreamImageCache
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez

def main():
    assert json.loads((O/'r2/image_supply_benchmark.json').read_text())['status']=='PASS_IMAGE_SUPPLY_PIXEL_IDENTITY'
    memory_gate=O/'r2/array_memory_benchmark.json'
    assert json.loads(memory_gate.read_text())['status']=='PASS_PROCESS_LOCAL_ARRAY_COPY_IDENTITY'
    memory._set_madvise_hugepage(False)
    assert not memory._get_madvise_hugepage()
    root=O/'r2/stream_verification';root.mkdir(parents=True,exist_ok=True)
    files=[Path(P.__file__),Path(__file__),Path(__file__).with_name('photo_stream_cache_reply2.py'),Path(__file__).with_name('photo_cameras.py')]
    before=dict(at=now(),sources={p.name:sha(p) for p in files},kernel_changed=False,numpy_hugepage_advice=False,memory_gate_sha256=sha(memory_gate),
                policy='4 GiB process LRU; read-only original JPEG on misses; identical float32 grayscale and pyramid; unchanged float64 scoring',scientific_verdict=None)
    dump(root/'before.json',before)
    P.ImageCache=StreamImageCache;g=P.packed_reference()
    result,timing=P.score(g,root,device='cpu',chunk_rows=600000,batch_rows=1024)
    original=loadz(O/'r1/photo_benchmark/scores_cpu.npz');errors={}
    assert np.array_equal(result['pyramid_levels'],original['pyramid_levels'])
    for key in ['best_score','best_height','texture','texture_by_view']:
        x=result[key];y=original[key];assert np.array_equal(np.isfinite(x),np.isfinite(y)),key
        m=np.isfinite(x);errors[key]=float(np.max(abs(x[m]-y[m]))) if m.any() else 0.
        assert errors[key]<1e-10,(key,errors[key])
    maximum=0.;curves=0
    for i in range(len(g['point_id'])):
        valid=np.isfinite(g['heights'][i])
        for k in range(2):
            l,r=g['plane_row_ptr'][2*i:2*i+3][k:k+2]
            if r==l:continue
            x=result['curves'][:,l:r];y=original['curves'][:,i,k][:,valid]
            assert np.array_equal(np.isfinite(x),np.isfinite(y))
            m=np.isfinite(x)
            if m.any():maximum=max(maximum,float(np.max(abs(x[m]-y[m]))))
            curves+=x.size
    assert maximum<1e-10,maximum
    savez(root/'scores.npz',**result)
    timing.update(status='PASS_STREAM_CACHE_200_POINT_SCORE_PARITY',errors=errors,max_curve_difference=maximum,numpy_hugepage_advice=False,memory_gate_sha256=sha(memory_gate),
                  compared_curve_entries=curves,sources=before['sources'],output_sha256=sha(root/'scores.npz'),scientific_verdict=None)
    dump(root/'complete.json',timing);dump(D/'tables/reply2_stream_cache_verification.json',timing)
    print(timing['status'],maximum,timing['total_seconds'],flush=True)

if __name__=='__main__':main()
