"""Verify an exact uint8-to-float32 conversion and resulting cached grayscale bytes."""
import cv2,time
from common import *
from cameras import Cameras

def main():
    sample=np.stack([np.arange(256,dtype=np.uint8),np.arange(255,-1,-1,dtype=np.uint8),np.roll(np.arange(256,dtype=np.uint8),73)],axis=1)[:,None,:]
    converted=cv2.add(sample,0,dtype=cv2.CV_32F)
    assert converted.dtype==np.float32 and np.array_equal(converted,sample.astype(np.float32))
    cam=Cameras();files=sorted((O/'image_cache').glob('*.npy'));rng=np.random.default_rng(20261026);rows=[]
    for index in rng.choice(len(files),8,replace=False):
        file=files[index];j=int(file.stem.split('_')[0]);level=int(file.stem.split('_L')[1]);start=time.monotonic()
        rgb=cam.rgb(j);gray=cv2.transform(cv2.add(rgb,0,dtype=cv2.CV_32F),np.array([[.299,.587,.114]],np.float32));del rgb
        for _ in range(level):gray=cv2.resize(gray,(gray.shape[1]//2,gray.shape[0]//2),interpolation=cv2.INTER_AREA)
        reference=np.load(file,mmap_mode='r');assert np.array_equal(gray,reference),file
        out=O/'tmp'/('fast_cast_'+file.name);np.save(out,gray);assert sha(out)==sha(file)
        row=dict(cache=file.name,sha256=sha(file),seconds=time.monotonic()-start);rows.append(row);print('exact cast verified',row,flush=True)
        out.unlink()
    result=dict(status='PASS',at=now(),all_uint8_values_and_channels_exact=True,files=rows,environment=env(),scientific_verdict=None)
    dump(O/'gates/fast_cast.json',result);dump(D/'provenance/fast_cast.json',result)
if __name__=='__main__':main()
