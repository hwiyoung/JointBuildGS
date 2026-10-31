"""Exhaustive h reconstruction for every disc pixel in each frozen representative view."""
import numpy as np
from common import *

def main():
    training_locked();rows=[]
    reps=json.loads((CFG/'representatives_v1.json').read_text())['rows']
    for rep in reps:
        for prior in rep['priors']:
            site=rep['site'];name=rep['camera']['name'];root=OUT/'stage1'/f'{site}_{prior}'/'maps'
            index=json.loads((root/'index.json').read_text());meta=index['views'][name]
            assert sha(root/meta['file'])==meta['sha256']
            with np.load(root/meta['file']) as z:depth,owner=z['depth'],z['owner']
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in ['centre','normal','h']}
            v,u=np.nonzero(owner>=0);pid=owner[v,u];K=np.asarray(meta['K']);M=np.asarray(meta['W2C'])
            # Independent full 4x4 inverse, rather than the producer's R transpose.
            ray=np.linalg.solve(K,np.stack([u,v,np.ones(len(u))]))
            camera_xyz=ray*depth[v,u];homogeneous=np.vstack([camera_xyz,np.ones(len(u))])
            xyz=(np.linalg.inv(M)@homogeneous)[:3].T
            h=np.einsum('ij,ij->i',xyz-d['centre'][pid],d['normal'][pid]);error=abs(h-d['h'][pid])
            median=float(np.median(error));assert median<=.01
            rows.append(dict(representative=rep['id'],site=site,prior=prior,camera=name,pixels=len(u),
                absolute_h_error_median_m=median,absolute_h_error_max_m=float(error.max()),criterion_m=.01,status='PASS'))
    result=dict(at=stamp(),status='PASS_ALL_REPRESENTATIVE_DISC_PIXELS',rows=rows,scientific_verdict=None)
    dump(OUT/'representative_pixel_verification.json',result);dump(DOC/'tables/stage1_representative_pixels.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
