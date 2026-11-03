"""Bounded, pixel-exact timing of existing NPY reads versus original JPEG decode."""
import json,time
import numpy as np
import torch
from preflight import D,O,Path,sha,dump,now
from photo_cameras import Cameras

def main():
    torch.set_num_threads(2)
    cam=Cameras()
    inherited=Path('/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1/image_cache')
    candidates=sorted(inherited.glob('*_L0.npy'))
    ids=np.linspace(0,len(candidates)-1,8,dtype=int)
    rows=[]
    for idx in ids:
        path=candidates[idx];j=int(path.stem.split('_')[0])
        t=time.monotonic();old=np.array(np.load(path,mmap_mode='r'));disk=time.monotonic()-t
        t=time.monotonic();decoded=cam.gray_pyramid(j,{0})[0];decode=time.monotonic()-t
        assert np.array_equal(old,decoded),str(path)
        t=time.monotonic();converted=torch.as_tensor(np.array(decoded,copy=True),dtype=torch.float64);copy=time.monotonic()-t
        assert np.array_equal(converted.numpy(),old.astype(np.float64))
        row=dict(camera=j,source=cam.names[j],shape=list(old.shape),bytes=old.nbytes,
                 npy_read_copy_seconds=disk,jpeg_decode_seconds=decode,float64_copy_seconds=copy,
                 pixel_exact=True)
        rows.append(row);print('IMAGE_SUPPLY',json.dumps(row),flush=True)
        del old,decoded,converted
    result=dict(at=now(),status='PASS_IMAGE_SUPPLY_PIXEL_IDENTITY',rows=rows,
                scope='Eight deterministic existing training images; no curve, selection, geometry, threshold or judgment change. Timings are concurrent-load observations, not isolated disk benchmarks.',
                source_sha256=sha(Path(__file__)),camera_source_sha256=sha(Path(__file__).with_name('photo_cameras.py')),
                total_npy_read_seconds=sum(r['npy_read_copy_seconds'] for r in rows),
                total_jpeg_decode_seconds=sum(r['jpeg_decode_seconds'] for r in rows),
                scientific_verdict=None)
    dump(O/'r2/image_supply_benchmark.json',result);dump(D/'tables/reply2_image_supply_benchmark.json',result)

if __name__=='__main__':main()
