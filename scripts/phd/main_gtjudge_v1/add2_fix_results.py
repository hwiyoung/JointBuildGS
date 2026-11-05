import sys,re
from add2_common import *

def main(site,prior):
    config2();stem=f'{site}__{prior}';root=O/'scenes'/stem;row,owner=full_owner(site,prior);cell=loadz(root/'stage1_cells.npz');t=loadz(target_file(site,prior));ids=loadz(O/'freespace_targets'/f'{stem}.npz')['patch_id'];patch=np.isin(t['patch_id'],ids);inside=np.zeros(len(owner),bool);good=owner>=0;inside[good]=patch[owner[good]]
    outside=np.full(len(owner),np.nan);jj=np.flatnonzero(inside);n=t['normal'][owner[jj]].copy();n/=np.linalg.norm(n,axis=1)[:,None];n*=np.where((n*row['normal'][jj]).sum(1)<0,-1,1)[:,None]
    outside[jj]=np.einsum('ij,ij->i',row['xyz'][jj]-t['target'][owner[jj]],n)
    masks=[('image_only_all',cell['case_id']==1),('image_only_in_freespace_columns',(cell['case_id']==1)&inside),('gt_over_1m_outside_target',inside&(outside>1))]
    f=root/'preservation_features.npz'
    if f.exists():
        feat=loadz(f);masks += [('preservation_'+str(q),feat['quadrant']==q) for q in [0,1,2,3,-2]]
    rr=[]
    for label,mask in masks:
        v=dict(site=site,prior=prior,division=label,n_gt=int(mask.sum()))
        for method in ['FINALTRAIN_30000','A2','fix','gt_judgment_mesh']:
            p=root/'distances'/f'{method}.npz'
            if p.exists() and mask.any():
                s=loadz(p,['row_s'])['row_s'];v[method+'_completeness_pct']=float(100*np.mean(np.isfinite(s[mask])&(abs(s[mask])<=row['row_tau_m'][mask])))
            else:v[method+'_completeness_pct']=None
        rr.append(v)
    table('addendum2/fix/'+stem+'_risks_and_strata',rr)
    dump(D/'tables/addendum2/fix'/f'{stem}_risk_definition.json',dict(target_normal_oriented_to='AXES71 reference normal',signed_distance='dot(reference point - target point, oriented unit target normal)',target_plane_threshold_m=1.,target_file_sha256=sha(target_file(site,prior)),GT_used_for_risk_evaluation_only=True,scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
