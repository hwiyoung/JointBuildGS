"""Map scored far points to actual rendered max contributors through visible train pixels.
Keep all observation-level votes; point attribution is the modal Gaussian ID, ties
resolved by the lowest original Gaussian index. Unseen points remain unavailable.
"""
from common import *
from target_quality import REGIONS
from scipy.sparse import coo_matrix
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
def main():
 start=time.monotonic();root=O/'lineage';rec=json.loads((root/'receipt.json').read_text());assert rec['status']=='PASS_EXACT_SAVED_DEPTH_MAX_ALPHA_T';p=loadz(O/'checks/check_b_LoD2_far_points.npz');xyz=p['xyz'].astype(float);N=len(xyz);g=loadz(root/'gaussian_lineage.npz');rr=FT/'meshes/B173nb_b10__LoD2/render';views=[v for v in json.loads((rr/'receipt.json').read_text())['views'] if not v['virtual']];P=[];G=[];vr=[]
 for v in views:
  E=np.asarray(v['W2C']);K=np.asarray(v['K']);q=xyz@E[:3,:3].T+E[:3,3];front=q[:,2]>0;ids=np.flatnonzero(front);a=q[ids];u=np.rint(K[0,0]*a[:,0]/a[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*a[:,1]/a[:,2]+K[1,2]).astype(int);inside=(u>=0)&(w>=0)&(u<v['width'])&(w<v['height']);ids=ids[inside];u=u[inside];w=w[inside];depth=loadz(rr/v['file'],['depth'])['depth'];index=loadz(root/'views'/v['file'],['max_gaussian'])['max_gaussian'];visible=(depth[w,u]>0)&(abs(depth[w,u]-q[ids,2])<=.25)&(index[w,u]>=0);ids=ids[visible];gg=index[w[visible],u[visible]];P.append(ids);G.append(gg);vr.append(dict(name=v['name'],points=len(ids)));savez(root/'point_views'/v['file'],far_point_index=ids,max_gaussian=gg)
 a=np.concatenate(P) if P else np.array([],'i8');b=np.concatenate(G) if G else np.array([],'i8');matrix=coo_matrix((np.ones(len(a),'i4'),(a,b)),shape=(N,len(g['origin']))).tocsr();chosen=np.full(N,-1,'i4');support=np.zeros(N,'i4');votes=np.asarray(matrix.sum(1)).ravel()
 for i in np.flatnonzero(np.diff(matrix.indptr)):
  begin,end=matrix.indptr[i:i+2];d=matrix.data[begin:end];j=matrix.indices[begin:end];k=np.argmax(d);chosen[i]=j[k];support[i]=d[k]
 valid=chosen>=0;j=np.maximum(chosen,0);initial=np.full(N,3,'i1');current=np.full(N,4,'i1');initial[valid&(g['origin'][j]==0)]=2;m=valid&(g['origin'][j]==1);initial[m]=np.where(g['initial_patch'][j[m]]==p['source_index'][m],0,1);current[valid&(g['target_tag'][j]==0)]=2;current[valid&(g['target_tag'][j]==2)]=3;m=valid&(g['target_tag'][j]==1);current[m]=np.where(g['current_patch'][j[m]]==p['source_index'][m],0,1)
 initial_names=['같은 패치 계보','다른 패치 계보','SfM 배경 계보','확인 불가'];current_names=['같은 패치에 묶임','다른 패치에 묶임','배경','풀림','확인 불가'];rows=[]
 for r in [0,1,2,3,4,9]:
  for i in range(4):
   for k in range(5):
    m=(p['judge_region']==r)&(initial==i)&(current==k)
    if not m.any():continue
    rows.append(dict(judgment_region=r,judgment_name=REGIONS[r],initial_lineage=initial_names[i],current_binding=current_names[k],points=int(m.sum()),fraction_of_all_far_points=float(m.sum()/N) if N else None,mean_support_views=float(votes[m].mean()),attribution='modal actual max-alpha*T Gaussian over depth-matched original train views; 0.25 m visibility; lowest original ID on tie'))
 table('check_b_LoD2_far_point_lineage',rows);savez(root/'far_point_attribution.npz',sample_index=p['sample_index'],selected_gaussian=chosen,selected_full_gaussian=np.where(valid,g['full_gaussian_index'][j],-1),total_visible_views=votes,modal_gaussian_votes=support,initial_lineage=initial,current_binding=current,judge_region=p['judge_region'])
 dump(root/'join.json',dict(status='PASS_WITH_EXPLICIT_UNSEEN',far_points=N,attributed_points=int(valid.sum()),unavailable_points=int((~valid).sum()),reason_unavailable='No positive-depth training pixel within the inherited 0.25 m visibility tolerance',views=vr,threshold_m=.25,rule='Modal maximum-contributor Gaussian, one vote per visible original training view; ties lowest original Gaussian ID. Attribution of the rasterized evidence, not a unique ancestry for a fused TSDF vertex.',sources={str(x):sha(x) for x in [O/'checks/check_b_LoD2_far_points.npz',root/'receipt.json',root/'gaussian_lineage.npz']},seconds=time.monotonic()-start,scientific_verdict=None));print('LINEAGE_JOIN',N,int(valid.sum()),flush=True)
if __name__=='__main__':main()
