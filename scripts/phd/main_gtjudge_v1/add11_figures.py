"""Two requested scientific figures only; no mesh rendering or new meshes."""
from add11 import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

COLORS=['#3978B7','#D85A30','#7955A1'];NAMES=['지금 규칙에서도 셈에 듦','바꾼 규칙으로 새로 셈에 듦','두 규칙 모두 뺌']

def main():
 for p in Path('/fonts').glob('*CJK*'):font_manager.fontManager.addfont(str(p))
 plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10})
 site='B173nb_b10';row=loadz(O/'scenes'/f'{site}__ALS'/'rows.npz',['xyz']);ref=row['xyz'];ms=['FINALTRAIN_30000','2DGS_30000'];q={m:loadz(W/'figure_points'/(m+'.npz')) for m in ms};new=np.concatenate([a['xyz'][a['new'].astype(bool)&~a['old'].astype(bool)] for a in q.values()]);assert len(new)
 grid=np.floor(new[:,:2]).astype('i4');cells,n=np.unique(grid,axis=0,return_counts=True);winner=int(np.argmax(n));center=cells[winner].astype(float)+.5
 inherited=O/'addendum6/selected/c1_B173nb_b10__ALS.json';section=json.loads(inherited.read_text())['section'];dr=np.array(section['end'])-section['start'];dr/=np.linalg.norm(dr);side=np.array([-dr[1],dr[0]]);cloud=np.concatenate([ref,*[a['xyz'] for a in q.values()]]);bounds=np.r_[cloud[:,:2].min(0)-1,cloud[:,:2].max(0)+1];t=(cloud[:,:2]-center)@dr;Aline=center+t.min()*dr;Bline=center+t.max()*dr;length=np.linalg.norm(Bline-Aline)
 def coord(P):v=P[:,:2]-Aline;return v@dr,v@side
 rs,rt=coord(ref);rkeep=(rs>=0)&(rs<=length)&(abs(rt)<=.5)
 fig,axes=plt.subplots(1,2,figsize=(12,6.4),layout='constrained')
 for ax,m in zip(axes,ms):
  z=q[m];P=z['xyz'];states=np.where(z['old'],0,np.where(z['new'],1,2));ax.scatter(ref[:,0],ref[:,1],s=.2,c='#DBDBDB',rasterized=True)
  for k in range(3):mask=states==k;ax.scatter(P[mask,0],P[mask,1],s=.4,c=COLORS[k],rasterized=True,linewidths=0)
  ax.plot([Aline[0],Bline[0]],[Aline[1],Bline[1]],color='#252525',lw=1);ax.set(xlim=bounds[[0,2]],ylim=bounds[[1,3]],xlabel='지역 X (m)',ylabel='지역 Y (m)',title='본 방법' if m=='FINALTRAIN_30000' else '2DGS');ax.set_aspect('equal')
 handles=[Line2D([],[],marker='o',linestyle='',color=c,label=n) for c,n in zip(COLORS,NAMES)]+[Line2D([],[],marker='o',linestyle='',color='#DBDBDB',label='참값 점')];fig.legend(handles=handles,loc='outside lower center',ncol=2);fig.savefig(F/'rule_top.png',dpi=240);plt.close(fig)
 fig=plt.figure(figsize=(12,10),layout='constrained');gs=fig.add_gridspec(2,2,height_ratios=[1.15,1]);ax=fig.add_subplot(gs[0,:]);ax.scatter(rs[rkeep],ref[rkeep,2],s=2,c='#BDBDBD',label='참값 점',rasterized=True)
 counts={}
 for m,marker,size in zip(ms,['o','x'],[3,6]):
  z=q[m];P=z['xyz'];s,t=coord(P);mask=(s>=0)&(s<=length)&(abs(t)<=.5);state=np.where(z['old'],0,np.where(z['new'],1,2));counts[m]={NAMES[k]:int((mask&(state==k)).sum()) for k in range(3)}
  for k in range(3):use=mask&(state==k);ax.scatter(s[use],P[use,2],s=size,c=COLORS[k],marker=marker,linewidths=.4,rasterized=True)
 ax.set(xlabel='A에서 선을 따른 거리 (m)',ylabel='지역 Z (m)',title='같은 선·폭 1m 단면: 본 방법 ○ / 2DGS ×');ax.legend(handles=handles,loc='upper right',ncol=2,fontsize=8);ax.grid(alpha=.15)
 tau=list(csv.DictReader((T/'tau_summary.csv').open()));palette=['#151515','#1D9E75','#9868C0','#2A78D6','#D99322'];names=['본 방법','LGDM','GeoGS','2DGS','CDGS']
 for panel,mode in enumerate(['fixed_cases','reclassified_cases']):
  ax=fig.add_subplot(gs[1,panel])
  for m,color,name in zip(A['presentation_methods'],palette,names):
   rr=[r for r in tau if r['method']==m and r['mode']==mode];rr.sort(key=lambda r:float(r['tau_multiplier']));x=[float(r['tau_multiplier']) for r in rr]
   for metric,style in [('completeness_pct','-'),('accuracy_new_pct','--')]:ax.plot(x,[float(r[metric+'_worst_gap_pp']) for r in rr],color=color,ls=style,marker='o',ms=3,label=name if style=='-' else None)
  ax.set(xlabel='τ 배수',ylabel='8칸 중 1위와 최대 차이 (%p)',title='(가) 경우 고정' if panel==0 else '(나) 경우도 다시 나눔',xticks=A['tau_multipliers']);ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
 fig.suptitle('τ 민감도: 실선 완전성 / 파선 바꾼 정확성',fontsize=12);fig.savefig(F/'rule_section_and_tau.png',dpi=240);plt.close(fig)
 dump(F/'rules.json',meta(colors=dict(zip(NAMES,COLORS)),source_methods=ms,reference_source=proof(O/'scenes'/f'{site}__ALS'/'rows.npz'),line=dict(A_local_xy=Aline.tolist(),Aprime_local_xy=Bline.tolist(),A_EPSG25832_xy=(Aline+[690953,5336071]).tolist(),Aprime_EPSG25832_xy=(Bline+[690953,5336071]).tolist(),direction_unit_xy=dr.tolist(),length_m=float(length),width_m=1.,selection_cell_local_xy=cells[winner].tolist(),selection_cell_new_points=int(n[winner]),selection='maximum pooled newly included case1 point count in1m XY cell; lexicographic tie; inherited c1 section direction',direction_source=proof(inherited)),section_counts=counts,section_reference_n=int(rkeep.sum()),map_all_points_drawn=True,new_mesh=False,mesh_rendering=False,tau_plot_combined_to_obey_two_image_limit=True));print('ADD11_FIGURES_DONE 2',flush=True)

if __name__=='__main__':main()
