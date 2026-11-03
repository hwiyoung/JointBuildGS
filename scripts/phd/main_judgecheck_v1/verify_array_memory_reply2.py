"""Observe read/copy and kernel CPU cost with process-local NumPy huge-page advice."""
import hashlib,resource,time
import numpy as np
from numpy.core import _multiarray_umath as memory
from preflight import D,O,Path,sha,dump,now

def main():
    path=Path('/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1/image_cache/0000_L0.npy')
    previous=memory._get_madvise_hugepage();rows=[]
    try:
        for enabled in [True,False,False,True]:
            memory._set_madvise_hugepage(enabled)
            before=resource.getrusage(resource.RUSAGE_SELF);start=time.monotonic()
            arr=np.array(np.load(path,mmap_mode='r'))
            seconds=time.monotonic()-start;after=resource.getrusage(resource.RUSAGE_SELF)
            row=dict(numpy_hugepage_advice=enabled,seconds=seconds,user_seconds=after.ru_utime-before.ru_utime,
                     system_seconds=after.ru_stime-before.ru_stime,bytes=arr.nbytes,
                     pixels_sha256=hashlib.sha256(memoryview(arr)).hexdigest())
            rows.append(row);print('ARRAY_MEMORY',row,flush=True);del arr
    finally:memory._set_madvise_hugepage(previous)
    assert len({r['pixels_sha256'] for r in rows})==1
    result=dict(at=now(),status='PASS_PROCESS_LOCAL_ARRAY_COPY_IDENTITY',rows=rows,
                scope='Single 83.55 MB image, mixed on/off order under concurrent load. Only this test process changes NumPy advice. No host kernel setting or running calculation changed.',
                source_sha256=sha(Path(__file__)),scientific_verdict=None)
    dump(O/'r2/array_memory_benchmark.json',result);dump(D/'tables/reply2_array_memory_benchmark.json',result)

if __name__=='__main__':main()
