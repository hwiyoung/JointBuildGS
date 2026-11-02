"""Add shared count scales and legends to existing histogram figures; no recomputation."""
import shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,colors
from common import *
ROOT=OUT/'screen_sim';D=DOC/'screen_sim/figures'
def main():
 font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams['font.family']='Noto Sans CJK JP';plt.rcParams['axes.unicode_minus']=False
 paths=list(D.glob('*_removed_overhead.json'));assert len(paths)==8
 maximum=max(np.max(p['hist']) for f in paths for p in json.loads(f.read_text())['panels']);norm=colors.Normalize(0,np.log10(1+maximum))
 original=ROOT/'figure_versions/unlabelled';original.mkdir(parents=True,exist_ok=True)
 for path in paths:
  meta=json.loads(path.read_text());lo,hi=np.array(meta['extent']);cams=np.array(meta['cameras']);poly=np.array(meta['evaluation_polygon']);fig,axes=plt.subplots(2,2,figsize=(12,11),sharex=True,sharey=True,layout='constrained')
  for ax,p in zip(axes.ravel(),meta['panels']):
   hist=np.array(p['hist']);xe=np.linspace(lo[0],hi[0],hist.shape[0]+1);ye=np.linspace(lo[1],hi[1],hist.shape[1]+1);im=ax.pcolormesh(xe,ye,np.log10(1+hist.T),cmap='magma',norm=norm,shading='auto');ax.plot(poly[:,0],poly[:,1],c='cyan',label='평가 상자');ax.scatter(cams[:,0],cams[:,1],s=5,c='lime',marker='^',label='카메라');ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),xlabel='지역 X / m',ylabel='지역 Y / m',title=f'{p["variant"]} · 그림 범위 밖 {p["outside_context"]:,}개');ax.set_aspect('equal');ax.legend(loc='upper right',fontsize=8)
  fig.suptitle(meta['state']+' · 그림 범위: 평가 상자 XY 최솟값·최댓값에서 ±200 m');fig.colorbar(im,ax=axes.ravel().tolist(),label='log10(1 + 격자 안 삭제 수), 모든 상태 공통 눈금',shrink=.7)
  for ext in ['png','pdf','json']:
   source=path.with_suffix('.'+ext);dest=original/source.name
   if not dest.exists():shutil.copy2(source,dest)
  fig.savefig(path.with_suffix('.png'),dpi=160);fig.savefig(path.with_suffix('.pdf'));plt.close(fig);meta.update(display_revision=2,count_scale='log10(1+count)',global_count_max=int(maximum),legend=dict(camera='lime triangle',evaluation_box='cyan polygon'));dump(path,meta)
 for path in D.glob('*_radius_contribution.json'):
  meta=json.loads(path.read_text());xe=np.array(meta['x_log10_edges']);ye=np.array(meta['y_log10_edges']);fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained',sharex=True,sharey=True);maximum=max(np.max(p['hist']) for p in meta['panels']);norm=colors.Normalize(0,np.log10(1+maximum))
  for ax,p,cmap in zip(axes,meta['panels'],['Blues','Oranges']):
   im=ax.pcolormesh(xe,ye,np.log10(1+np.array(p['hist']).T),cmap=cmap,norm=norm,shading='auto');ax.set(title='카메라 ≤30 m' if p['near30'] else '카메라 >30 m',xlabel='log10(최대 화면 반지름 / px)',ylabel='log10(203장 총 색 기여)');fig.colorbar(im,ax=ax,label='log10(1 + 가우시안 수)',shrink=.7)
   for th in [20,102.4,256,512]:ax.axvline(np.log10(th),c='black',ls='--',lw=.7);ax.text(np.log10(th),ye[-1],f'{th:g}px',rotation=90,va='top',fontsize=7)
  fig.suptitle(f'{meta["state"]} · 색 기여 0: {meta["zero_total_contribution"]:,}개 (축 밖)')
  for ext in ['png','pdf','json']:
   source=path.with_suffix('.'+ext);dest=original/source.name
   if not dest.exists():shutil.copy2(source,dest)
  fig.savefig(path.with_suffix('.png'),dpi=160);fig.savefig(path.with_suffix('.pdf'));plt.close(fig);meta.update(display_revision=2,count_scale='log10(1+count)',panel_shared_count_max=int(maximum));dump(path,meta)
 dump(D/'display_revision.json',dict(at=stamp(),revision=2,reason='Explicit legends and count colorbars; overhead count scale shared across all eight states; numerical histograms, thresholds and selected views unchanged',scientific_verdict=None))
if __name__=='__main__':main()
