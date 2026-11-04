"""Original modal max-contributor join, now for all inherited reference rows."""
from common import *
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree
import sys
def main(site,prior):
    cfg();stem=f'{site}__{prior}';root=O/'stage1'/stem;rows=loadz(root/'rows.npz');g=loadz(root/'gaussians.npz');lin=root/'lineage';rec=json.loads((lin/'receipt.json').read_text());assert rec['status']=='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T'
    ids=loadz(lin/'gaussian_lineage.npz')['full_gaussian_index'];rr=Path(rec['render_root']);views=[v for v in json.loads((rr/'receipt.json').read_text())['views'] if not v['virtual']]
    xyz=rows['lineage_xyz'];N=len(xyz);P=[];G=[];clear=np.zeros(N,'i4');unknown=np.zeros(N,'i4');missing=rows['result_type']==3
    for v in views:
        E=np.array(v['W2C']);K=np.array(v['K']);q=xyz@E[:3,:3].T+E[:3,3];front=q[:,2]>0;ii=np.flatnonzero(front);a=q[ii];u=np.rint(K[0,0]*a[:,0]/a[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*a[:,1]/a[:,2]+K[1,2]).astype(int)
        keep=(u>=0)&(w>=0)&(u<v['width'])&(w<v['height']);ii=ii[keep];u=u[keep];w=w[keep];dep=loadz(rr/v['file'],['depth'])['depth'][w,u];index=loadz(lin/'views'/v['file'],['max_gaussian'])['max_gaussian'][w,u]
        positive=dep>0;unoccluded=positive&(dep>=q[ii,2]-.25);clear[ii[unoccluded]]+=1;unknown[ii[~positive]]+=1
        match=positive&(abs(dep-q[ii,2])<=.25)
        # No surface has no surface-depth correspondence to enforce. Count the
        # actual contributor at the GT projection, including foreground blockers.
        # Unoccluded-view counts remain a separate quantity above.
        match[missing[ii]]=positive[missing[ii]];match&=index>=0
        P.append(ii[match]);G.append(index[match])
    a=np.concatenate(P);b=np.concatenate(G);matrix=coo_matrix((np.ones(len(a),'i4'),(a,b)),shape=(N,len(ids))).tocsr();chosen=np.full(N,-1,'i8');votes=np.asarray(matrix.sum(1)).ravel();support=np.zeros(N,'i4')
    for i in np.flatnonzero(np.diff(matrix.indptr)):
        lo,hi=matrix.indptr[i:i+2];d=matrix.data[lo:hi];j=matrix.indices[lo:hi];pick=np.argmax(d);chosen[i]=ids[j[pick]];support[i]=d[pick]
    valid=chosen>=0;j=np.maximum(chosen,0);tag=np.full(N,4,'i1');tag[valid&(g['tag'][j]==0)]=3;tag[valid&(g['tag'][j]==2)]=2
    attached=valid&(g['tag'][j]==1);current_patch=np.full(N,-1,'i8');current_patch[attached]=g['patch_ids'][g['target_index'][j[attached]]]
    tag[attached]=np.where(current_patch[attached]==rows['source_index'][attached],0,1)
    t=loadz(FT/'targets'/f'{stem}.npz');other=tag==1;height_diff=np.full(N,np.nan);other_region=np.full(N,-1,'i1');target_ok=other&(rows['source_index']>=0)
    delta=t['target'][current_patch[target_ok]]-t['target'][rows['source_index'][target_ok]];height_diff[target_ok]=(delta*t['normal'][rows['source_index'][target_ok]]).sum(1);other_region[target_ok]=t['judge_region'][current_patch[target_ok]]
    tangent=np.full(N,np.nan);excess=tangent.copy();first=np.full(N,-1,'i4');rel=tag==2;tangent[rel]=g['tangent_m'][j[rel]];excess[rel]=g['normal_excess_m'][j[rel]];first[rel]=g['first_release_checkpoint'][j[rel]]
    # Missing rows: exact Euclidean 0.25 m neighborhood of V0 centers.
    tree=cKDTree(g['xyz']);near_count=np.zeros(N,'i4');opacity=np.full(N,np.nan);tag_counts=np.zeros((N,3),'i4')
    for i,near in zip(np.flatnonzero(missing),tree.query_ball_point(rows['xyz'][missing],.25,workers=2)):
        near=np.asarray(near,'i8');near_count[i]=len(near)
        if len(near):opacity[i]=np.median(g['opacity'][near]);tag_counts[i]=np.bincount(g['tag'][near],minlength=3)
    save=dict(selected_gaussian=chosen,current_binding=tag,visible_views=votes,modal_votes=support,unoccluded_positive_depth_views=clear,unknown_zero_depth_views=unknown,other_target_judgment=other_region,other_target_normal_height_difference_m=height_diff,released_target_tangent_m=tangent,released_target_excess_m=excess,first_release_checkpoint=first,near_025m_count=near_count,near_025m_opacity_median=opacity,near_025m_tag_counts=tag_counts)
    savez(root/'attribution.npz',**save)
    out=[];modes=[('original',rows['old_cell'])];cp=O/'stage0'/stem/'cells.npz'
    if cp.exists():modes.append(('score',loadz(cp,['score_cell_1p0'])['score_cell_1p0']))
    for mode,cells in modes:
        for cell in [0,1,2,4]:
            for region in [-1,0,1,2,3,4,9] if cell in [2,4] else [-1]:
                base=(cells==cell)&((rows['judge_region']==region) if region>=0 else True);den=int(base.sum())
                for typ in range(4):
                    typden=int((base&(rows['result_type']==typ)).sum())
                    for label in range(5):
                        m=base&(rows['result_type']==typ)&(tag==label);count=int(m.sum());out.append(dict(site=site,prior=prior,cell_basis=mode,cell=cell,judgment_region=region,result_type=typ,binding=label,n_gt=count,cell_n_gt=den,cell_fraction=count/den if den else None,result_type_fraction=count/typden if typden else None,small='적음' if den<1000 else ''))
    table('stage1/'+stem+'_attribution',out)
    dump(root/'join.json',dict(status='PASS_WITH_EXPLICIT_UNAVAILABLE',rows=N,attributed=int(valid.sum()),unavailable=int((~valid).sum()),
      bindings={0:'same patch',1:'other patch',2:'released',3:'background',4:'unavailable'},missing_attribution='actual max contributor at projected GT pixel in every positive-depth train view, including foreground blockers',missing_visibility='separate count: positive saved depth at or behind GT minus 0.25 m; zero-depth views unknown, not asserted clear',sources={str(lin/'receipt.json'):sha(lin/'receipt.json'),str(root/'rows.npz'):sha(root/'rows.npz')},scientific_verdict=None))
    print('STAGE1_JOIN_COMPLETE',stem,N,int(valid.sum()),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
