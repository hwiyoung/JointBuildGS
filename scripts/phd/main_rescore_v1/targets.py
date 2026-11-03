"""Reference-free judgment targets; oracle changes only explicitly allowed cells."""
from common import *
def targets(site,prior):
 keys=['patch_id','centre','normal','tangent1','tangent2','kind','area','region','reason','n','u_mvs','sigma_P_m','prior_height_m','mvs_mean_m','photo_code','source_index']
 p=JA/'core_points'/f'{site}__{prior}.npz';d=loadz(p,keys);region=d['region'][5].copy();reason=d['reason'][5].copy()
 undecided=(region==9)&(d['n']>=4)&~np.isfinite(d['u_mvs'])&np.isfinite(d['mvs_mean_m'])&np.isfinite(d['prior_height_m'])
 region[undecided]=1 if prior=='ALS' else 2;reason[undecided]=2
 support=undecided&(d['photo_code']==0);refute=undecided&(d['photo_code']==1)
 region[support]=1;reason[support]=0;region[refute]=2;reason[refute]=1
 hp,hm,sp,um=[d[k] for k in ['prior_height_m','mvs_mean_m','sigma_P_m','u_mvs']]
 vp=sp**2;vm=um**2
 with np.errstate(divide='ignore',invalid='ignore'):
  agreement=(hp*vm+hm*vp)/(vm+vp);sigma=np.sqrt(vp*vm/(vp+vm))
 h=np.full(len(hp),np.nan);s=h.copy()
 for mask,height,sd in [(region==0,agreement,sigma),(np.isin(region,[1,4]),hp,sp),(region==2,hm,um)]:h[mask]=height[mask];s[mask]=sd[mask]
 s[undecided&(region==2)]=np.nan
 save=dict(patch_id=d['patch_id'],source_index=d['source_index'],region=region,reason=reason,target_height_m=h,target_sigma_m=s,undecided_before=undecided,surface_exists=np.isin(region,[0,1,2,4])&np.isfinite(h))
 out=O/'targets_v2'/f'{site}__{prior}.npz';savez(out,**save)
 v2=loadz(O/'cells_v2'/f'{site}__{prior}.npz');assert np.array_equal(v2['patch_id'],d['patch_id']);cell=v2['cell_v2'];upper=h.copy()
 upper[cell==0]=np.where(np.isfinite(um[cell==0]),agreement[cell==0],hp[cell==0]);upper[cell==1]=hm[cell==1];upper[np.isin(cell,[2,4])]=hp[np.isin(cell,[2,4])]
 savez(O/'targets_oracle'/f'{site}__{prior}.npz',patch_id=d['patch_id'],target_height_m=upper,cell_v2=cell,surface_exists=np.isfinite(upper),GT_exception='only cells 0,1,2,4 choose the target; cells 3,5,6,9 preserve method target')
 fusion=d['region'][4];hf=np.where(np.isin(fusion,[1,4]),hp,np.where(fusion==2,hm,np.nan));savez(O/'targets_fusion'/f'{site}__{prior}.npz',patch_id=d['patch_id'],region=fusion,target_height_m=hf,surface_exists=np.isfinite(hf))
 comparison=dict(status='확인 전');training=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/targets'/f'{site}__{prior}.npz'
 if training.exists():
  train=loadz(training,['source_index','target_height_m']);lookup={int(k):i for i,k in enumerate(train['source_index'])};complete=all(int(k) in lookup for k in d['source_index'])
  if complete:
   ix=np.array([lookup[int(k)] for k in d['source_index']]);a=train['target_height_m'][ix];finite=np.isfinite(h)&np.isfinite(a);same=bool(np.array_equal(np.isfinite(h),np.isfinite(a)));maximum=float(np.max(abs(a[finite]-h[finite]))) if finite.any() else 0.
   comparison=dict(status='PASS' if same and maximum<=.001 else 'FAIL_DIFFERENT_TARGETS',file=str(training),sha256=sha(training),join='source_index',max_height_difference_m=maximum,finite_mask_equal=same,n=int(finite.sum()),note='FINALTRAIN target heights only; its missing-sigma training replacement is not copied into RESCORE')
  else:comparison=dict(status='확인 불가',file=str(training),reason='FINALTRAIN source_index가 모든 핵심점을 포함하지 않음')
 return dict(site=site,prior=prior,n=len(h),source=str(p),source_sha256=sha(p),output_sha256=sha(out),undecided_patches=int(undecided.sum()),undecided_area_m2=float(d['area'][undecided].sum()),undecided_regions={str(k):dict(n=int((undecided&(region==k)).sum()),area_m2=float(d['area'][undecided&(region==k)].sum())) for k in [1,2]},sigma_missing_area_m2=float(d['area'][np.isfinite(h)&~np.isfinite(s)].sum()),sigma_W_used=False,r_added=False,training_v2_comparison=dict(status='확인 전',reason='JUDGEAPPLY 학습용 v2 파일은 별도 확인'),finaltrain_target_comparison=comparison,source_tag='[이 발주에서 냄]')
def main():
 start=time.monotonic();cfg();import sys;site=sys.argv[1];assert site in SITES[:3];rows=[targets(site,p) for p in ['LoD2','ALS']];table('target_diagnostics_'+site,rows);timing('targets_'+site,start)
if __name__=='__main__':main()
