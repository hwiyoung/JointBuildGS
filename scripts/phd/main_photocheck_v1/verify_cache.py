"""Validate cache headers and compare a seeded sample to original JPEG decoding."""
import cv2
from common import *
from cameras import Cameras
def main():
    cam=Cameras();fs=sorted((O/'image_cache').glob('[0-9]*.npy'));headers=[]
    for f in fs:
        a=np.load(f,mmap_mode='r');assert a.dtype==np.float32 and a.ndim==2
        assert f.stat().st_size==a.offset+a.size*a.dtype.itemsize
        headers.append(dict(file=f.name,shape=a.shape,bytes=f.stat().st_size))
    rng=np.random.default_rng(20261026);chosen=rng.choice(len(fs),min(12,len(fs)),replace=False);rows=[]
    for i in chosen:
        f=fs[i];j=int(f.stem.split('_')[0]);level=int(f.stem.split('_L')[1]);rgb=cam.rgb(j);gray=cv2.transform(rgb.astype(np.float32),np.array([[.299,.587,.114]],np.float32));del rgb
        for _ in range(level):gray=cv2.resize(gray,(gray.shape[1]//2,gray.shape[0]//2),interpolation=cv2.INTER_AREA)
        stored=np.load(f,mmap_mode='r');assert np.array_equal(stored,gray),f
        rows.append(dict(file=f.name,image=cam.names[j],level=level,pixels=gray.size,max_difference=0,sha256=sha(f)))
    dump(O/'gates/cache.json',dict(status='PASS',headers_checked=len(headers),fresh_original_images_compared=len(rows),rows=rows,seed=20261026,environment=env()))
    print('cache PASS',len(headers),'headers;',len(rows),'complete grayscale arrays compared to original JPEG')
if __name__=='__main__':main()
