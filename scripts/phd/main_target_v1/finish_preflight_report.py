"""Source-backed diagnostic comparison and compact execution timings."""
import numpy as np
from common import *
from report_stage0 import plt,save,read

def main():
    rows=[]
    for folder,prior in [('decompose','ALS'),('diagnose','LoD2')]:
        d=read(OUT/folder/f'B173nb_b10_{prior}'/'diagnosis.json');r=d['rows'][0];part=r['decomposition']['prior_only'];full=r['strata']['prior']
        rows.append(dict(prior=prior,full_error_median_m=full['error']['quantiles'][2],
            prior_only_error_median_m=part['prior_error']['quantiles'][2],full_pixels=full['error']['count'],
            prior_only_pixels=part['prior_error']['count'],prior_only_depth_coverage=part['prior_error']['count']/full['error']['count'],
            largest_disk=d['largest_initial_disk'],control_error_median_m=r['analytic_plane_control']['quantiles'][2]))
    fig,ax=plt.subplots(1,2,figsize=(10,4));x=np.arange(2)
    ax[0].bar(x-.17,[r['full_error_median_m'] for r in rows],width=.34,color='#478ac3',label='전체 초기 장면')
    ax[0].bar(x+.17,[r['prior_only_error_median_m'] for r in rows],width=.34,color='#e6ab42',label='진단: 배경 제외')
    ax[0].axhline(.05,color='black',ls='--');ax[0].set(xticks=x,xticklabels=['항공 LiDAR','LoD2'],title='사전 패치 화소의 깊이 오차',ylabel='절대 오차 중앙값 (m)');ax[0].legend(fontsize=8)
    ax[1].bar(x,[100*r['prior_only_depth_coverage'] for r in rows],color='#e6ab42');ax[1].set(xticks=x,xticklabels=['항공 LiDAR','LoD2'],ylim=(0,105),title='배경 제외 뒤 유효 깊이가 남은 화소',ylabel='전체 초기 장면의 사전 화소 대비 (%)')
    for i,r in enumerate(rows):ax[1].text(i,100*r['prior_only_depth_coverage']+1,f'{100*r["prior_only_depth_coverage"]:.1f}%',ha='center')
    fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
    save(fig,'stage1_background_diagnosis','배경을 제외하면 오차는 줄지만 깊이가 사라지는 화소도 있다',rows,
        '고정 B173 영상 한 장 · 진단용 분해 렌더 · 학습 초기화/5 cm 통과로 사용하지 않음')
    dump(DOC/'tables/stage1_background_diagnosis.json',rows)
    receipts=[]
    for folder in ['preflight_commands','diagnose_commands','decompose_commands']:
        for p in sorted((OUT/folder).glob('*/receipt.json')):
            r=read(p);receipts.append(dict(path=str(p.relative_to(OUT)),**r))
    config=read(CFG/'target_v1.json');start=dt.datetime.fromisoformat(config['amendments'][0]['at']);end=dt.datetime.fromisoformat(stamp())
    timing=dict(started_at=start.isoformat(),as_of=end.isoformat(),elapsed_minutes=(end-start).total_seconds()/60,
        gpu_invocation_receipts=receipts,training_iterations=0,scientific_verdict=None)
    dump(DOC/'tables/stage1_timing.json',timing)
    report=DOC/'영역별목표학습_보고_v1.md';text=report.read_text()
    text=text.replace('### 초기 오차의 확인된 원인과 범위\n','### 초기 오차의 확인된 원인과 범위\n\n![배경 진단](figures/stage1_background_diagnosis.png)\n')
    text=text.replace('원 r18은 변경하지 않았다.','원 r18은 변경하지 않았다. 변경 위치는 [파일·줄 기록](tables/r19_changes.json)과 [train.py 차이](tables/r19_train.patch)에 있다.')
    elapsed=timing['elapsed_minutes'];duration=sum(r['seconds'] for r in receipts if r['exit_code']==0)
    text=text.replace('각 실행 시간은 실행 영수증에 있다.',f'개정 설정 잠금부터 이 보고까지 약 {elapsed:.1f}분이 지났다. GPU를 사용한 초기 렌더·진단 호출 시간의 합은 {duration/60:.1f}분이며 병렬 실행을 포함하므로 전체 경과 시간과 다르다. [실행 시간 기록](tables/stage1_timing.json)에 호출별 영수증이 있다.')
    text=text.replace('사용자 초기화/기준 변경 결정','사용자 초기화·기준 변경 결정')
    assert len(text)<20000;report.write_text(text.rstrip()+'\n')
    dump(DOC/'tables/stage1_visual_review.json',dict(at=stamp(),status='AGENT_REVIEWED',user_acceptance=False,
        reviewed=['stage1_rep1_ALS_target.png','stage1_rep1_ALS_initial.png','stage1_rep1_LoD2_section.png'],
        observation='labels, shared color ranges and missing-result labels visible; target map and initial rendered depth differences retained',scientific_verdict=None))
    print('REPORT_FINISHED',len(text),elapsed,flush=True)

if __name__=='__main__':main()
