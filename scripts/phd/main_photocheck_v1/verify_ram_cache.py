"""Verify optional tmpfs copies and exercise repeated reads without pixel changes."""
import time
from common import *
from cameras import Cameras
def main():
    cam=Cameras();files=sorted((O/'image_cache').glob('*.npy'));rng=np.random.default_rng(20261026);rows=[]
    for i in rng.choice(len(files),size=min(8,len(files)),replace=False):
        f=files[i];j=int(f.stem.split('_')[0]);level=int(f.stem.split('_L')[1]);t=time.monotonic();im=cam.gray(j,level);cold=time.monotonic()-t;target=O/'tmp/image_cache_ram'/f.name
        assert target.exists() and sha(f)==sha(target)
        t=time.monotonic();second=cam.gray(j,level);warm=time.monotonic()-t;assert np.array_equal(im,second)
        rows.append(dict(image_index=j,pyramid_level=level,bytes=f.stat().st_size,sha256=sha(target),first_copy_seconds=cold,repeated_open_seconds=warm))
    result=dict(status='PASS',at=now(),byte_identical_files=len(rows),cache_budget_bytes=int(os.environ['PHOTOCHECK_RAM_CACHE_BYTES']),container_memory_limit_gib=32,policy='20 GiB LRU in ephemeral tmpfs /out/tmp/image_cache_ram. A cache miss decodes the compact original JPEG with identical grayscale and pyramid arithmetic; resulting NPY bytes match existing persistent cache bytes. One image opened at a time; persistent image cache preserved.',rows=rows,scientific_verdict=None)
    dump(O/'gates/ram_cache.json',result);dump(D/'provenance/ram_cache.json',result);print('RAM cache byte identity PASS',len(rows))
if __name__=='__main__':main()
