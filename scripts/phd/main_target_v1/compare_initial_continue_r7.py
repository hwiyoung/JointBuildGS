"""Compare matched initial seeds and stored initial Gaussian arrays, without optimization."""
import numpy as np
from common import *
from diagnose_als_continue_r7 import load
from report_stage0 import plt,save,csvout

def compare(a,b):
 eq=(a==b)|(np.isnan(a)&np.isnan(b)) if a.dtype.kind=='f' else a==b
 same=eq.reshape(len(a),-1).all(1) if a.ndim>1 else eq
 out=dict(rows=len(a),different_rows=int((~same).sum()),byte_equal=a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes())
 if a.dtype.kind in 'fiu':
  d=np.abs(a.astype(float)-b.astype(float));d=d[np.isfinite(d)];out['max_abs_delta']=float(d.max()) if len(d) else None
 return out

def main():
 root=OUT/'r7_continue/diagnostics/ALS';seeds=[load(OUT/v/'stage1/B173nb_b10_ALS/seeds.npz') for v in ['r2','r7']];snaps=[load(OUT/v/'runs'/f'tg_B173nb_b10_ALS_s0_{v}/model/target_monitor/snapshot_0.npz') for v in ['r6','r7']];a,b=seeds;shared,i,j=np.intersect1d(a['keep_original'],b['keep_original'],return_indices=True);bg=[np.flatnonzero(s['origin']==0) for s in seeds];assert len(bg[0])==len(bg[1]);rows=[]
 for population,ii,jj in [('background',bg[0],bg[1]),('matched_prior_original_index',i,j)]:
  for field in ['xyz','target','normal','quaternion','sigma','patch','region','uncertainty_replaced']:
   rows.append(dict(population=population,source='seeds',field=field,**compare(a[field][ii],b[field][jj])))
  for field in ['xyz','scale','opacity','anchor','normal','sigma','initial_scale','initial_large_background']:
   rows.append(dict(population=population,source='snapshot0',field=field,**compare(snaps[0][field][ii],snaps[1][field][jj])))
 t=[load(OUT/r/'targets/B173nb_b10_ALS.npz') for r in ['r2','r7']];target=[]
 for k in sorted(set(t[0])&set(t[1])):
  if t[0][k].shape==t[1][k].shape and t[0][k].dtype.kind in 'fiub':target.append(dict(field=k,**compare(t[0][k],t[1][k])))
 rng=json.loads((root.parent/'resume_and_rng.json').read_text())['rng'];rngcmp={k:rng['r6']['saved'].get(k)==rng['r7']['saved'].get(k) for k in set(rng['r6']['saved'])|set(rng['r7']['saved'])}
 result=dict(at=stamp(),shared_prior_seeds=len(shared),r6_only_prior_seeds=len(a['keep_original'])-len(shared),r7_only_prior_seeds=len(b['keep_original'])-len(shared),matched_fields=rows,target_fields=target,stored_rng_and_camera_equality_at7000=rngcmp,scientific_verdict=None);dump(root/'initial_matched_comparison.json',result);dump(DOC/'tables/continue_r7_ALS_initial_comparison.json',result);csvout('continue_r7_ALS_initial_comparison',rows)
 fig,axes=plt.subplots(1,2,figsize=(13,5))
 for ax,pop in zip(axes,['background','matched_prior_original_index']):
  rr=[r for r in rows if r['population']==pop and r['source']=='snapshot0'];ax.barh([r['field'] for r in rr],[r['different_rows'] for r in rr],color='#437ea9');ax.set(xlabel='값이 다른 씨앗 수',title='배경' if pop=='background' else '같은 원본 번호의 사전 씨앗');ax.tick_params(axis='y',labelsize=8)
 fig.subplots_adjust(top=.82,bottom=.18,left=.12,wspace=.4);save(fig,'continue_r7_ALS_initial_comparison','r6·r7 항공 LiDAR: 같은 씨앗의 처음 상태 비교',result,'입력 XYZ·색이 같아도 전체 이웃 구성이 다른 초기 크기는 별도로 비교 · 원본 번호가 없는 행은 대입하지 않음')
 print('INITIAL_COMPARISON',len(shared),[(r['population'],r['field'],r['different_rows']) for r in rows if r['source']=='snapshot0'],flush=True)
if __name__=='__main__':main()
