"""Regression audit for the observed out-of-tile occlusion defect."""
from common import *
from task0_scan import cameras_depth
def main():
    old=load(PAY/'task0/invalidated_v2/task0_specular_candidates.json')['selected'];Q=np.array(old['gt_representative']);N=np.array(old['normal']);wanted=set(old['patch_ids']);poses,cam=cameras_depth();meta=load(PAY/'task0/global_visibility/complete.json');glob=np.load(PAY/'task0/global_visibility/zbuffer.npy',mmap_mode='r');rows=[]
    for tile in old['tiles']:
        z=geometry(tile,old['prior']);g=np.load(PAY/'task0/gt'/f'{tile}_{old["prior"]}.npz');m=np.load(PAY/'task0/mvs_v2'/f'{tile}_{old["prior"]}.npz');sel=np.array([s in wanted for s in z['patch_id'][m['patch_index']]]);ix=m['patch_index'][sel];X=g['representative'][ix];err=m['per_view_signed'][sel]
        for j,name in enumerate(m['view_names']):
            ids=np.flatnonzero(np.isfinite(err[:,j]));
            if not len(ids):continue
            uv,d=G.project(X[ids],poses[str(name)],cam);ij=np.floor(uv).astype(int);buf=glob[meta['names'].index(str(name))];visible=d<=buf[ij[:,1]*1024+ij[:,0]]+.25
            if (PAY/'task0/public_lod2_visibility.npz').exists():
                from solid_visibility import visible as solid
                vi=np.flatnonzero(visible);visible[vi]&=solid(X[ids[vi]],poses[str(name)],d[vi])
            rows.append(dict(view=str(name),old_visible=int(len(ids)),new_visible=int(visible.sum()),old_abs_median_m=float(np.median(abs(err[ids,j]))),retained_abs_median_m=float(np.median(abs(err[ids[visible],j]))) if visible.any() else None))
    bad=[r for r in rows if r['old_abs_median_m']>50];removed=sum(r['old_visible']-r['new_visible'] for r in bad);total=sum(r['old_visible'] for r in bad)
    dump(DOC/'qa/global_visibility_regression.json',dict(status='PASS' if total and removed/total>.95 else 'PARTIAL',old_component=old['component_id'],old_samples_above_50m_view_median=total,removed_by_global_occlusion=removed,removed_fraction=removed/total,views=rows,scientific_verdict=None));print('GLOBAL REGRESSION',removed,total,removed/total)
if __name__=='__main__':main()
