"""One trained checkpoint, frozen camera/section/ranges, baseline7k and r7 comparators."""
import sys
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save
from report_movement_r7 import read,loadz,pc,REGION_NAMES
from report_r7 import LABELS
METRICS=['floating_fraction_cells_0_3','agreement_within_tau_fraction','no_surface_fraction_cells_0_3']
WORDS=['칸 0~3 뜬 면','일치 영역 τ 안','칸 0~3 면 없음']
def main():
    prior,it=sys.argv[1],int(sys.argv[2]);site='B173nb_b10';prefix=f'r8_{prior}_{it}';run=OUT/'r8/runs'/f'tg_{site}_{prior}_s0_r8';old=OUT/'r7/runs'/f'tg_{site}_{prior}_s0_r7';base=OUT/'r7/baselines'/f'base7k_{site}_{prior}_s0'
    roots=[base,old,run];its=[7000,7000,it];names=['기존 방법 7,000회','r7 7,000회',f'r8 {it:,}회'];posts=[r/f'post{n}' for r,n in zip(roots,its)];scores=[read(p/'score.json') for p in posts];vers=[read(r/f'verification{n}.json') for r,n in zip(roots,its)];zs=[loadz(p/'patch_z.npz') for p in posts]
    ratio=read(run/f'origin_ratio_{it}.json');move=read(OUT/'r8/movement'/f'{prior}_{it}/summary.json');fail=read(OUT/'r8/failures'/f'{prior}_{it}/summary.json');big=read(run/f'model/check{it}/large_background_descendants.json')
    thresholds=[scores[0][METRICS[0]]+.02,scores[0][METRICS[1]]-.02,scores[0][METRICS[2]]+.01];checks=[scores[2][METRICS[0]]<=thresholds[0],scores[2][METRICS[1]]>=thresholds[1],scores[2][METRICS[2]]<=thresholds[2]]
    healthfile=run/f'model/target_monitor/health_{it}.json';health=read(healthfile) if healthfile.exists() else dict(status='NOT_AVAILABLE',scientific_verdict=None)
    record=dict(at=stamp(),prior=prior,iteration=it,score=scores[2],baseline=scores[0],r7=scores[1],thresholds=dict(zip(METRICS,thresholds)),geometry_checks=dict(zip(METRICS,checks)),geometry_status='PASS' if all(checks) else 'FAIL',health=health,coverage=vers[2],origin_ratio=ratio,movement=move,large_background=big,scientific_verdict=None)
    L=[f'# {prior} r8 {it:,}회 점검 [이 발주에서 냄]','',f"기하 기준: {record['geometry_status']}. 건강: {health['status']}. 기하 기준은 기록이며 22:20 결정대로 학습 중단에 쓰지 않는다.",'','[구현·초기 입력 점검](구현과_초기점검_r8.md)','', '| 항목 | 기존 방법 7,000회 | r7 7,000회 | r8 | 문턱 | 통과 |','|---|---:|---:|---:|---:|---|']
    for k,w,th,ok,sign in zip(METRICS,WORDS,thresholds,checks,['≤','≥','≤']):L.append(f'| {w} | '+ ' | '.join(pc(s[k]) for s in scores)+f' | {sign}{pc(th)} | {ok} |')
    L +=['','| 화소 구분 | 목표 화소 수 | 기존 방법 폭 안 | r7 폭 안 | r8 폭 안 | r8 깊이 없음 |','|---|---:|---:|---:|---:|---:|']
    for k,v in vers[2]['strata'].items():
        assert all(v['target_pixels']==q['strata'][k]['target_pixels'] for q in vers)
        L.append(f'| {LABELS[k]} | {v["target_pixels"]:,} | '+' | '.join(pc(q['strata'][k]['fraction']) for q in vers)+' | '+pc(v['missing_fraction'])+' |')
    fig,axes=plt.subplots(1,2,figsize=(12,4));keys=['all','prior','background','prior_roof','prior_wall']
    for dx,s,v,name,col in zip([-.25,0,.25],scores,vers,names,['#50a27a','#999999','#438bb6']):
        axes[0].bar(np.arange(3)+dx,[s[k]*100 for k in METRICS],width=.25,label=name,color=col);axes[1].bar(np.arange(5)+dx,[np.nan if v['strata'][k]['fraction'] is None else v['strata'][k]['fraction']*100 for k in keys],width=.25,label=name,color=col)
    axes[0].set(xticks=range(3),xticklabels=['뜬 면','일치 τ 안','면 없음'],ylabel='넓이 (%)',ylim=(0,100));axes[1].set(xticks=range(5),xticklabels=['전체','사전','배경 MVS 목표','지붕','벽'],ylabel='목표 폭 안 화소 (%)',ylim=(0,100))
    for ax in axes:ax.legend(fontsize=7)
    fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,prefix+'_gate_coverage',f'{prior}: 기하와 목표 따름',record,'세 판 모두 같은 r7 영역·목표 · 기하 기준 미달은 기록')
    for replacement in ['all','original','replaced']:
        rr=[r for r in scores[2]['result_vs_target'] if r['replacement']==replacement];fig,axes=plt.subplots(1,2,figsize=(12,4));xx=np.arange(len(rr))
        for dx,label,source,col in [(-.27,'기존 방법',scores[0],'#50a27a'),(-.09,'r7',scores[1],'#999999'),(.09,'r8',scores[2],'#438bb6'),(.27,'목표 자체',None,'#222222')]:
            values=[r['target_within_tau_fraction'] if source is None else next(q['result_within_tau_fraction'] for q in source['result_vs_target'] if q['region']==r['region'] and q['replacement']==replacement) for r in rr];axes[0].bar(xx+dx,[np.nan if v is None else 100*v for v in values],width=.18,label=label,color=col)
        for dx,s,name,col in zip([-.25,0,.25],scores,names,['#50a27a','#999999','#438bb6']):
            vv=[next(q['floating_fraction'] for q in s['result_vs_target'] if q['region']==r['region'] and q['replacement']==replacement) for r in rr];axes[1].bar(xx+dx,[np.nan if v is None else v*100 for v in vv],width=.25,label=name,color=col)
        for ax,lab in zip(axes,['τ 안 넓이 (%)','뜬 면 넓이 (%)']):ax.set(xticks=xx,xticklabels=[REGION_NAMES[r['region']] for r in rr],ylim=(0,100),ylabel=lab);ax.legend(fontsize=6)
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,prefix+'_regions_'+replacement,f'{prior}: {replacement} 영역별 기록',dict(scores=scores,replacement=replacement),'목표 없는 사라짐, 분모 없는 줄은 빈칸')
    rep=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1);camera=rep['camera']['name'];t=loadz(OUT/'r7/targets'/f'{site}_{prior}.npz');e=loadz(PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{site}__{prior}/evaluation.npz');eligible=e['in_eval']&e['scoring_allowed'];a,b=np.array(rep['start']),np.array(rep['end']);direction=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a);q=t['centre'][:,:2]-a;dd=q@direction;off=abs(q[:,0]*direction[1]-q[:,1]*direction[0]);sel=(dd>=0)&(dd<=length)&(off<=rep['half_width']);roof=sel&(t['kind']==1)&e['scoring_allowed'];limits=read(DOC/'figures'/f'r6_{prior}_section_comparison.json')['values']['height_limits_m'];gt=t['centre'][:,2]+e['p_gt']*t['normal'][:,2]
    fig,axes=plt.subplots(1,3,figsize=(16,4.7))
    for ax,z,name in zip(axes,zs,names):
        h=t['centre'][:,2]+z['z']*t['normal'][:,2];ok=roof&np.isfinite(h);ax.scatter(dd[roof],gt[roof],s=5,c='black',label='참값');ax.scatter(dd[sel],t['centre'][sel,2],s=3,c='#e6ab42',label='사전');ax.errorbar(dd[roof],t['target'][roof,2],yerr=1.96*t['sigma'][roof]*abs(t['normal'][roof,2]),fmt='.',ms=1,c='gray',alpha=.25,label='목표 폭');ax.scatter(dd[ok],h[ok],s=5,c='#438bb6',label='결과');ax.set(title=name,ylim=limits,xlim=(0,length),xlabel='고정 단면 거리(m)');ax.legend(fontsize=6)
    fig.subplots_adjust(top=.81,bottom=.2,wspace=.22);save(fig,prefix+'_section',f'{prior}: B173 날개 고정 단면',dict(section=rep,height_limits_m=limits,source_scores=[str(p/'score.json') for p in posts]),'지금 채점 메시의 첫 교차점 · r6·r7과 같은 단면·높이 범위')
    fig,axes=plt.subplots(1,3,figsize=(16,5));counts=[]
    for ax,z,p,name in zip(axes,zs,posts,names):
        floating=eligible&(z['category']==1);label=np.full(len(floating),3,np.int8)
        attribution_path=(OUT/'r8/baseline_origin'/prior/'origin_attribution.npz') if p==posts[0] else p/'origin_attribution.npz'
        if attribution_path.exists():
            if p==posts[0]:assert read(attribution_path.parent/'verification.json')['status']=='PASS_BASELINE_ORIGIN_JOIN'
            att=loadz(attribution_path);seen=att['views']>0
            for code,ch in [(0,0),(1,2),(2,1)]:label[seen&(att['mean_fraction'][:,ch]>=.5)]=code
        ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],s=.3,c='#dddddd')
        for i,col,lab in [(0,'#61a8a7','배경 우세'),(1,'#a94e83','패치 우세'),(2,'#e09c36','풀림 우세'),(3,'#444444','혼합·확인 불가')]:
            m=floating&(label==i);ax.scatter(t['centre'][m,0],t['centre'][m,1],s=1.4,c=col,label=lab)
        ax.set_aspect('equal');ax.set(title=name,xlabel='동쪽(m)',ylabel='북쪽(m)');ax.legend(fontsize=6);counts.append(dict(name=name,floating_patches=int(floating.sum()),origin_counts={str(i):int((floating&(label==i)).sum()) for i in range(4)}))
    fig.subplots_adjust(top=.82,bottom=.17,wspace=.25);save(fig,prefix+'_floating_origin',f'{prior}: 뜬 면 출신 지도',counts,'같은 평가 범위 · 영상 평균 기여 ≥0.5가 우세 · 기존 방법은 PLY 출신 사용, 풀림 해당 없음')
    renders=[loadz(r/f'model/check{n}/renders'/f'{camera}.npz') for r,n in zip(roots,its)];photo=loadz(OUT/'r2/preflight'/f'{site}_{prior}'/f'{camera}.npz')['photo_rgb'].transpose(1,2,0);fig,axes=plt.subplots(1,4,figsize=(16,4))
    for ax,img,name in zip(axes,[photo]+[x['rgb'] for x in renders],['사진']+names):ax.imshow(img);ax.set_title(name);ax.axis('off')
    fig.subplots_adjust(top=.81,bottom=.15,wspace=.03);save(fig,prefix+'_fixed_render',f'{prior}: 고정 영상',dict(camera=camera,rows=names),'같은 카메라·해상도')
    m=loadz(OUT/'r8/stage1'/f'{site}_{prior}/maps/{camera}.npz');ix=read(OUT/'r8/stage1'/f'{site}_{prior}/maps/index.json')['views'][camera];owner=m['owner'];has=owner>=0;j=np.maximum(owner,0);K=np.array(ix['K']);inv=np.linalg.inv(np.array(ix['W2C']));vv,uu=np.indices(owner.shape)
    def height(x):
        dep=x['depth'];q=np.stack([(uu-K[0,2])/K[0,0]*dep,(vv-K[1,2])/K[1,1]*dep,dep,np.ones_like(dep)],-1);world=(q.reshape(-1,4)@inv.T)[:,:3].reshape(*owner.shape,3);h=((world-t['centre'][j])*t['normal'][j]).sum(2);h[~has|~np.isfinite(dep)|(dep<=0)]=np.nan;return h
    fig,axes=plt.subplots(1,4,figsize=(16,4))
    for ax,x,name in zip(axes,[np.where(has,t['h'][j],np.nan)]+[height(x) for x in renders],['r7 고정 목표']+names):im=ax.imshow(x,cmap='coolwarm',vmin=-5,vmax=5);ax.set_title(name);ax.axis('off');fig.colorbar(im,ax=ax,fraction=.04,extend='both')
    fig.subplots_adjust(top=.8,bottom=.17,wspace=.13);save(fig,prefix+'_fixed_height',f'{prior}: 사전 패치 법선 높이',dict(camera=camera,color_range_m=[-5,5]),'r6·r7과 같은 색 범위 · 원반 없는 화소는 빈칸')
    fig,axes=plt.subplots(1,2,figsize=(10,5));colors=['#999999','#62a4cc','#64a866','#d5884d','#eeeeee','#cb789f']
    for ax,rev in zip(axes,['r7','r8']):
        target=loadz(OUT/rev/'targets'/f'{site}_{prior}.npz');ax.scatter(t['centre'][eligible,0],t['centre'][eligible,1],c=target['region'][eligible],cmap=ListedColormap(colors),vmin=0,vmax=5,s=1);ax.set_aspect('equal');ax.set(title=rev,xlabel='동쪽(m)',ylabel='북쪽(m)')
    fig.subplots_adjust(top=.82,bottom=.17);save(fig,prefix+'_regions_map',f'{prior}: 고정 영역 표지',dict(identical=sha(OUT/'r7/targets'/f'{site}_{prior}.npz')==sha(OUT/'r8/targets'/f'{site}_{prior}.npz'),colors=dict(zip(range(6),colors))),'회색 관측 없음 · 파랑 일치 · 초록 보존 · 주황 보정 · 분홍 사라짐 · 평가 범위')
    L +=['','| 현재 출신 | 그리는 몫 | 폭 밖 최대 기여 몫 | 틀린 몫 / 그리는 몫 |','|---|---:|---:|---:|']
    for r in ratio['rows']:L.append(f"| {r['origin']} | {pc(r['draw_share'])} | {pc(r['outside_max_share'])} | "+('확인 불가' if r['wrong_share_over_draw_share'] is None else f"{r['wrong_share_over_draw_share']:.6f}")+' |')
    L +=['','| 현재 출신 | 수 | 접선 1 m 초과 | 긴 축 중앙(m) | 불투명도 중앙 | 법선 이동 중앙(m) | 접선 이동 중앙(m) |','|---|---:|---:|---:|---:|---:|---:|']
    for tag,r in move['origins'].items():L.append(f"| {tag} | {r['gaussians']:,} | {r['tangent_over_1m']:,} | "+' | '.join('해당 없음' if r[k] is None else f"{r[k]['median']:.6f}" for k in ['size_max_axis_m','opacity','normal_displacement_abs_m','tangent_displacement_m'])+' |')
    L +=['',f"처음 1 m 초과 배경에서 살아남은 부모 {big['surviving_original_ancestors']:,}개, 자손 {big['surviving_gaussians']:,}개. 크기·불투명도·이동 전체 배열은 저장 증거에 있다.",'']
    for suffix in ['failure','release','large_background','counts_memory','section_centres','gate_coverage','section','fixed_render','fixed_height','floating_origin','regions_map','regions_all','regions_original','regions_replaced']+[f'{tag}_movement_{view}' for tag in ['patch','background','released'] for view in ['top','oblique']]:L +=[f'![{suffix}](figures/{prefix}_{suffix}.png)','']
    L+=['scientific_verdict: null.'];(DOC/f'{prefix}_점검.md').write_text('\n'.join(L)+'\n');dump(DOC/'tables'/f'{prefix}_summary.json',record);dump(run/f'report{it}.json',dict(at=stamp(),status='PASS_CHECKPOINT_REPORT',record_sha256=sha(DOC/'tables'/f'{prefix}_summary.json'),scientific_verdict=None));print('R8_CHECKPOINT_REPORT',prior,it,record['geometry_status'],flush=True)
if __name__=='__main__':main()
