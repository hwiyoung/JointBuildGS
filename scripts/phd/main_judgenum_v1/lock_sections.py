"""Resolve predeclared sections and source paths, preserving the original lock."""
import json
from pathlib import Path
import shutil
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from lock_config import dump,sha,stamp
C=Path('/cfg');O=Path('/out')

def largest_component(c,area,patch):
    tree=cKDTree(c);pairs=tree.query_pairs(.36,output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs),np.int8),(pairs[:,0],pairs[:,1])),shape=(len(c),len(c)))
    nc,labels=connected_components(graph,directed=False)
    aa=np.bincount(labels,weights=area,minlength=nc)
    candidates=np.flatnonzero(aa==aa.max())
    best=min(candidates,key=lambda k:str(min(patch[labels==k])))
    return np.flatnonzero(labels==best),float(aa[best])

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());before=sha(C/'judgenum_v1.json')
    assert cfg['figures']['section_coordinates'] is None
    sections=[]
    for prior in ['LoD2','ALS']:
        parts=[]
        for p in sorted((O/'inputs').glob(f'*__{prior}.npz')):
            with np.load(p) as z:parts.append({k:z[k] for k in ['centre','area','building','patch_id','cell','kind','roof_type']})
        data={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
        for cell in [1,2,0] if prior=='LoD2' else [1,2]:
            eligible=data['cell']==cell
            if cell==0:eligible&=(data['kind']==1)&(data['roof_type']=='1000')
            best=None
            for bid in sorted(set(data['building'][eligible])):
                ix=np.flatnonzero(eligible&(data['building']==bid))
                local,area=largest_component(data['centre'][ix],data['area'][ix],data['patch_id'][ix]);ids=ix[local]
                score=float(data['area'][ix].sum()) if cell==0 else area
                key=(-score,bid,str(min(data['patch_id'][ids])))
                if best is None or key<best[0]:best=(key,bid,ids,area)
            if best is None:sections.append({'prior':prior,'cell':cell,'status':'unavailable: no eligible component'});continue
            _,bid,ids,area=best;xyz=data['centre'][ids];weights=data['area'][ids]
            centre=np.average(xyz,axis=0,weights=weights);v=xyz[:,:2]-centre[:2]
            _,axes=np.linalg.eigh((v.T*weights)@v/weights.sum());major=axes[:,-1]
            direction=np.array([-major[1],major[0]])
            if direction[0]<0 or (direction[0]==0 and direction[1]<0):direction=-direction
            sections.append({'prior':prior,'cell':cell,'building':bid,'component_area_m2':area,
              'centre_local_m':centre.tolist(),'a_local_xy_m':(centre[:2]-5*direction).tolist(),
              'b_local_xy_m':(centre[:2]+5*direction).tolist(),'half_width_m':.3,
              'axis_definition':'area-weighted horizontal principal axis; section perpendicular in XY',
              'patch_ids':data['patch_id'][ids].tolist()})
            print('SECTION',prior,cell,bid,area,flush=True)
    shutil.copyfile(C/'judgenum_v1.json',C/'judgenum_v1.r0.json')
    shutil.copyfile(C/'judgenum_v1.lock.json',C/'judgenum_v1.r0.lock.json')
    cfg['sources']['mvs_points']=cfg['sources']['mvs_points'].replace('mvs_a.npy','mvs_a_xyz.npy')
    cfg['sources']['mvs_points_status']='verified existing training-only float32 XYZ arrays in 100m tiles with 10m context'
    cfg['figures']['section_coordinates']=sections
    cfg['figures']['section_coordinate_status']='resolved by the frozen rule after section 2.1 and before cylinders'
    cfg['execution']['benchmark_tile']='6908_53359'
    cfg['execution']['benchmark_rule']='largest eligible patch-count tile; one full tile including all radii and all half-length sensitivities'
    cfg['amendments'].append({'at':stamp(),'previous_config_sha256':before,
      'reason':'Resolve verified source filename and deterministic section coordinates; add conservative largest-tile benchmark. Sample counts have been seen; no cylinders, detection limits or choices computed.',
      'original_rules_unchanged':True})
    dump(C/'judgenum_v1.json',cfg)
    old=json.loads((C/'judgenum_v1.r0.lock.json').read_text())
    dump(C/'judgenum_v1.lock.json',{**old,'locked_at':stamp(),'before_first_calculation':False,
      'before_first_cylinder_calculation':True,'config_sha256':sha(C/'judgenum_v1.json'),
      'previous_lock':'judgenum_v1.r0.lock.json','implementation':{p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*')) if p.is_file()}})
    print('R1_LOCK',sha(C/'judgenum_v1.json'))

if __name__=='__main__':main()
