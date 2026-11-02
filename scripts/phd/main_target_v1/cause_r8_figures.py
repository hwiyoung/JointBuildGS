"""Shared-scale static scientific figures; each figure has its numeric JSON companion."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from common import *
ROOT=OUT/'r8_lod2_cause'
for p in Path('/fonts').glob('*CJK*Regular.ttc'):
    font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(p)).get_name();break
plt.rcParams['axes.unicode_minus']=False
COLORS=['#4c94b2','#d89537','#a8588e','#d5a7bd']
def save(fig,name,data):
    root=ROOT/'figures';root.mkdir(exist_ok=True)
    fig.savefig(root/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(root/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
    dump(root/(name+'.json'),dict(data=data,scientific_verdict=None))
def main():
    summary=json.loads((ROOT/'summary.json').read_text());cells=json.loads((ROOT/'counts.json').read_text())['rows'];views=json.loads((ROOT/'render_views.json').read_text())['rows'];b=json.loads((ROOT/'boundaries.json').read_text())
    keys=[r['state'] for r in summary['states']];ymax=max(sum(r['count'] for r in cells if r['state']==key and r['xy_bin']==x and r['height_bin']==h) for key in keys for x in range(4) for h in range(4))*1.08
    loadmax=max(r['overlaps'] for r in views)*1.06
    ticks=[f'가로{x+1}\n높이{h+1}' for x in range(4) for h in range(4)]
    caption='가로 1 상자 안 · 2 밖 50 m 안 · 3 50~200 m · 4 200 m 넘음\n'+' · '.join(f'높이{i+1} {v}' for i,v in enumerate(b['height_labels']))
    for key in keys:
        rows=[r for r in cells if r['state']==key];fig,ax=plt.subplots(figsize=(12,5));bottom=np.zeros(16)
        for tag in sorted({r['tag'] for r in rows}):
            rr=[r for r in rows if r['tag']==tag];vals=np.array([next(r['count'] for r in rr if r['xy_bin']==x and r['height_bin']==h) for x in range(4) for h in range(4)])
            ax.bar(np.arange(16),vals,bottom=bottom,color=COLORS[tag],label=rr[0]['provenance']);bottom+=vals
        ax.set(xticks=np.arange(16),xticklabels=ticks,ylim=(0,ymax),ylabel='가우시안 수',title=key+' · 밀도 제어 직전 PLY');ax.ticklabel_format(axis='y',style='sci',scilimits=(6,6));ax.legend();ax.grid(axis='y',alpha=.2)
        fig.text(.06,-.02,caption,fontsize=9);save(fig,'counts_'+key,dict(rows=rows,y_limits=[0,ymax],boundaries=b['height_local_m'],height_labels=b['height_labels']))
        rr=[r for r in views if r['state']==key];fig,ax=plt.subplots(figsize=(12,4.2));ax.plot([r['view_index'] for r in rr],[r['overlaps'] for r in rr],color='#346a8d',lw=1)
        top=sorted(rr,key=lambda r:-r['overlaps'])[:5]
        for i,r in enumerate(top):ax.scatter(r['view_index'],r['overlaps'],color='#b63b4c',s=14);ax.annotate(str(i+1),(r['view_index'],r['overlaps']),xytext=(3,5),textcoords='offset points',fontsize=8)
        ax.set(xlim=(0,202),ylim=(0,loadmax),xlabel='학습 영상 번호 (이름순, 0~202)',ylabel='가우시안–타일 겹침 수',title=key+' · 203장 전부');ax.ticklabel_format(axis='y',style='sci',scilimits=(6,6));ax.grid(alpha=.2);save(fig,'load_'+key,dict(rows=rr,top5=top,y_limits=[0,loadmax]))
    fig,axes=plt.subplots(3,4,figsize=(18,10),sharex=True,sharey=True)
    for ax,key in zip(axes.flat,keys):
        rr=[r for r in views if r['state']==key];ax.plot([r['view_index'] for r in rr],[r['overlaps']/1e6 for r in rr],lw=.8);ax.set(title=key,ylim=(0,loadmax/1e6));ax.grid(alpha=.2)
    fig.supxlabel('학습 영상 번호 (이름순)');fig.supylabel('가우시안–타일 겹침 (백만)');fig.tight_layout();save(fig,'load_all',dict(rows=views,y_limits=[0,loadmax/1e6]))
    pairs=['base_LoD2_7000','r8_LoD2_7000'];zs=[np.load(ROOT/'states'/key/'arrays.npz')['xyz'][:,2].astype(float)-b['ground_local_m'] for key in pairs]
    edges=np.linspace(min(z.min() for z in zs),max(z.max() for z in zs),121);zoom=np.arange(-100, max(101,int(np.ceil(b['camera_median_local_m']-b['ground_local_m']))+101),1)
    ymaxs=[max(np.histogram(z,ee)[0].max() for z in zs)*1.5 for ee in [edges,zoom]]
    fig,axes=plt.subplots(2,2,figsize=(13,8),sharey='row');data=[]
    for i,(key,z) in enumerate(zip(pairs,zs)):
        vals=np.histogram(z,edges)[0];zvals=np.histogram(z,zoom)[0]
        for j,(ee,vv,title) in enumerate([(edges,vals,'전체 높이 범위'),(zoom,zvals,'지면 주변 확대')]):
            ax=axes[j,i];ax.stairs(vv,ee,fill=True,alpha=.7,color=COLORS[i]);ax.set(title=key+' · '+title,xlabel='지면 기준 높이 (m)',yscale='log',ylim=(.8,ymaxs[j]));ax.grid(alpha=.2)
            for threshold,label in zip(b['height_local_m'],b['height_boundary_names']):ax.axvline(threshold-b['ground_local_m'],c='#a33140',lw=.7,ls='--')
        data.append(dict(state=key,count=len(z),min=float(z.min()),max=float(z.max()),full_edges_m=edges.tolist(),full_counts=vals.tolist(),zoom_edges_m=zoom.tolist(),zoom_counts=zvals.tolist(),below_zoom=int((z<zoom[0]).sum()),above_zoom=int((z>zoom[-1]).sum())))
        axes[1,i].text(.02,.95,f'확대 범위 밖: 아래 {data[-1]["below_zoom"]:,} / 위 {data[-1]["above_zoom"]:,}',transform=axes[1,i].transAxes,va='top',fontsize=8)
    # Same y-axis across both states in each row, including empty bins in the JSON.
    for j in range(2):
        upper=max(ax.get_ylim()[1] for ax in axes[j]);[ax.set_ylim(.8,upper) for ax in axes[j]]
    axes[0,0].set_ylabel('가우시안 수 (로그)');axes[1,0].set_ylabel('가우시안 수 (로그)');fig.tight_layout();save(fig,'height_LoD2_7000',dict(states=data,boundaries=b['height_local_m'],ground=b['ground_local_m']))
    print('FIGURES_COMPLETE',len(keys),flush=True)
if __name__=='__main__':main()
