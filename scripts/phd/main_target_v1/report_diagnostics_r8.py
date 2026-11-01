"""Checkpoint origin, release, large-background and health/count figures."""
import sys
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save
from report_movement_r7 import read,loadz
def main():
    prior,it=sys.argv[1],int(sys.argv[2]);prefix=f'r8_{prior}_{it}';run=OUT/'r8/runs'/f'tg_B173nb_b10_{prior}_s0_r8';root=OUT/'r8';ratio=read(run/f'origin_ratio_{it}.json');fail=read(root/'failures'/f'{prior}_{it}/summary.json');move=read(root/'movement'/f'{prior}_{it}/summary.json');big=read(run/f'model/check{it}/large_background_descendants.json');data=loadz(run/f'model/check{it}/large_background_descendants.npz');cam=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1)['camera']['name']
    fig,axes=plt.subplots(2,2,figsize=(12,9));xx=np.arange(3)
    for dx,k,lab,col in [(-.18,'draw_share','렌더 αT 합의 몫','#61a8a7'),(.18,'outside_max_share','폭 밖 최대 기여 몫','#e09c36')]:axes[0,0].bar(xx+dx,[r[k]*100 if r[k] is not None else np.nan for r in ratio['rows']],width=.36,label=lab,color=col)
    axes[0,0].set(xticks=xx,xticklabels=['배경','풀림','패치'],ylim=(0,100),ylabel='%');axes[0,0].legend(fontsize=8)
    matrix=np.array(fail['cross_fraction_of_outside'])*100;im=axes[0,1].imshow(matrix,vmin=0,vmax=100,cmap='Blues');axes[0,1].set(xticks=range(5),xticklabels=['같은 패치','다른 패치','배경','풀림','확인 불가'],yticks=[0,1],yticklabels=['앞','뒤']);axes[0,1].tick_params(axis='x',labelsize=7)
    for i in range(2):
        for j in range(5):axes[0,1].text(j,i,f'{matrix[i,j]:.2f}',ha='center',va='center',fontsize=8)
    fig.colorbar(im,ax=axes[0,1],fraction=.04);h=np.array(fail['sigma_hist_counts']).sum(0);axes[1,0].plot(range(len(h)),100*h/max(h.sum(),1),'o-',color='#438bb6');axes[1,0].set(xticks=range(len(h)),xticklabels=fail['sigma_hist_bins'][:-1],xlabel='|렌더 깊이−목표| / σ 구간 아래끝',ylabel='폭 밖 화소, %',ylim=(0,100));pix=loadz(root/'failures'/f'{prior}_{it}/pixels/{cam}.npz');axes[1,1].imshow(np.where(pix['front_back']>=0,pix['lineage']+1,0),cmap=ListedColormap(['#eeeeee','#55a577','#a94e83','#438bb6','#e09c36','#444444']),vmin=0,vmax=5);axes[1,1].axis('off');axes[1,1].set_title('고정 영상의 폭 밖 화소');fig.subplots_adjust(top=.88,bottom=.14,hspace=.4,wspace=.3);save(fig,prefix+'_failure',f'{prior} {it:,}회: 기여·폭 밖 화소·벗어난 크기',dict(ratio=ratio,failure=fail,camera=cam),'초록 같은 패치 · 자주 다른 패치 · 파랑 배경 · 주황 풀림 · 검정 확인 불가 · 회색 대상 밖')
    rel=move['reattach'];events=read(run/f'model/target_monitor/reattach_{it}.json')['events'];iterations=sorted(set(r['iteration'] for r in events));fig,axes=plt.subplots(1,2,figsize=(11,4));axes[0].bar(iterations,[sum(r['released'] for r in events if r['iteration']==i) for i in iterations],width=75,color='#e09c36');axes[0].set(xlabel='풀린 반복',ylabel='전환 사건 수');hist=rel['surviving_release_iteration_counts'];axes[1].bar([int(k) for k in hist],list(hist.values()),width=75,color='#e09c36');axes[1].set(xlabel='물려받은 풀림 반복',ylabel='남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,prefix+'_release',f'{prior}: 풀림 사건과 생존 계보',rel,'전환 사건과 살아남은 자손은 분모가 다름')
    size=data['scale'].max(1);fig,axes=plt.subplots(1,2,figsize=(11,4))
    if len(size):axes[0].hist(size,bins=np.geomspace(max(size.min(),1e-8),max(size.max(),size.min()*1.01),55),color='#61a8a7');axes[0].set_xscale('log')
    axes[0].set(xlabel='긴 축(m)',ylabel='남은 자손 수');axes[1].hist(data['opacity'],bins=np.linspace(0,1,51),color='#61a8a7');axes[1].set(xlabel='불투명도',ylabel='남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,prefix+'_large_background',f'{prior}: 처음 1 m 초과 배경의 자손',big,'크기 상한 없음 · 기록 항목')
    figure,axes=plt.subplots(1,3,figsize=(15,4));sources=[]
    for rev,model,style in [('r7',OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model','--'),('r8',run/'model','-')]:
        rows=[json.loads(s) for s in (model/'target_monitor/curve.jsonl').read_text().splitlines() if json.loads(s)['iteration']<=(7000 if rev=='r7' else it)];sources.append(dict(revision=rev,rows=rows));x=[r['iteration'] for r in rows];axes[0].plot(x,[r['gaussians'] for r in rows],style,label=rev)
        for tag,col in [('0','#61a8a7'),('1','#a94e83'),('2','#e09c36')]:axes[1].plot(x,[r['tags'][tag] for r in rows],style,c=col,label=rev+' '+{'0':'배경','1':'패치','2':'풀림'}[tag])
    base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0/model/jbgs_trace.jsonl'
    baseline_rows=[json.loads(s) for s in base.read_text().splitlines() if json.loads(s)['iteration']<=7000]
    axes[0].plot([r['iteration'] for r in baseline_rows],[r['gaussians'] for r in baseline_rows],':',label='기존 방법 7,000회',c='#50a27a');sources.append(dict(revision='baseline7k',rows=baseline_rows))
    memories=[json.loads(s) for s in (run/'model/target_monitor/memory_1000.jsonl').read_text().splitlines() if json.loads(s)['iteration']<=it]
    for key,label in [('allocated_bytes','현재 할당'),('peak_allocated_bytes','누적 최대 할당'),('peak_reserved_bytes','누적 최대 예약')]:axes[2].plot([r['iteration'] for r in memories],[r[key]/2**30 for r in memories],'-o',label=label,ms=3)
    axes[0].set(ylabel='전체 가우시안 수');axes[1].set(ylabel='꼬리표별 수');axes[2].set(ylabel='GPU GiB')
    for ax in axes:ax.set_xlabel('반복');ax.legend(fontsize=6);ax.grid(alpha=.2)
    figure.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(figure,prefix+'_counts_memory',f'{prior}: 가우시안 수와 GPU 메모리',dict(curves=sources,memory=memories),'r8은 1,000회마다 수·메모리 기록 · 최대 메모리는 프로세스 시작부터 누적')
    rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');a,b=np.asarray(rep['start']),np.asarray(rep['end']);vec=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a);limits=read(DOC/'figures'/f'r6_{prior}_section_comparison.json')['values']['height_limits_m']
    def crop(x):
        q=x[:,:2]-a;d=q@vec;off=abs(q[:,0]*vec[1]-q[:,1]*vec[0]);return d,(d>=0)&(d<=length)&(off<=rep['half_width'])
    fig,axes=plt.subplots(1,3,figsize=(16,5));d,m=crop(t['centre']);axes[0].scatter(d[m],t['centre'][m,2],s=4,c='#e6ab42',label='사전 지붕·벽')
    for filename,color,label in [('gt_xyz.npy','black','참값 점'),('mvs_a_xyz.npy','#478ac3','MVS 점')]:
        points=np.load(UN/'points/B173nb_b10'/filename,mmap_mode='r');dd,mask=crop(points);ix=np.flatnonzero(mask);ix=ix[::max(1,len(ix)//4000)];axes[0].scatter(dd[ix],points[ix,2],s=.5,c=color,alpha=.3,label=label)
    sections=[]
    for ax,rev,step,sr in [(axes[1],'r7',7000,OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7'),(axes[2],'r8',it,run)]:
        s=loadz(sr/f'model/target_monitor/snapshot_{step}.npz');dd,mm=crop(s['xyz'])
        for tag,label,color in [(0,'배경','#61a8a7'),(1,'패치','#a94e83'),(2,'풀림','#e09c36')]:
            select=mm&(s['target_tag']==tag);ax.scatter(dd[select],s['xyz'][select,2],s=2,c=color,label=label)
        sections.append(dict(revision=rev,iteration=step,in_section=int(mm.sum()),outside_fixed_height=int((mm&((s['xyz'][:,2]<limits[0])|(s['xyz'][:,2]>limits[1]))).sum())));ax.set_title(f'{rev} {step:,}회 중심')
    axes[0].set_title('고정 입력')
    for ax in axes:ax.set(xlim=(0,length),ylim=limits,xlabel='고정 단면 거리(m)');ax.legend(fontsize=6)
    fig.subplots_adjust(top=.8,bottom=.2,wspace=.2);save(fig,prefix+'_section_centres',f'B173 날개 · {prior}: 지붕·벽 입력과 출신별 중심',dict(section=rep,height_limits_m=limits,counts=sections),'r6·r7과 같은 폭·높이 범위 · 벽은 입력 점과 중심으로 표시 · 높이 범위 밖 수는 JSON에 기록')
    dump(run/f'diagnostics_report{it}.json',dict(status='PASS_DIAGNOSTIC_FIGURES',iteration=it,prior=prior,scientific_verdict=None));print('R8_DIAGNOSTIC_FIGURES',prior,it,flush=True)
if __name__=='__main__':main()
