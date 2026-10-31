"""Freeze display locations from prior place files and frozen region labels only."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from common import *
sys.path.insert(0,str(REPO/'scripts/phd/main_axes71_v2'))
import mvs_surface as MS


def load(site):
    with np.load(OUT/'targets'/f'{site}_LoD2.npz') as z:return {k:z[k] for k in z.files}


def main():
    cfg,lock=training_locked();dest=CFG/'representatives_v1.json';assert not dest.exists()
    old=REPO/'configs/phd/main_losstrain_v1/losstrain_v1.json'
    sections=json.loads(old.read_text())['figures']['sections'][:2]
    rows=[dict(x,id=k+1,place_source=str(old),place_source_sha256=sha(old)) for k,x in enumerate(sections)]
    places=S1/'defs/fig_views_v1.json';p=json.loads(places.read_text())
    # Exact old B0 view centre; the display section follows prior roof geometry only.
    def find_target(x):
        if isinstance(x,dict):
            if 'B0_b10' in x:return find_target(x['B0_b10'])
            if 'target' in x:return x['target']
            for v in x.values():
                y=find_target(v)
                if y is not None:return y
        return None
    centre=np.asarray(find_target(p),float);assert centre.shape==(3,)
    d=load('B0_b10');near=(d['kind']==1)&(np.linalg.norm(d['centre'][:,:2]-centre[:2],axis=1)<8)
    assert near.sum()>10
    C=d['centre'][near,:2];_,_,V=np.linalg.svd(C-C.mean(0),full_matrices=False);direction=V[0]
    if direction[0]<0:direction=-direction
    rows.append(dict(id=3,name='B0 단순화 지붕',site='B0_b10',priors=['LoD2'],start=(centre[:2]-6*direction).tolist(),
        end=(centre[:2]+6*direction).tolist(),half_width=.6,place_source=str(places),place_source_sha256=sha(places),
        place_note='old B0 view centre, prior-roof PCA direction within 8m, 12m section; approximately 15cm is an order expectation, not a selection statistic'))
    candidates=[]
    for site in cfg['sites']+cfg['deferred_sites']:
        d=load(site)
        with np.load(OUT/'stage0_r1/evaluation'/f'{site}_LoD2.npz') as z:cell=z['cell']
        ids=np.flatnonzero((d['kind']==1)&(d['region']==2)&(cell==1)&d['in_eval'])
        pairs=cKDTree(d['centre'][ids]).query_pairs(.36,output_type='ndarray')
        graph=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(ids),len(ids)))
        count,label=connected_components(graph,directed=False)
        areas=np.bincount(label,weights=d['area'][ids],minlength=count)
        for k in np.flatnonzero(areas==areas.max()):
            part=ids[label==k];candidates.append((float(areas[k]),site,int(part.min()),part))
    area,site,first,ids=sorted(candidates,key=lambda x:(-x[0],x[1],x[2]))[0]
    d=load(site);C=d['centre'][ids,:2];centre=np.average(C,weights=d['area'][ids],axis=0)
    _,_,V=np.linalg.svd(C-centre,full_matrices=False);direction=V[0]
    if direction[0]<0:direction=-direction
    along=(C-centre)@direction;lo,hi=along.min()-1,along.max()+1
    rows.append(dict(id=4,name='판단이 틀린 보존 자리',site=site,priors=['LoD2'],start=(centre+lo*direction).tolist(),
        end=(centre+hi*direction).tolist(),half_width=.6,component_area_m2=area,component_patch_count=len(ids),
        first_patch_index=first,patch_indices=ids.tolist(),selection='largest area connected component, radius .36m, ties site then index; display only'))
    for r in rows:
        d=load(r['site']);a,b=np.array(r['start']),np.array(r['end']);delta=b-a;length=np.linalg.norm(delta);v=delta/length
        rel=d['centre'][:,:2]-a;along=rel@v;perp=abs(rel[:,0]*v[1]-rel[:,1]*v[0])
        mask=(along>=0)&(along<=length)&(perp<=r['half_width'])&(d['kind']==1)
        assert mask.any(),r['name']
        xyz=d['centre'][mask];center=xyz.mean(0);cams,_=MS.cameras(r['site']);rank=[]
        for cam in cams:
            M=cam['W2C'];c=xyz@M[:3,:3].T+M[:3,3];uv=c[:,:2]/c[:,2,None]
            u=cam['fx']*uv[:,0]+cam['cx'];v=cam['fy']*uv[:,1]+cam['cy']
            inside=(c[:,2]>0)&(u>20)&(u<cam['W']-20)&(v>20)&(v<cam['H']-20)
            if not inside.any():continue
            footprint=float(np.ptp(u[inside])*np.ptp(v[inside]));rank.append((-int(inside.sum()),-footprint,cam['name'],cam))
        cam=sorted(rank,key=lambda x:x[:3])[0][3]
        r['camera']={k:(v.tolist() if isinstance(v,np.ndarray) else v.item() if isinstance(v,np.generic) else v) for k,v in cam.items()}
        r['camera_rule']='training camera with most section prior patch centres in frame, then projected bounding area, then name; no rendered output used'
        r['center_xyz']=center.tolist();r['mesh_views']=[dict(azimuth=a,elevation=35) for a in [-60,60,180]]
    result=dict(at=stamp(),config_sha256=lock['config_sha256'],rows=rows,scientific_verdict=None)
    dump(dest,result);dump(CFG/'representatives_v1.lock.json',dict(at=stamp(),sha256=sha(dest),before_training=True,source_sha256=sha(Path(__file__))))
    print('REPRESENTATIVES_FROZEN',[(r['id'],r['site'],r['camera']['name']) for r in rows],flush=True)

if __name__=='__main__':main()
