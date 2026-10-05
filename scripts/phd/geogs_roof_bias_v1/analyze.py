"""Reproducible postprocessing. No optimization code or trained state is changed."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.special import expit
from plyfile import PlyData
import open3d as o3d

def xyz_ply(path,opacity=False):
    p=PlyData.read(str(path))['vertex'];xyz=np.column_stack([p[k] for k in ('x','y','z')]).astype(np.float64)
    return (xyz,expit(np.asarray(p['opacity'],dtype=np.float64))) if opacity else xyz

def stats(x):
    x=np.asarray(x);x=x[np.isfinite(x)]
    if not len(x):return {'n':0,'median_m':None,'nmad_m':None,'abs_gt_0_2_fraction':None}
    med=np.median(x)
    return {'n':len(x),'median_m':float(med),'nmad_m':float(1.4826*np.median(np.abs(x-med))),'abs_gt_0_2_fraction':float(np.mean(np.abs(x)>.2))}

def opacity_stats(x):
    x=np.asarray(x);total=len(x);x=x[np.isfinite(x)]
    return {'n':total,'opacity_valid_n':len(x),'opacity_nonfinite_n':total-len(x),'opacity_median':float(np.median(x)) if len(x) else None,'opacity_gt_0_5_fraction':float(np.mean(x>.5)) if len(x) else None,'opacity_lt_0_01_fraction':float(np.mean(x<.01)) if len(x) else None}

def signed_distances(displacement, normals):
    component = np.einsum('ij,ij->i', displacement, normals)
    return np.linalg.norm(displacement, axis=1) * np.sign(component), component

def track(a,b,threshold=.05):
    finite_a=np.isfinite(a).all(axis=1);finite_b=np.isfinite(b).all(axis=1)
    original_b=np.flatnonzero(finite_b)
    d=np.full(len(a),np.inf);idx=np.full(len(a),-1,dtype=np.int64)
    if finite_a.any() and finite_b.any():
        da,ib=cKDTree(b[finite_b]).query(a[finite_a],workers=8)
        d[finite_a]=da;idx[finite_a]=original_b[ib]
    valid=d<threshold
    # One destination can only represent one source. Keep closest source for each collision.
    order=np.argsort(d,kind='stable');keep=np.zeros(len(a),bool);seen=set()
    for i in order:
        if valid[i] and int(idx[i]) not in seen:keep[i]=True;seen.add(int(idx[i]))
    return d,idx,keep,{'source_count':len(a),'distance_failed':int((~valid&finite_a).sum()),'nonfinite_source_failed':int((~finite_a).sum()),'nonfinite_destination_excluded':int((~finite_b).sum()),'collision_failed':int(valid.sum()-keep.sum()),'matched_unique':int(keep.sum()),'unmatched_total':int((~keep).sum())}

class OriginalMesh:
    def __init__(self,path):
        z=np.load(path);self.v=z['vertices'];self.f=z['faces'];self.target=z['target_face_mask'];self.labels=z['labels'];self.ids=z['building_ids']
        tri=self.v[self.f];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-15)
        roof=(self.labels!='GroundSurface')&(np.abs(n[:,2])>.2)
        n[roof&(n[:,2]<0)]*=-1;self.normals=n
        self.kind=np.zeros(len(n),np.uint8);self.kind[self.target&roof]=1;self.kind[self.target&(self.labels!='GroundSurface')&~roof]=2
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(self.v),o3d.utility.Vector3iVector(self.f.astype(np.int32)))
        self.scene=o3d.t.geometry.RaycastingScene();self.scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        pts=tri[self.target].reshape(-1,3);self.lo=pts.min(0);self.hi=pts.max(0)
    def assign(self,x):
        i=np.empty(len(x),np.int64)
        for a in range(0,len(x),100000):i[a:a+100000]=self.scene.compute_closest_points(o3d.core.Tensor(x[a:a+100000].astype('float32')))['primitive_ids'].numpy()
        return self.kind[i],i
    def bbox(self,x):return np.all((x[:,:2]>=self.lo[:2])&(x[:,:2]<=self.hi[:2]),axis=1)

def main(name):
    T=Path('/task');root=T/'conditions'/name;out=root/'analysis';out.mkdir(exist_ok=True);mesh=OriginalMesh(T/'provenance/original_mesh.npz')
    receipt={'condition':name,'scientific_verdict':None};pointfile=root/'evaluation/pred_points.ply'
    if pointfile.exists():
        gt=xyz_ply(root/'evaluation/gt_cropped.ply');pred=xyz_ply(pointfile)
        gkind,gface=mesh.assign(gt);pkind,pface=mesh.assign(pred);receipt['surfaces']={}
        for code,label in [(1,'roof'),(2,'wall')]:
            gp=gt[gkind==code];pp=pred[pkind==code];fi=pface[pkind==code]
            if not len(gp) or not len(pp):receipt['surfaces'][label]=dict(stats([]),gt_n=len(gp),prediction_n=len(pp));continue
            d,ix=cKDTree(gp).query(pp,workers=8);displacement=pp-gp[ix];signed,normal_component=signed_distances(displacement,mesh.normals[fi])
            receipt['surfaces'][label]=dict(stats(signed),gt_n=len(gp),prediction_n=len(pp),normal_component_stats=stats(normal_component))
            np.savez(out/f'{label}_errors.npz',prediction=pp,gt_nearest=gp[ix],signed_error=signed,normal_component=normal_component,face_id=fi)
    p8=root/'model/point_cloud/iteration_8000/point_cloud.ply';p30=root/'model/point_cloud/iteration_30000/point_cloud.ply'
    if p8.exists() and p30.exists():
        x8=xyz_ply(p8);x30,op=xyz_ply(p30,True)
        finite30=np.isfinite(x30).all(axis=1)
        receipt['checkpoint_quality']={'nonfinite_xyz_30000':int((~finite30).sum()),'nonfinite_opacity_30000':int((~np.isfinite(op)).sum()),'policy':'Original PLY unchanged; nonfinite coordinates excluded from spatial queries with original indices retained; opacity statistics use finite values and report denominator.'}
        prior_path=Path('/original_scene/lod2_pcd.ply') if name=='N' else root/'scene/lod2_pcd.ply'
        prior=xyz_ply(prior_path);near,_=cKDTree(prior).query(x8,workers=8);mask8=near<.2
        exact=out/'native_mask8000.npy'
        if exact.exists():
            native8=np.load(exact);assert len(native8)==len(mask8)
            receipt['mask8000_comparison']={'official_count':int(native8.sum()),'scipy_count':int(mask8.sum()),'disagreement_count':int(np.sum(native8!=mask8)),'primary':'official train.find_building_mask_from_pcd'}
            mask8=native8
        else:receipt['mask8000_comparison']={'primary':'SCIPY_FALLBACK_NATIVE_MASK_UNAVAILABLE'}
        d,idx,keep,tr=track(x8[mask8],x30);matched=idx[keep];mop=op[matched];mov=d[keep]
        receipt['protection']=dict(opacity_stats(mop),n_8000=int(mask8.sum()),**tr,movement_median_m=float(np.median(mov)) if len(mov) else None,movement_p95_m=float(np.quantile(mov,.95)) if len(mov) else None)
        actual_path=root/'observations/frozen_mask_30000.npy'
        if actual_path.exists():
            actual=np.load(actual_path);assert len(actual)==len(x30)
            receipt['checkpoint_quality']['nonfinite_xyz_native_protected']=int((actual&~finite30).sum())
            receipt['checkpoint_quality']['nonfinite_xyz_native_unprotected']=int((~actual&~finite30).sum())
            receipt['actual_protected']=opacity_stats(op[actual]);receipt['protection']['matched_native_protected_fraction']=float(np.mean(actual[matched])) if len(matched) else None
        else:
            actual=np.zeros(len(x30),bool);actual[matched]=True
            receipt['actual_protected']={'status':'MISSING_NATIVE_MASK; inferred tracking complement only'}
        crop=finite30&mesh.bbox(x30);local_indices=np.flatnonzero(crop);kind,face=mesh.assign(x30[crop]);roof_idx=local_indices[kind==1];unprotected=roof_idx[~actual[roof_idx]]
        receipt['roof_unprotected']=opacity_stats(op[unprotected]);receipt['roof_actual_protected']=opacity_stats(op[roof_idx[actual[roof_idx]]])
        np.savez(out/'protected_statistics.npz',tracked_opacity=mop,tracked_displacement=mov,local_xyz=x30[local_indices],local_opacity=op[local_indices],local_actual_protected=actual[local_indices],local_kind=kind,matched_count=len(matched))
        reg=root/'observations/actual_protection_registration.npz'
        if reg.exists():
            r=np.load(reg);receipt['actual_registration_count']=int(r['mask'].sum());receipt['registration_total']=len(r['mask'])
    events=root/'observations/events.jsonl'
    if events.exists():
        rows=[json.loads(x) for x in events.read_text().splitlines()];receipt['densification']=rows[-1] if rows else {}
    (out/'summary.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))

if __name__=='__main__':main(sys.argv[1])
