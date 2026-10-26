"""Exact global public-input GT z buffers; no spatial filling or outcome reads."""
import itertools,time,shutil
from concurrent.futures import ThreadPoolExecutor
from common import *
from task0_scan import points,cameras_depth
from fast_zbuffer import fast,build
def main():
    config();amend=CFG/'amendment_04_global_visibility.json'
    if not amend.exists():
        dump(amend,dict(at=now(),task_id='PHD-SLIDE-PHOTO-v1',scientific_verdict=None,
          reason='Selected-component numeric audit found some same-pixel MVS depths about 100m nearer than GT. Tile-local z-buffer omitted foreground occluders outside its 10m context. Initial candidate tables and material classification are invalid for selection.',
          evidence='qa/task0_numeric_audit.json before recalculation; large residual views versus near-zero residual views',
          correction='Accumulate nearest camera-Z from all 24 public input GT tiles into each training camera. Exact pixel minimum; no neighbour filling. Retain front-face test, density, error, connectivity, material and ranking rules.',
          stage='after first material review and before task0 completion; rerun all candidates and independent material review'))
        archive=PAY/'task0/invalidated_v2';archive.mkdir()
        for p in [*list((DOC/'figures').glob('task0*')),*list((DOC/'figures').glob('figS_c_specular*')),DOC/'qa/task0_material_review.json',DOC/'qa/task0_numeric_audit.json',PAY/'task0/components.json',PAY/'task0/top10_photos.json']:
            if p.exists():shutil.move(str(p),str(archive/p.name))
    poses,cam=cameras_depth();names=sorted(n for n,p in poses.items() if (W/'mvs/full/stereo/depth_maps'/f'{p["name"]}.geometric.bin').exists());out=PAY/'task0/global_visibility';out.mkdir(exist_ok=True)
    if (out/'complete.json').exists():return
    buf=np.lib.format.open_memmap(out/'zbuffer.npy',mode='w+',dtype=np.float64,shape=(len(names),741*1024));buf[:]=np.inf;build();counts={};started=time.monotonic()
    for tile in load(W/'inputs/tiles.json'):
        X=points(tile['id']);lo=X.min(0);hi=X.max(0);corners=np.array(list(itertools.product(*zip(lo,hi))));work=[]
        for i,n in enumerate(names):
            p=poses[n];q=corners@p['R'].T+p['t'];fx,fy,cx,cy=cam['p'];u=fx*q[:,0]+cx*q[:,2];v=fy*q[:,1]+cy*q[:,2]
            planes=np.c_[q[:,2],u,1024*q[:,2]-u,v,741*q[:,2]-v]
            if np.any(np.all(planes<=0,axis=0)):continue
            work.append((i,p))
        def one(item):
            i,p=item;fast(X,p,cam,buf[i]);return i
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,work))
        counts[tile['id']]=dict(points=len(X),intersecting_cameras=len(work));buf.flush();print('GLOBAL VIS',tile['id'],counts[tile['id']],'seconds',round(time.monotonic()-started),flush=True)
    dump(out/'complete.json',dict(at=now(),names=names,tiles=counts,seconds=time.monotonic()-started,scientific_verdict=None,rule='exact nearest camera Z from all public input tiles, shared original kernel'))
if __name__=='__main__':main()
