"""Stream raw points once into 100 m cells with 10 m context; bounded CPU memory.

These are source points, not holdout patch measurements. No manual ULS.
"""
import json
import time
from pathlib import Path
import laspy
import numpy as np
from preflight import dump, sha

O=Path('/out');RAW=Path('/art/phase-payloads/p0-audit/data/raw')
DT=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('cls','u1'),('multi','u1')])

def main():
    t0=time.monotonic();tiles=json.loads((O/'inputs/tiles.json').read_text())
    root=O/'inputs/points';root.mkdir(parents=True,exist_ok=True)
    for kind,paths in [('als',sorted((RAW/'als').glob('*.laz'))),('uls',[RAW/'tum2twin/TUM_Downtown_ULS_20241217_nadir.laz'])]:
        if (root/f'{kind}_receipt.json').exists():continue
        files={};count={t['id']:0 for t in tiles}
        for tile in tiles:
            p=root/tile['id'];p.mkdir(exist_ok=True)
            files[tile['id']]=(p/f'{kind}.bin').open('wb')
        for p in paths:
            with laspy.open(p) as f:
                for pts in f.chunk_iterator(1_000_000):
                    x,y,z=np.asarray(pts.x),np.asarray(pts.y),np.asarray(pts.z)
                    cls=np.asarray(pts.classification);multi=np.asarray(pts.number_of_returns)>1
                    eligible=np.ones(len(x),bool)
                    if kind=='als':
                        ee,nn=[int(v)*1000 for v in p.stem.split('_')]
                        eligible=(x>=ee)&(x<ee+1000)&(y>=nn)&(y<nn+1000)&np.isin(cls,[2,6])
                    for tile in tiles:
                        x0,y0,x1,y1=tile['buffer_global']
                        m=eligible&(x>=x0)&(x<x1)&(y>=y0)&(y<y1)
                        n=int(m.sum())
                        if not n:continue
                        a=np.empty(n,DT)
                        a['x']=x[m]-690953.;a['y']=y[m]-5336071.
                        a['z']=z[m]+(45.7 if kind=='als' else 0.)-604.
                        a['cls']=cls[m];a['multi']=multi[m]
                        a.tofile(files[tile['id']]);count[tile['id']]+=n
            print('partitioned',kind,p.name,flush=True)
        for f in files.values():f.close()
        dump(root/f'{kind}_receipt.json',dict(points_per_context_tile=count,dtype=DT.descr,
            sources=[str(p) for p in paths],config_sha256=sha('/cfg/widen0_v2.json'),
            includes_overlap=True,manual_uls=False,scientific_verdict=None,seconds=time.monotonic()-t0))

if __name__=='__main__':main()
