from common import *
from task0_scan import cameras_depth
def main():
    row=load(DOC/'figures/task0_specular_candidates.json')['selected'];poses,cam=cameras_depth();wanted=set(row['patch_ids']);rows=[]
    for tile in row['tiles']:
        z=geometry(tile,row['prior']);m=dict(np.load(PAY/'task0/mvs_v4'/f'{tile}_{row["prior"]}.npz'));g=dict(np.load(PAY/'task0/gt'/f'{tile}_{row["prior"]}.npz'));sel=np.array([p in wanted for p in z['patch_id'][m['patch_index']]]);ix=m['patch_index'][sel];X=g['representative'][ix];per=m['per_view_signed'][sel]
        for i,name in enumerate(m['view_names']):
            ids=np.flatnonzero(np.isfinite(per[:,i]));
            if not len(ids):continue
            p=poses[str(name)];uv,zz=G.project(X[ids],p,cam);ij=np.floor(uv).astype(int);D=depth(W/'mvs/full/stereo/depth_maps'/f'{p["name"]}.geometric.bin');dd=D[ij[:,1],ij[:,0]]
            rows.append(dict(tile=tile,view=str(name),n=len(ids),normal_signed_median=float(np.median(per[ids,i])),normal_abs_median=float(np.median(abs(per[ids,i]))),camera_z_delta_quantiles=np.quantile(dd-zz,[0,.1,.5,.9,1]),gt_depth_median=float(np.median(zz)),mvs_depth_median=float(np.median(dd))))
    rows.sort(key=lambda r:-r['n']);out=dict(component_id=row['component_id'],camera=cam,views=rows,scientific_verdict=None,interpretation='Camera-ray depth discrepancy; material cause and same-surface MVS correspondence are not established.');dump(DOC/'qa/task0_numeric_audit.json',out)
    for r in rows[:15]:print(r)
if __name__=='__main__':main()
