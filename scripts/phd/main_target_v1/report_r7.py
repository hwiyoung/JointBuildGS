"""Measurement report for the locked r7 checkpoint; no scientific verdict."""
import numpy as np
from matplotlib.colors import ListedColormap
from common import *
from report_stage0 import plt,save
from report_movement_r7 import read,loadz,pc,REGION_NAMES,NAMES,COLORS
LABELS={'all':'전체','prior':'사전 패치','background':'배경 MVS','prior_roof':'사전 지붕','prior_wall':'사전 벽','prior_original':'사전 원값','prior_replaced':'사전 대체',**{f'region_{k}':v for k,v in REGION_NAMES.items()}}
def main():
    from report_curves_r7 import main as curves
    curves()
    text=['# r7 · 7,000회 점검','',
    '[이 발주에서 냄] r20을 보존하고 r21에서 관측 없음의 사라짐 판단, 폭과 접선 거리를 함께 쓰는 목표 재연결, 정기 불투명도 초기화 뒤 500회 감시 예외를 구현했다. 배경·풀림은 묶지 않으며 손실·학습률·밀도 제어 일정은 그대로다.','',
    '[단계 0 사라짐 판단·정확도·대체 비율](단계0_사라짐_점검_r7.md)을 별도로 기록했다. 사라짐은 목표와 씨앗을 받지 않으며, 원반이 없어진 화소는 기존 MVS 목표 규칙을 따른다.','',
    '기존 깊이 손실 기준선은 r5 비교에 쓰인 r15의 30,000회 저장 상태에 기록된 구현 해시를 현재 코드와 대조했다. 같은 원래 설정·씨앗·영상 나눔으로 새 두 판을 7,000회까지만 실행했다. 학습률 일정의 전체 반복 수는 30,000으로 유지하고, 출력 위치·7,000회 저장·7,000회 종료만 바꿨다. 처음 input.ply도 원 기준선과 바이트 단위로 같았다. 상세 차이는 `baseline7k.r7.json`에 남겼다.','',
    '배경 씨앗은 신뢰도 마스크를 통과한 MVS 점이며, 기존 깊이 손실 기준선의 초기 SfM 희소점과 다르다. 초기 크기와 불투명도 규칙은 기준선과 같고, 큰 배경의 처음 열 개·계보는 [초기 씨앗 확인](초기배경_크기_r7.md)에 적었다.','',
    '메시 기하 비율의 분모는 기존 MESHPATCH와 같은 평가 범위의 채점 가능 참값 패치 넓이다. 참값 면 측정이 없는 패치는 그 분모에서 빠진다. 면 없음은 참값 채점이 가능한 위치에서 결과 메시의 첫 면을 찾지 못한 경우다. 단계 0의 참값 확인 불가와 구분한다.','',
    '판정은 같은 사전 정보의 기존 방법 7,000회와 비교한다: 뜬 면 +2%p 이하, 일치 영역 τ 안 −2%p 이상, 칸 0~3 면 없음 +1%p 이하. 건강 검사는 별도다. 목표 폭 안 화소 비율과 추가 계보 진단은 기록이며 통과 문턱이 아니다.','']
    text += ['배경 씨앗 위치·학습 영상·기존 기준선의 초기 점은 r5와 같다(이번 초기 입력 검증에서 대조). [씨앗 범위와 영상 시야를 겹친 지도](중단후_비교진단_r5.md)는 이 입력에 그대로 해당한다. 시야 지도는 입력 지붕 중앙 높이의 평면과 카메라 절두체의 교차이며 실제 가림을 반영한 관측 영역과 구분한다.','']
    allrows=[];camera=next(r for r in read(CFG/'representatives_v1.json')['rows'] if r['id']==1)['camera']['name']
    for prior in ['ALS','LoD2']:
        run=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7';old=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0'
        score=read(run/'post7000/score.json');ref=read(base/'post7000/score.json');oldscore=read(old/'post7000/score.json');ver=read(run/'verification7000.json');bv=read(base/'verification7000.json');ov=read(old/'verification7000.json');move=read(OUT/'r7/movement'/prior/'summary.json');ratio=read(run/'origin_ratio.json');fail=read(OUT/'r7/failures'/prior/'summary.json');health=read(run/'model/target_monitor/health_7000.json')
        row=dict(prior=prior,score=score,baseline=ref,r6=oldscore,coverage=ver['strata'],baseline_coverage=bv['strata'],movement=move,origin_ratio=ratio,health=health);allrows.append(row)
        metrics=['floating_fraction_cells_0_3','agreement_within_tau_fraction','no_surface_fraction_cells_0_3'];words=['뜬 면','일치 영역 τ 안','칸 0~3 면 없음'];threshold=['floating_max','agreement_min','no_surface_max']
        text +=[f'## {prior} · {score["status"]}','', '| 항목 | 기존 방법 7,000회 | r6 7,000회 | r7 7,000회 | r7 기준 |','|---|---:|---:|---:|---:|']
        for k,w,th,sign in zip(metrics,words,threshold,['≤','≥','≤']):text.append(f'| {w} | {pc(ref[k])} | {pc(oldscore[k])} | {pc(score[k])} | {sign}{pc(score["thresholds"][th])} |')
        text +=['',f'7,000회 건강: {health["status"]}; 가우시안 {health["gaussians"]:,}개, 처음 패치 계보의 불투명도 중앙값 {health["prior_opacity_median"]:.6f}.','', '| 목표 화소 구분 | 화소 수 | 기존 방법 폭 안 | r7 폭 안 | r7 깊이 없음 |','|---|---:|---:|---:|---:|']
        for k,v in ver['strata'].items():
            assert v['target_pixels']==bv['strata'][k]['target_pixels'];text.append(f'| {LABELS[k]} | {v["target_pixels"]:,} | {pc(bv["strata"][k]["fraction"])} | {pc(v["fraction"])} | {pc(v["missing_fraction"])} |')
        text +=['','사라짐에는 사전 원반이 없으므로 사라짐 소유 화소는 0개다. 그 자리의 MVS 목표 화소는 배경 행에 포함된다. 메시 채점의 사라짐 영역은 고정 패치 위치로 별도 집계했다.','']
        fig,axes=plt.subplots(1,2,figsize=(12,4));keys=['all','prior','background','prior_roof','prior_wall']
        for dx,obj,name,color in [(-.25,ref,'기존 방법','#50a27a'),(0,oldscore,'r6','#999999'),(.25,score,'r7','#438bb6')]:axes[0].bar(np.arange(3)+dx,[100*obj[k] for k in metrics],width=.25,label=name,color=color)
        for dx,obj,name,color in [(-.18,bv,'기존 방법','#50a27a'),(.18,ver,'r7','#438bb6')]:axes[1].bar(np.arange(5)+dx,[100*obj['strata'][k]['fraction'] if obj['strata'][k]['fraction'] is not None else np.nan for k in keys],width=.36,label=name,color=color)
        axes[0].set(xticks=range(3),xticklabels=['뜬 면','일치 τ 안','면 없음'],ylim=(0,100),ylabel='넓이 (%)');axes[1].set(xticks=range(5),xticklabels=['전체','사전','배경','지붕','벽'],ylim=(0,100),ylabel='목표 폭 안 화소 (%)')
        for ax in axes:ax.legend(fontsize=7)
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.25);save(fig,f'r7_{prior}_gate_coverage',f'{prior}: 같은 학습량의 기하와 목표 따름',row,'기존 방법과 r7은 같은 r7 영역·목표 지도 · r6는 당시 영역(사라짐 없음) · 목표 따름은 기록')
        text +=[f'![점검 비교](figures/r7_{prior}_gate_coverage.png)','', '| 구분 | 영역 | 넓이(m²) | r7 결과 τ 안 | 목표 자체 τ 안 | 기존 방법 τ 안 | r7 뜬 면 |','|---|---|---:|---:|---:|---:|---:|']
        for r in score['result_vs_target']:
            b=next(x for x in ref['result_vs_target'] if x['region']==r['region'] and x['replacement']==r['replacement']);text.append(f'| {r["replacement"]} | {REGION_NAMES[r["region"]]} | {r["area_m2"]:.3f} | {pc(r["result_within_tau_fraction"])} | {pc(r["target_within_tau_fraction"])} | {pc(b["result_within_tau_fraction"])} | {pc(r["floating_fraction"])} |')
        for replacement in ['all','original','replaced']:
            rr=[r for r in score['result_vs_target'] if r['replacement']==replacement];fig,axes=plt.subplots(1,2,figsize=(11,4));x=np.arange(len(rr))
            for dx,key,label,col in [(-.25,'result_within_tau_fraction','r7 결과','#438bb6'),(0,'target_within_tau_fraction','목표 자체','#888888'),(.25,'baseline','기존 방법','#50a27a')]:
                vals=[next(q for q in ref['result_vs_target'] if q['region']==r['region'] and q['replacement']==replacement)['result_within_tau_fraction'] if key=='baseline' else r[key] for r in rr];axes[0].bar(x+dx,[100*v if v is not None else np.nan for v in vals],width=.25,label=label,color=col)
            axes[0].set(xticks=x,xticklabels=[REGION_NAMES[r['region']] for r in rr],ylim=(0,100),ylabel='τ 안 넓이 (%)');axes[0].legend(fontsize=7)
            axes[1].bar(x,[100*r['floating_fraction'] if r['floating_fraction'] is not None else np.nan for r in rr],color='#c95b4f');axes[1].set(xticks=x,xticklabels=[REGION_NAMES[r['region']] for r in rr],ylim=(0,100),ylabel='영역별 뜬 면 넓이 (%)');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
            save(fig,f'r7_{prior}_regions_{replacement}',f'{prior} · {replacement}: 영역별 목표·결과·뜨는 면',dict(r7=rr,baseline=[q for q in ref['result_vs_target'] if q['replacement']==replacement]),'목표 없는 사라짐 및 분모 없는 줄은 빈칸 · 평가 가능 넓이로 셈')
            text +=['',f'![영역별 비교](figures/r7_{prior}_regions_{replacement}.png)','']
        text +=['| 현재 출신 | 그리는 몫 | 폭 밖 최대 기여 몫 | 틀린 몫 / 그리는 몫 |','|---|---:|---:|---:|']
        for r in ratio['rows']:text.append(f'| {r["origin"]} | {pc(r["draw_share"])} | {pc(r["outside_max_share"])} | '+(f'{r["wrong_share_over_draw_share"]:.4f}' if r['wrong_share_over_draw_share'] is not None else '확인 불가')+' |')
        fig,axes=plt.subplots(1,2,figsize=(11,4));x=np.arange(3);rr=ratio['rows']
        for dx,key,label,col in [(-.18,'draw_share','렌더 기여 합의 몫','#61a8a7'),(.18,'outside_max_share','폭 밖 최대 기여 몫','#e09c36')]:axes[0].bar(x+dx,[100*r[key] if r[key] is not None else np.nan for r in rr],width=.36,label=label,color=col)
        axes[0].set(xticks=x,xticklabels=['배경','풀림','패치'],ylim=(0,100),ylabel='몫 (%)');axes[0].legend(fontsize=7);axes[1].bar(x,[r['wrong_share_over_draw_share'] if r['wrong_share_over_draw_share'] is not None else np.nan for r in rr],color='#438bb6');axes[1].axhline(1,color='gray',ls='--');axes[1].set(xticks=x,xticklabels=['배경','풀림','패치'],ylabel='틀린 몫 / 그리는 몫');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
        save(fig,f'r7_{prior}_origin_ratio',f'{prior}: 건물 목표 화소에서의 렌더 기여와 폭 밖 최대 기여',ratio,'그리는 몫: αT 합 비율 · 틀린 몫: 폭 밖 사전 화소의 최대 기여 수 비율 · 인과 판정 아님')
        text +=['',f'![출신별 몫](figures/r7_{prior}_origin_ratio.png)','','그리는 몫은 사전 목표 원반 화소에서 αT 기여를 합한 비율이다. 틀린 몫은 폭 밖 사전 화소의 최대 기여 가우시안을 센 비율이다. 두 비율의 분모가 다르며, 관계를 기록한 것으로 원인을 확정하지 않는다.','']
        matrix=np.asarray(fail['cross_fraction_of_outside']);oldfail=read(OUT/'r6/failures'/prior/'summary.json');fig,axes=plt.subplots(1,2,figsize=(12,4));im=axes[0].imshow(matrix*100,vmin=0,vmax=100,cmap='Blues');axes[0].set(xticks=range(5),xticklabels=['같은 패치','다른 패치','배경','풀림','확인 불가'],yticks=[0,1],yticklabels=['앞','뒤'])
        for i in range(2):
            for j in range(5):axes[0].text(j,i,f'{matrix[i,j]*100:.2f}',ha='center',va='center',fontsize=8)
        fig.colorbar(im,ax=axes[0],fraction=.04)
        for f,label,color in [(oldfail,'r6','#999999'),(fail,'r7','#438bb6')]:
            h=np.asarray(f['sigma_hist_counts']).sum(0);axes[1].plot(range(len(h)),100*h/max(1,h.sum()),'o-',c=color,label=label)
        axes[1].set(xticks=range(len(h)),xticklabels=fail['sigma_hist_bins'][:-1],ylim=(0,100),xlabel='|깊이 차이|/σ 구간 아래끝',ylabel='폭 밖 사전 화소 (%)');axes[1].legend();fig.subplots_adjust(top=.8,bottom=.23,wspace=.3);save(fig,f'r7_{prior}_failure_table',f'{prior}: 폭 밖 화소의 방향·최대 기여·벗어난 크기',fail,'교차표 분모는 폭 밖 사전 화소 · 방향은 가림/비침 방향이며 물리적 원인 확정 아님')
        text +=['| 깊이 방향 | 같은 현재 패치 | 다른 현재 패치 | 배경 | 풀림 | 확인 불가 |','|---|---:|---:|---:|---:|---:|']
        for d,w in enumerate(['앞','뒤']):text.append('| '+w+' | '+' | '.join(pc(v) for v in matrix[d])+' |')
        fig,axes=plt.subplots(1,2,figsize=(11,4));cmap=ListedColormap(['#eeeeee','#55a577','#a94e83','#438bb6','#e09c36','#444444'])
        for ax,revision in zip(axes,['r6','r7']):
            pix=loadz(OUT/revision/'failures'/prior/'pixels'/f'{camera}.npz');ax.imshow(np.where(pix['front_back']>=0,pix['lineage']+1,0),cmap=cmap,vmin=0,vmax=5);ax.set_title(revision);ax.axis('off')
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.03);save(fig,f'r7_{prior}_failure_map',f'{prior}: 같은 고정 영상의 폭 밖 화소',dict(camera=camera,r6=oldfail['totals'],r7=fail['totals']),'초록 같은 패치 · 자주 다른 패치 · 파랑 배경 · 주황 풀림 · 검정 확인 불가 · 회색 대상 밖')
        text +=['', '| 현재 출신 | 수 | 처음 목표 면을 따라 1 m 초과 | 긴 축 중앙(m) | 불투명도 중앙 | 법선 이동 중앙(m) | 접선 이동 중앙(m) |','|---|---:|---:|---:|---:|---:|---:|']
        for tag,r in move['origins'].items():
            vals=[f'{r[k]["median"]:.6f}' if r[k] else '해당 없음' for k in ['size_max_axis_m','opacity','normal_displacement_abs_m','tangent_displacement_m']];text.append(f'| {tag} | {r["gaussians"]:,} | {r["tangent_over_1m"]:,} | '+' | '.join(vals)+' |')
        rel=move['reattach'];text +=['',f'풀림 {rel["current_released"]:,}/{rel["current_prior_lineage"]:,} = {pc(rel["current_released_fraction"])}. 현재 목표 재연결과 별개로 이동은 처음 씨앗의 목표·법선에서 잰 값이다.','']
        fig,axes=plt.subplots(1,2,figsize=(11,4));events=read(run/'model/target_monitor/reattach_7000.json')['events'];iterations=sorted(set(r['iteration'] for r in events));axes[0].bar(iterations,[sum(r['released'] for r in events if r['iteration']==i) for i in iterations],width=75,color='#e09c36');axes[0].set(xlabel='풀린 반복',ylabel='전환 사건 수');hist=rel['surviving_release_iteration_counts'];axes[1].bar([int(k) for k in hist],list(hist.values()),width=75,color='#e09c36');axes[1].set(xlabel='물려받은 풀림 반복',ylabel='7,000회에 남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,f'r7_{prior}_release',f'{prior}: 풀림 사건과 살아남은 계보',rel,'전환 사건에는 이후 삭제된 가우시안도 포함 · 살아남은 자손과 분모 구분')
        big=read(run/'model/check7000/large_background_descendants.json');data=loadz(run/'model/check7000/large_background_descendants.npz');fig,axes=plt.subplots(1,2,figsize=(11,4));size=data['scale'].max(1)
        if len(size):axes[0].hist(size,bins=np.geomspace(max(size.min(),1e-8),max(size.max(),size.min()*1.01),55),color=COLORS[0]);axes[0].set_xscale('log')
        axes[0].set(xlabel='긴 축 (m)',ylabel='남은 자손 수');axes[1].hist(data['opacity'],bins=np.linspace(0,1,51),color=COLORS[0]);axes[1].set(xlabel='불투명도',ylabel='남은 자손 수');fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,f'r7_{prior}_large_background',f'{prior}: 처음 1 m 초과 배경의 남은 자손',big,'초기 크기 상한 없음 · 별도 멈춤 기준 아님')
        text +=[f'처음 1 m 초과 배경 {big["initial_large_background_count"]:,}개에서 {big["surviving_original_ancestors"]:,}개 부모 계보, 자손 {big["surviving_gaussians"]:,}개가 남았다. 크기·불투명도·이동 분포는 그림 JSON과 전체 NPZ에 보존했다.','']
        for suffix in ['fixed_render','fixed_render_baseline','fixed_height','fixed_height_baseline','failure_table','failure_map','section_comparison','within_tau','floating_origin','release','large_background','movement_reference']+[f'{tag}_movement_{view}' for tag in ['patch','background','released'] for view in ['top','oblique']]:text +=[f'![{suffix}](figures/r7_{prior}_{suffix}.png)','']
    text +=['![학습 곡선](figures/r7_training_curves.png)','','## 구현과 검증','', '새 판의 변경 파일·줄은 `tables/r21_changes_r7.json`과 패치에 남겼다. σ=1 m 목표에서 법선 방향 0.8 m의 씨앗 유지, 접선 방향 0.6 m의 풀림 및 자식 상속, 임의 법선 731개 질의의 전수 후보 대조를 통과했다. 작은 결정적 예제의 100회 연속/재개는 모델·Adam·난수·영상 순서·동적 목표 상태가 같았다.','', '7,000회 채점 PLY·스냅숏은 밀도 제어 직전이고, 이어 학습 상태는 해당 반복의 밀도 제어와 목표 갱신 뒤다. 실제 전체 상태의 Adam과 해시를 별도 검증했다. 15,000·30,000회는 도달한 경우만 완료로 적는다.','', '렌더 깊이 재집계, 계보 교차표, 2,048개 독립 첫 면 광선과 넓이 합계를 검증했다. 최대 기여 진단은 저장 깊이와 203개 영상 모두 바이트 단위 재현을 확인한다.','', '![r6 마지막 σ](figures/r7_r6_LoD2_released_last_sigma.png)','','`scientific_verdict: null`',stamp()]
    dump(DOC/'tables/summary_r7.json',dict(rows=allrows,scientific_verdict=None));(DOC/'단계1_7000회_점검_r7.md').write_text('\n'.join(text)+'\n');print('REPORT_R7_COMPLETE',flush=True)
if __name__=='__main__':main()
