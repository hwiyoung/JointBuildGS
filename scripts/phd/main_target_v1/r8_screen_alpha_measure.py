"""Replay original per-pixel compositing from unmodified forward buffers on CPU."""
import numpy as np
from common import *
from r8_screen_measure_r1 import stat
ROOT=OUT/'r8_screen_prune'
def main():
 lock=json.loads((CFG/'r8_screen_alpha.lock.json').read_text());assert sha(__file__)==lock['files'][__file__]
 a=dict(np.load(ROOT/'alpha_raw.npz'));ref=dict(np.load(ROOT/'alpha_reference.npz'));selected=a['selected'];union=a['union'];is_selected=np.isin(union,selected);selected_map=np.searchsorted(union,selected);present=selected_map<len(union);present[present]&=union[selected_map[present]]==selected[present]
 mx=np.zeros(len(union),dtype='f4');subsetmx=mx.copy();full_est=[];sub_est=[];full_rgb=[];sub_rgb=[];pixel_full=[];pixel_sub=[];nonzero_pairs=0
 # No selected row contributes at the other pixels: subset alpha is exactly zero,
 # all accepted contributions are nonnegative, and subset never reaches early exit.
 assert np.all(ref['subset_alpha']<.01);assert np.array_equal(a['pixels'],np.argwhere(ref['subset_alpha']>0))
 for y,x in a['pixels']:
  tile=(y//16)*((ref['full_alpha'].shape[1]+15)//16)+x//16;k=int(np.searchsorted(a['unique_tiles'],tile));ids=a['point_list'][a['offsets'][k]:a['offsets'][k+1]];ix=np.searchsorted(union,ids);tr=a['trans'][ix];tu,tv,tw=tr[:,:3],tr[:,3:6],tr[:,6:9]
  # Float32 operations use the same preprocessed geometry and sorted order.
  p=np.cross(np.float32(x)*tw-tu,np.float32(y)*tw-tv)
  with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
   s=p[:,:2]/p[:,2:3];rho3=np.sum(s*s,axis=1);delta=a['xy'][ix]-np.array([x,y],dtype='f4');rho2=np.float32(2)*np.sum(delta*delta,axis=1);rho=np.minimum(rho3,rho2);depth=(s[:,0]*tw[:,0]+s[:,1]*tw[:,1])+tw[:,2];alpha=np.minimum(np.float32(.99),a['normal_opacity'][ix,3]*np.exp(np.float32(-.5)*rho))
  ok=(p[:,2]!=0)&(depth>=.2)&(rho>=0)&(alpha>=np.float32(1/255));alpha[~ok]=0
  def compose(aa):
   after=np.cumprod(np.float32(1)-aa,dtype='f4');cross=np.flatnonzero(after<np.float32(.0001));end=int(cross[0]) if len(cross) else len(aa);before=np.r_[np.float32(1),after[:-1]];w=aa*before;w[end:]=0;T=after[end-1] if end else np.float32(1);return w,float(np.float32(1)-T),np.sum(a['color'][ix]*w[:,None],axis=0,dtype='f4')
  w,al,col=compose(alpha);sw,sal,scol=compose(np.where(is_selected[ix],alpha,np.float32(0)));np.maximum.at(mx,ix,w*is_selected[ix]);np.maximum.at(subsetmx,ix,sw);nonzero_pairs+=int(np.count_nonzero(w*is_selected[ix]));full_est.append(al);sub_est.append(sal);full_rgb.append(col);sub_rgb.append(scol);pixel_full.append(ref['full_alpha'][y,x]);pixel_sub.append(ref['subset_alpha'][y,x])
 y,x=a['pixels'].T;errors=dict(full_alpha_max_abs=float(np.max(np.abs(np.array(full_est)-pixel_full))),subset_alpha_max_abs=float(np.max(np.abs(np.array(sub_est)-pixel_sub))),full_rgb_max_abs=float(np.max(np.abs(np.array(full_rgb)-ref['full_rgb'][:,y,x].T))),subset_rgb_max_abs=float(np.max(np.abs(np.array(sub_rgb)-ref['subset_rgb'][:,y,x].T))))
 tol=lock['alpha_replay_max_abs_tolerance'];passed=all(v<=tol for v in errors.values());result=np.zeros(len(selected),dtype='f4');subresult=result.copy();result[present]=mx[selected_map[present]];subresult[present]=subsetmx[selected_map[present]]
 np.savez_compressed(ROOT/'alpha_replay.npz',row=selected,max_alphaT=result,subset_max_alphaT=subresult,pixels=a['pixels'],full_alpha_est=full_est,subset_alpha_est=sub_est,full_rgb_est=full_rgb,subset_rgb_est=sub_rgb)
 dump(ROOT/'alpha_measure.json',dict(at=stamp(),status='VALIDATED_FLOAT32_CPU_REPLAY' if passed else 'REPLAY_VALIDATION_FAILED',errors=errors,tolerance=tol,selected=len(selected),nonzero_max=int(np.count_nonzero(result)),zero_max=int((result==0).sum()),max_alphaT=stat(result) if passed else None,nonzero_max_alphaT=stat(result[result>0]) if passed else None,subset_max_alphaT=stat(subresult) if passed else None,accepted_selected_pixel_pairs=nonzero_pairs if passed else None,nonzero_subset_pixels=len(y),zero_other_pixels=len(ref['full_alpha'].ravel())-len(y),method='Unmodified original CUDA forward buffers; CPU float32 sorted alpha*T replay validated against actual full/subset RGB and alpha. Omitted pixels have exact zero subset alpha and nonnegative contributions; subset alpha<0.01 precludes early-exit hiding.',optimization_steps=0,scientific_verdict=None));assert passed,errors;print('ALPHA_VALIDATED',errors,int(np.count_nonzero(result)),flush=True)
if __name__=='__main__':main()
