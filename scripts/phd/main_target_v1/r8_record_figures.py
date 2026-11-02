"""Static scientific figures and exact companion data for the recorded continuation."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from common import *
ROOT=OUT/'r8_recorded_continue';OLD=OUT/'r8_lod2_cause';D=ROOT/'stop_diagnostic'
NAMES=['배경','패치','풀림: 100회 자손','풀림: 그 밖'];COLORS=['#4c94b2','#d89537','#a8588e','#d5a7bd']
for p in Path('/fonts').glob('*CJK*Regular.ttc'):
    font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(p)).get_name();break
plt.rcParams['axes.unicode_minus']=False
def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]
def save(fig,name,data):
    d=ROOT/'figures';d.mkdir(exist_ok=True)
    fig.savefig(d/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(d/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
    dump(d/(name+'.json'),dict(data=data,scientific_verdict=None))
def main():
    cfg=read(CFG/'r8_record_continue.json');stop=read(ROOT/'STOP_LoD2.json');b=read(cfg['boundaries']);model=Path(cfg['model']);key='r8_LoD2_stop_'+str(stop['attempted_iteration'])
    cells=read(OLD/'counts.json')['rows']+read(D/'counts.json')['rows'];keys=list(dict.fromkeys(r['state'] for r in cells));views=read(OLD/'render_views.json')['rows']
    new=read(D/'renders/summary.json');views+=[dict(r,state=key) for r in new['views']]
    dump(D/'comparison_counts.json',dict(rows=cells,scientific_verdict=None));dump(D/'comparison_views.json',dict(rows=views,scientific_verdict=None))
    ymax=max(sum(r['count'] for r in cells if r['state']==k and r['xy_bin']==x and r['height_bin']==h) for k in keys for x in range(4) for h in range(4))*1.08
    loadmax=max(r['overlaps'] for r in views)*1.06;ticks=[f'가로{x+1}\n높이{h+1}' for x in range(4) for h in range(4)]
    caption='가로: 상자 안 / 밖 50 m 안 / 50~200 m / 200 m 넘음\n높이: 지면 아래 / 지면~지붕+10 m / 지붕+10 m~카메라 / 카메라 위'
    for k in keys:
        rows=[r for r in cells if r['state']==k];fig,ax=plt.subplots(figsize=(12,5));bottom=np.zeros(16)
        for tag in sorted({r['tag'] for r in rows}):
            rr=[r for r in rows if r['tag']==tag];vals=np.array([next(r['count'] for r in rr if r['xy_bin']==x and r['height_bin']==h) for x in range(4) for h in range(4)])
            ax.bar(np.arange(16),vals,bottom=bottom,color=COLORS[tag],label=rr[0]['provenance']);bottom+=vals
        ax.set(xticks=np.arange(16),xticklabels=ticks,ylim=(0,ymax),ylabel='가우시안 수',title=k);ax.legend();ax.grid(axis='y',alpha=.2)
        fig.text(.06,-.025,caption,fontsize=9);save(fig,'counts_'+k,dict(rows=rows,y_limits=[0,ymax],boundaries=b['height_local_m']))
        rr=[r for r in views if r['state']==k];fig,ax=plt.subplots(figsize=(12,4.2));ax.plot([r['view_index'] for r in rr],[r['overlaps'] for r in rr],lw=1)
        top=sorted(rr,key=lambda r:(-r['overlaps'],r['camera']))[:5]
        for i,r in enumerate(top):ax.scatter(r['view_index'],r['overlaps'],color='#b63b4c',s=12);ax.annotate(str(i+1),(r['view_index'],r['overlaps']),xytext=(3,4),textcoords='offset points')
        ax.set(xlim=(0,202),ylim=(0,loadmax),xlabel='학습 영상 번호 (이름순, 0~202)',ylabel='가우시안–타일 겹침 수',title=k+' · 203장');ax.grid(alpha=.2);save(fig,'load_'+k,dict(rows=rr,top5=top,y_limits=[0,loadmax]))
    forward=lines(model/'recording/forward_100.jsonl');after=lines(model/'recording/after_iteration_100.jsonl');fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True)
    it=[r['iteration'] for r in after];cc=np.array([r['counts'] for r in after]).sum(axis=(2,3));axes[0].stackplot(it,cc.T,labels=NAMES,colors=COLORS);axes[0].axhline(3*cfg['count_at_6000'],ls='--',color='black',label='6,000회 수 × 3');axes[0].legend(loc='upper left',fontsize=8);axes[0].set_ylabel('가우시안 수')
    fi=[r['iteration'] for r in forward];axes[1].plot(fi,[r['overlaps'] for r in forward]);axes[1].set_ylabel('그 반복 영상 겹침 수')
    axes[2].plot(fi,[r['binning_bytes']/2**30 for r in forward],label='정렬 버퍼');axes[2].plot(fi,[r['free_bytes_before_binning']/2**31 for r in forward],label='할당 직전 여유 메모리의 절반')
    if stop['status']=='STOPPED_BUFFER_GUARD':
        s=stop['guard_stats'];axes[2].scatter([stop['attempted_iteration']],[s[2]/2**30],color='red',marker='x',label='멈춘 영상')
    axes[2].set(xlabel='학습 반복',ylabel='GiB');axes[2].legend();[ax.grid(alpha=.2) for ax in axes];fig.tight_layout();save(fig,'continuation_records',dict(forward=forward,after=after,stop=stop,count_limit=3*cfg['count_at_6000']))
    pairs=['base_LoD2_7000','r8_LoD2_7000',key];zs=[np.load(OLD/'states'/k/'arrays.npz')['xyz'][:,2].astype(float)-b['ground_local_m'] for k in pairs[:2]]+[np.load(D/'arrays.npz')['xyz'][:,2].astype(float)-b['ground_local_m']]
    edges=np.linspace(min(z.min() for z in zs),max(z.max() for z in zs),121);zoom=np.arange(-100,202,1);fig,axes=plt.subplots(2,3,figsize=(17,8),sharey='row');data=[]
    for i,(k,z) in enumerate(zip(pairs,zs)):
        vv=[np.histogram(z,e)[0] for e in [edges,zoom]]
        for j,(e,v) in enumerate(zip([edges,zoom],vv)):
            ax=axes[j,i];ax.stairs(v,e,fill=True,alpha=.7,color=COLORS[i]);ax.set(title=k+(' · 전체' if j==0 else ' · 확대'),xlabel='지면 기준 높이 (m)',yscale='log');ax.grid(alpha=.2)
            for t in b['height_local_m']:ax.axvline(t-b['ground_local_m'],color='#a33140',ls='--',lw=.7)
        data.append(dict(state=k,full_edges=edges.tolist(),full_counts=vv[0].tolist(),zoom_edges=zoom.tolist(),zoom_counts=vv[1].tolist(),below_zoom=int((z<zoom[0]).sum()),above_zoom=int((z>zoom[-1]).sum())))
    for j in range(2):
        upper=max(ax.get_ylim()[1] for ax in axes[j]);[ax.set_ylim(.8,upper) for ax in axes[j]];axes[j,0].set_ylabel('가우시안 수 (로그)')
    fig.tight_layout();save(fig,'height_comparison',dict(states=data,boundaries=b['height_local_m']))
    grad=read(D/'gradient.json')['rows'];iterations=sorted({r['iteration'] for r in grad});fig,axes=plt.subplots(2,2,figsize=(13,8),sharex=True,sharey=True)
    for tag,ax in enumerate(axes.flat):
        for xy in range(4):
            y=[]
            for i in iterations:
                rr=[r for r in grad if r['iteration']==i and r['tag']==tag and r['xy_bin']==xy];n=sum(r['count'] for r in rr);y.append(sum(r['above'] for r in rr)/n if n else np.nan)
            ax.plot(iterations,y,'o-',label=b['xy_labels'][xy])
        ax.set(title=NAMES[tag],xlabel='반복',ylabel='기울기 문턱 이상 비율');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8);fig.tight_layout();save(fig,'gradient_eligibility',dict(rows=grad,threshold=cfg['densify_grad_threshold']))
    print('RECORDED_FIGURES_COMPLETE',len(keys),flush=True)
if __name__=='__main__':main()
