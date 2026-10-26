"""Record the approved +100 opacity stop and unchanged baseline trajectory."""
import json
import shutil
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from inputs import OUT,PH,save,sha
from runtime_report import records

def main():
    stop=json.loads((OUT/'runs/B173nb_b10/lt_dyngt_ALS_s0/STOP_attempt_1.json').read_text());r=stop['run'];result=r['variant']+'_'+r['prior']+'_s0'
    root=OUT/'runs'/r['site']/result/f"attempt_{stop['attempt']}";health=records(root/'model/monitor/losstrain_health.jsonl')
    event=next(x for x in health if x['stop']);assert event['iterations_after_reset']==100 and event['prior_opacity_median']<.05
    comparison=records(root/'model/monitor/losstrain_reset_comparison.jsonl')[-1]
    old=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/r['site']/('nojudge_'+r['prior']+'_s0')/'model/monitor/scalars.jsonl'
    own=records(root/'model/monitor/scalars.jsonl');baseline=records(old)
    selected=[6000,6100,7000,8000,8500,8900,9000,9100];keys=['iteration','n','n_prior','n_image','n_locked','added','removed','opacity_q_prior','opacity_q_locked','opacity_share_ge05_prior','total','rgb','mvs','prior']
    trajectory={name:[{k:x.get(k) for k in keys} for x in rows if x['iteration'] in selected] for name,rows in [('dynamic_gt',own),('nojudge',baseline)]}
    out=dict(status='STOPPED_UNDER_APPROVED_100_STEP_RULE',stop=stop,event=event,comparison=comparison,trajectory=trajectory,
        source=str(root),health_sha256=sha(root/'model/monitor/losstrain_health.jsonl'),scalars_sha256=sha(root/'model/monitor/scalars.jsonl'),
        baseline_source=str(old),baseline_sha256=sha(old),receipt=json.loads((root/'receipt.json').read_text()),
        cause_confirmed='prior-origin opacity median remains below 0.05 at actual reset+100; threshold enforced exactly',
        cause_unresolved='why this arm fails to recover; increasing prior-origin descendant count and opacity saturation are observations, not a proven cause',
        no_new_training=True,scientific_verdict=None)
    save(OUT/'checks/opacity_grace_v1/stop_diagnostic.json',out);save('/docs/tables/opacity_grace_stop.json',out)
    lines=['# 100회 유예 뒤에도 불투명도 기준에 걸린 중단','',
        '완료 학습: 짧은 학습 4/4. 새 본 학습의 완료 수는 progress.md와 tables/runtime.json에 갱신한다. 다이내믹·참값 1회 중단.',
        '고른 λ: 0.0025, 변경 없음.',
        '확인 불가: 다이내믹·참값의 30,000회 결과와 학습 효과. 불투명도 회복 실패의 원인은 아직 확정하지 않았다.','',
        '사용자가 승인한 규칙을 그대로 적용했다. 실제 9,000회 정기 초기화 뒤 1~99회에는 불투명도 판정을 유예했고, 100회째인 9,100회에 기준을 다시 적용했다.','',
        f"- 사전 출신 불투명도 중앙값: **{event['prior_opacity_median']:.9f} < 0.05**.",
        f"- 같은 반복의 nojudge 중앙값: **{comparison['nojudge_prior_opacity_median']:.9f}**.",
        f"- 전체 가우시안 {event['gaussians']:,}개, 사전 출신 {event['prior_gaussians']:,}개.",
        f"- 중단 영상: `{event['camera']}`. 사용자 기준에 따른 중단이며, NaN·GPU 메모리 부족 예외가 아니다.",
        '- 관측 시점: 최적화와 불투명도 보호 뒤, 밀도 제어와 초기화 전. nojudge와 같다.',
        '- 3,100회·6,100회는 통과했다. 9,100회 중단 뒤 이 판을 다시 돌리지 않았으며, 새 학습은 보류했다. 이미 돌던 고정·참값은 계속 관측한다.','',
        '## 중단 전 기록','',
        '| 학습 | 반복 | 사전 출신 N | 보호 N | 불투명도 중앙값 |',
        '|---|---:|---:|---:|---:|']
    for label,rows in trajectory.items():
        for x in rows:
            lines.append(f"| {label} | {x['iteration']} | {x['n_prior']:,} | {x['n_locked']:,} | {x['opacity_q_prior'][1]:.9f} |")
    lines+=['','9,000회 표는 그 반복의 밀도 제어·초기화 전이다. 9,100회 중단 기록은 이후 밀도 제어 전이며, 중단이 일반 스칼라 기록보다 앞에서 일어나 위 표의 dynamic_gt에는 9,100회 행이 없다. 맨 위의 중단 관측 기록에 그 값과 N을 따로 보존했다.',
        '다이내믹·참값에서는 사전 출신 수와 불투명도 중앙값이 초기화 전에 빠르게 증가했다. nojudge의 같은 반복 기록도 함께 보였지만, 이것만으로 후손 증가가 회복 실패를 일으켰다고 판단하지 않는다. 초기화·보호·밀도 제어·손실 세기를 추가로 바꾸지 않았다.',
        '', '## 완료한 독립 작업','',
        '기존 비교 결과 30개의 1단계 패치 채점, 학습 없는 시험 30개, 기존 nojudge 여섯 단위의 심긴 점 집계, AXES71 기존 표 재사용과 수치 차이 기준을 정리했다. 8.1의 표는 tables/patch_scores_all.*, 두 축 평가는 tables/axes_metrics.*, 심긴 점은 tables/fates_all.*에 있다.',
        '5 cm·18 cm 연결 기록, 17시 직접 값 부여 규칙과 두 점검 통과, 짧은 학습 4회, 최초 3,001회 중단 두 건, 100회 유예 승인과 재실행 기록을 모두 보존했다.',
        '발주문 1절 10번과 사용자의 100회 뒤 중단 지시에 따라 새 학습의 다음 범위를 문의한다. 재학습이나 기준 완화는 적용하지 않았다.',
        '', 'scientific_verdict: null']
    text='\n'.join(lines)+'\n';Path('/docs/중단보고_100회뒤_v1.md').write_text(text)
    p=Path('/docs/손실학습시험_보고_v1.md');h=Path('/docs/history/pre_grace_stop_보고_v1.md')
    if not h.exists():shutil.copyfile(p,h)
    p.write_text(text+'\n---\n\n'+Path('/docs/준비보고_v1.md').read_text())
    issues=Path('/docs/issues.md');s=issues.read_text()
    if 'LT-012 ' not in s:issues.write_text(s+'\nLT-012 OPEN: dynamic-gt B173 ALS attempt_1 stopped at 9100, actual periodic reset+100, prior opacity median 0.00798154715448618 < 0.05. Same-iteration nojudge median 0.23826287686824799. No NaN/OOM exception; cause of recovery failure unconfirmed. New trainings blocked; in-flight fixed-gt continues.\n')
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False})
    fig,axs=plt.subplots(1,2,figsize=(10,4.5))
    for name,rows,col in [('dynamic_gt',own,'#d1495b'),('nojudge',baseline,'#777777')]:
        xs=[x['iteration'] for x in rows if 6000<=x['iteration']<=9100];ys=[x['n_prior'] for x in rows if 6000<=x['iteration']<=9100]
        axs[0].plot(xs,ys,color=col);axs[0].text(xs[-1],ys[-1],'다이내믹 · 참값' if name=='dynamic_gt' else '판정 끔',fontsize=8,color=col,ha='right',va='bottom')
    axs[0].set(xlabel='반복',ylabel='사전 출신 가우시안 수',ylim=(0,1100000),title='초기화 전 사전 출신 수 증가')
    events=records(root/'model/monitor/losstrain_reset_comparison.jsonl')
    for key,col,name in [('prior_opacity_median','#d1495b','다이내믹 · 참값'),('nojudge_prior_opacity_median','#777777','판정 끔')]:
        xs=[x['iteration'] for x in events];ys=[x[key] for x in events];axs[1].plot(xs,ys,'o-',color=col)
        axs[1].text(xs[0]+100,ys[0]+.015,name,color=col,ha='left',fontsize=9)
    axs[1].axhline(.05,color='black',linestyle='--');axs[1].set(xlabel='초기화 100회 뒤 반복',ylabel='불투명도 중앙값',ylim=(0,.28),title='9,100회에 0.05 아래')
    fig.suptitle('승인된 100회 유예 뒤에도 다이내믹·참값은 기준에 미달했다',fontsize=13)
    fig.text(.04,.01,f"9,100회: {event['prior_opacity_median']:.6f} / 판정 끔 {comparison['nojudge_prior_opacity_median']:.6f} · 인과관계는 확인 불가",fontsize=9)
    fig.tight_layout(rect=[0,.05,1,.92]);dest=Path('/docs/figures/opacity_grace_stop.png');fig.savefig(dest,dpi=300);plt.close(fig)
    save(dest.with_suffix('.json'),dict(source='/docs/tables/opacity_grace_stop.json',source_sha256=sha('/docs/tables/opacity_grace_stop.json'),visual_review='PENDING',scientific_verdict=None))
    print('approved reset+100 stop recorded',event['iteration'],event['prior_opacity_median'],flush=True)

if __name__=='__main__':main()
