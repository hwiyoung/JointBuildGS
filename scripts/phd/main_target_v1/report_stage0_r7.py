"""Requested stage-0 before/after evidence, with aggregate-only holdout figures."""
import numpy as np
from matplotlib.patches import Patch
from common import *
from report_stage0 import plt,save
from disappearance_r7 import loadz
COL={-1:'#9b9b9b',0:'#a78bc2',1:'#54ad80',2:'#e6ab42',3:'#478ac3',5:'#db5b5b'}
WORDS={-1:'셀 수 없음',0:'관측 없음',1:'일치',2:'보존',3:'보정',5:'사라짐'}
def main():
    rep=next(r for r in json.loads((CFG/'representatives_v1.json').read_text())['rows'] if r['id']==1)
    for prior in ['ALS','LoD2']:
        stem=f'B173nb_b10_{prior}';old=loadz(OUT/'r2/targets'/f'{stem}.npz');new=loadz(OUT/'r7/targets'/f'{stem}.npz');e=loadz(OUT/'r2/stage0/evaluation'/f'{stem}.npz')
        if prior=='LoD2':
            sel=old['in_eval'];order=np.flatnonzero(sel);order=order[np.argsort(old['centre'][order,2])];fig,axes=plt.subplots(1,2,figsize=(11,5))
            for ax,d,label in [(axes[0],old,'r6 판단'),(axes[1],new,'r7 판단')]:
                ax.scatter(d['centre'][order,0],d['centre'][order,1],c=[COL[int(k)] for k in d['region'][order]],s=.6)
                # Identical visibility priority before/after for overlapping wall/roof XY.
                ids=order[old['region'][order]==0];ax.scatter(d['centre'][ids,0],d['centre'][ids,1],c=[COL[int(k)] for k in d['region'][ids]],s=.6)
                ax.set_aspect('equal');ax.set(title=label,xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)')
            fig.legend(handles=[Patch(color=COL[k],label=WORDS[k]) for k in COL],ncol=6,loc='lower center',bbox_to_anchor=(.5,.08),fontsize=8);fig.subplots_adjust(top=.83,bottom=.23,wspace=.22)
            save(fig,'r7_B173nb_LoD2_regions','B173 주변 LoD2: 관측 없음에서 사라짐을 나눴다',dict(centre=old['centre'][sel].tolist(),before=old['region'][sel].tolist(),after=new['region'][sel].tolist(),area_m2=old['area'][sel].tolist(),target_sha256=sha(OUT/'r7/targets'/f'{stem}.npz')),'평가 범위만 · 둘레 띠 제외 · 겹친 곳은 이전 관측 없음 패치를 두 그림 모두 앞에 표시')
        start,end=np.asarray(rep['start']),np.asarray(rep['end']);direction=(end-start)/np.linalg.norm(end-start);q=old['centre'][:,:2]-start;dist=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);sel=(dist>=0)&(dist<=np.linalg.norm(end-start))&(off<=rep['half_width'])
        gt=old['centre'][:,2]+e['gt_med']*old['normal'][:,2];mvs=old['centre'][:,2]+old['d']*old['normal'][:,2]
        values=np.r_[old['centre'][sel,2],gt[sel],mvs[sel]];values=values[np.isfinite(values)];limits=[float(values.min()-1),float(values.max()+1)]
        fig,axes=plt.subplots(1,3,figsize=(14,4.5));axes[0].scatter(dist[sel],old['centre'][sel,2],s=7,c='#e6ab42',label='사전 정보');axes[0].scatter(dist[sel],mvs[sel],s=5,c='#478ac3',label='MVS');axes[0].scatter(dist[sel],gt[sel],s=6,c='black',label='참값');axes[0].set_title('고정 입력')
        for ax,d,title in [(axes[1],old,'r6 영역'),(axes[2],new,'r7 영역')]:
            ax.scatter(dist[sel],gt[sel],s=4,c='black',alpha=.4)
            for region in COL:
                mask=sel&(d['region']==region);ax.scatter(dist[mask],d['centre'][mask,2],s=8,c=COL[region],label=WORDS[region])
            ax.set_title(title)
        for ax in axes:ax.set(xlabel='고정 단면 거리 (m)',xlim=(0,np.linalg.norm(end-start)),ylim=limits);ax.legend(fontsize=6,loc='upper right')
        axes[0].set_ylabel('지역 높이 (m)');fig.subplots_adjust(top=.81,bottom=.19,wspace=.2)
        save(fig,f'r7_stage0_wing_{prior}',f'B173 날개 · {prior}: 없어진 면 판단 전후를 같은 단면에서 비교했다',dict(representative=rep,patch_index=np.flatnonzero(sel).tolist(),distance=dist[sel].tolist(),prior_z=old['centre'][sel,2].tolist(),mvs_z=[float(x) if np.isfinite(x) else None for x in mvs[sel]],gt_z=[float(x) if np.isfinite(x) else None for x in gt[sel]],before=old['region'][sel].tolist(),after=new['region'][sel].tolist(),height_limits_m=limits),'지붕과 벽 포함 · 폭 1.2 m 고정 · 사라짐에는 목표와 씨앗을 두지 않음')
    rows=json.loads((DOC/'tables/disappearance_accuracy_r7.json').read_text())['rows']
    policies=['keep_all','delete_all','reference_tested_patch_u','r7'];labels=['모두 지킴','모두 지움','패치 u 참고','r7 화소 u']
    for split,word in [('development','개발용'),('holdout','확인용'),('experiment','실험 지역')]:
        for replacement,repword in [('all','전체'),('original','원값'),('replaced','대체')]:
            fig,axes=plt.subplots(1,3,figsize=(12,4),sharey=True);values=[]
            for ax,(prior,kind,title) in zip(axes,[('ALS',1,'항공 LiDAR 지붕'),('LoD2',1,'LoD2 지붕'),('LoD2',2,'LoD2 벽')]):
                selected=[]
                for policy in policies:
                    rr=[r for r in rows if r['split']==split and r['range']=='eval' and r['replacement']==replacement and r['prior']==prior and r['kind']==kind and r['policy']==policy]
                    summed={k:sum(r[k] for r in rr) for k in ['unobserved_area_m2','correctly_preserved_area_m2','wrongly_preserved_area_m2','correctly_deleted_area_m2','wrongly_deleted_area_m2','deleted_truth_unavailable_area_m2','preserved_truth_unavailable_area_m2']}
                    summed.update(prior=prior,kind=kind,policy=policy);selected.append(summed);values.append(summed)
                bottom=np.zeros(4)
                for field,col,label in [('correctly_preserved_area_m2','#54ad80','맞게 지킴'),('wrongly_preserved_area_m2','#e6ab42','잘못 지킴'),('correctly_deleted_area_m2','#478ac3','맞게 지움'),('wrongly_deleted_area_m2','#db5b5b','잘못 지움')]:
                    y=np.array([100*r[field]/r['unobserved_area_m2'] if r['unobserved_area_m2'] else 0 for r in selected]);ax.bar(np.arange(4),y,bottom=bottom,color=col,label=label);bottom+=y
                y=np.array([100*(r['deleted_truth_unavailable_area_m2']+r['preserved_truth_unavailable_area_m2'])/r['unobserved_area_m2'] if r['unobserved_area_m2'] else 0 for r in selected]);ax.bar(np.arange(4),y,bottom=bottom,color='#cccccc',label='참값 확인 불가')
                ax.set(title=title,xticks=np.arange(4),xticklabels=labels,ylim=(0,100));ax.tick_params(axis='x',rotation=20)
            axes[0].set_ylabel('고치기 전 관측 없음 넓이 대비 (%)');handles,labs=axes[-1].get_legend_handles_labels();fig.legend(handles,labs,ncol=5,loc='lower center',bbox_to_anchor=(.5,.06),fontsize=7);fig.subplots_adjust(top=.81,bottom=.28,wspace=.15)
            save(fig,f'r7_disappear_accuracy_{split}_{replacement}',f'{word} · {repword}: 사라짐 판단과 두 비교 규칙의 넓이를 셌다',values,'참값 없는 부분은 회색 · 패치 u 방식은 참고만 · 분모가 없으면 막대를 그리지 않음')
    print('R7_STAGE0_FIGURES_COMPLETE',flush=True)
if __name__=='__main__':main()
