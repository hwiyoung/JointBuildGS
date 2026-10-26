"""Record the two actual stop events and the unchanged inherited reset mechanism."""
import json
import shutil
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from inputs import OUT,save,sha

def main():
    stamp=datetime.now(timezone(timedelta(hours=9))).isoformat();runs=[]
    for variant in ['lt_fixgt','lt_dyngt']:
        root=OUT/'runs/B173nb_b10'/(variant+'_ALS_s0')/'attempt_0'
        path=root/'model/monitor/losstrain_health.jsonl'
        records=[json.loads(x) for x in path.read_text().splitlines()]
        stops=[x for x in records if x['stop']];assert len(stops)==1
        event=stops[0];assert event['iteration']==3001 and event['stop']=='prior opacity median < 0.05'
        before=next(x for x in records if x['iteration']==3000)
        rec=json.loads((root/'receipt.json').read_text())
        assert rec['exit_code']!=0
        runs.append(dict(variant=variant,before_reset=before,stop=event,receipt=rec,source=str(path),source_sha256=sha(path),
            log=str(root/'run.log'),log_sha256=sha(root/'run.log'),completed_30000=False))
    proposal=json.loads((OUT/'checks/opacity_reset_proposal.json').read_text())
    result=dict(status='STOPPED_AWAITING_USER_RULE',at=stamp,runs=runs,calibration_completed=4,full_completed=0,full_stopped=2,
        full_not_started=22,optional_not_started=6,selected_lambda=.0025,
        cause='unchanged r16 periodic reset at 3000 clamps non-exempt opacity to min(current,0.01); all-prior median then crosses the explicit 0.05 stop condition at 3001',
        reset_source='src/phd/forks/GeoGS-conf-guided-v1-r16/train.py:1148; scene/gaussian_model.py:243',
        source_comparison='r16 and r17 GaussianModel reset bytes identical; final r17 rebuild verified',
        proposal=proposal,approved=False,scientific_verdict=None)
    save(OUT/'checks/opacity_reset_stop.json',result);save('/docs/tables/opacity_reset_stop.json',result)
    lines=['# 불투명도 정기 초기화에 따른 중단 기록','',f'기록 {stamp} · scientific_verdict: null','',
        '짧은 학습 4/4 완료. 본 학습 0/24 완료, 2회 중단, 22회 미실행. 선택 학습 0/6. 선택 λ = 0.0025.',
        '발주문 1절 10번에 따라 재학습은 보류하고 사용자에게 중단 기준의 정기 초기화 처리 방법을 문의했다. 아래 제안은 적용하지 않았다.','',
        '| 판 | 3,000회 직전 중앙값 | 3,001회 중앙값 | 전체 / 사전 출신 가우시안 | 3,001회 손실 |','|---|---:|---:|---:|---:|']
    for r in runs:
        e=r['stop'];lines.append(f"| {r['variant']} | {r['before_reset']['prior_opacity_median']:.9f} | {e['prior_opacity_median']:.9f} | {e['gaussians']:,} / {e['prior_gaussians']:,} | {e['loss_total']:.9f} |")
    lines+=['','두 실행의 중단 영상은 `DJI_20241217084447_0067_D`다. 손실은 유한했고 GPU 메모리 부족으로 중단한 것이 아니다.',
        'r16부터 유지된 기본 설정은 불투명도 초기화 간격 3,000회, 밀도 제어 종료 15,000회다. 초기화는 보호된 가우시안을 제외하고 불투명도를 현재 값과 0.01 중 작은 값으로 둔다. r17도 이 함수를 같은 바이트로 사용한다. 새 관측기는 초기화 다음 반복의 전체 사전 출신 중앙값 0.01에 발주문의 중단식을 적용했다.',
        '3,000회 짧은 학습은 다음 반복이 없어 이 중단을 만나지 않았다. 이번 기록만으로 학습 중 자연 발생한 불투명도 붕괴라고 해석하지 않는다.',
        '', '## 제안과 근거', '',
        '기존 nojudge 여섯 단위의 3,000·6,000·9,000·12,000회 초기화 24건을 읽었다. 모두 첫 100회 뒤 기록에서 중앙값이 0.05 이상이었다. 기록 간격이 100회이므로 실제 회복 시점은 그보다 정확히 알 수 없다. 새 손실의 회복을 보장하는 근거는 아니다.',
        '제안: 기존 초기화·보호·밀도 제어는 유지한다. 실제 초기화 뒤 1~99회는 불투명도 중단 판정만 유예하고 100회부터 0.05 기준을 다시 적용한다. NaN과 다른 오류는 계속 즉시 중단한다. 승인 후 실패 기록을 보존한 채 두 판을 씨앗 0부터 다시 실행한다.',
        '', '## 확인된 준비와 한계', '',
        '직접 값 부여·LoD2 점검과 여섯 단위 기본 동작/실제 손실 화소 검사는 통과했다. 짧은 학습에서 전체 가우시안 기울기 중앙값은 두 항 모두 0이었다. 비율은 확인 불가였으며, 학습 전에 고정한 엄격 부등식과 PSNR 감소 0.730011 dB에 따라 기본 λ를 유지했다. 보이는 가우시안 통계로 기준을 사후 교체하지 않았다.',
        '30,000회 새 메시·채점·그림·중간 보고는 아직 없다. 기존 결과의 새 1단계 패치 채점과 학습 없는 시험은 계속 정리한다. 5 cm·18 cm 연결 중단 기록도 그대로 보존한다.']
    text='\n'.join(lines)+'\n';Path('/docs/중단보고_초기화_v1.md').write_text(text)
    previous=Path('/docs/손실학습시험_보고_v1.md');hist=Path('/docs/history/pre_opacity_stop_보고_v1.md')
    if not hist.exists():shutil.copyfile(previous,hist)
    previous.write_text(text+'\n---\n\n'+Path('/docs/준비보고_v1.md').read_text())
    Path('/docs/progress.md').write_text(f'# PHD-MAIN-LOSSTRAIN-v1\n\n{stamp}: STOPPED_AWAITING_USER_RULE.\n\nPreparation committed/pushed c7c61a629d185a93de19052f550bc00033ffb790. Calibration 4/4, lambda 0.0025. Full 0/24 complete; fixed-gt and dynamic-gt stopped at 3001 after inherited opacity reset. No new training scheduled. Baseline patch scoring continues. scientific_verdict: null.\n')
    with Path('/docs/issues.md').open('a') as f:f.write('\nLT-009 OPEN: fixed-gt and dynamic-gt stopped at 3001 because inherited opacity reset clamps free opacities to 0.01. A 100-step reset-specific opacity-check grace was proposed from 24 historical nojudge cycles, not applied. Awaiting user decision under work-order 1.10.\n')
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False})
    fig,axs=plt.subplots(1,2,figsize=(10,4.2))
    for i,r in enumerate(runs):
        x=np.array([0.,1.])+i*.05
        axs[0].plot(x,[r['before_reset']['prior_opacity_median'],r['stop']['prior_opacity_median']],'-o',label=r['variant'])
        axs[0].text(.05,.9-i*.11,r['variant'],transform=axs[0].transAxes,color=['#1f77b4','#ff7f0e'][i])
    axs[0].set(xticks=[0,1],xticklabels=['3,000회 초기화 전','3,001회 중단'],ylabel='사전 출신 불투명도 중앙값',title='이번 두 판')
    ys=[x['first_recorded_recovery_median'] for x in proposal['baseline_evidence']]
    axs[1].scatter(np.arange(1,25),ys,c='#666666',s=20)
    axs[1].set(xlabel='기존 초기화 기록 24건',title='기존 nojudge: 초기화 100회 뒤',ylabel='사전 출신 불투명도 중앙값')
    for ax in axs:
        ax.axhline(.05,color='#c62828',linestyle='--');ax.set_ylim(0,.7)
    fig.suptitle('정기 초기화 직후의 값이 중단 기준에 걸렸다',fontsize=14)
    fig.text(.04,.01,'중단 기준 0.05 · 기존 기록 최소 '+f'{min(ys):.4f}'+' · 기존 회복 기록은 새 손실의 회복을 보장하지 않음',fontsize=9)
    fig.tight_layout(rect=[0,.05,1,.92]);dest=Path('/docs/figures');dest.mkdir(exist_ok=True)
    fig.savefig(dest/'opacity_reset_stop.png',dpi=300);plt.close(fig)
    save(dest/'opacity_reset_stop.json',dict(source='/docs/tables/opacity_reset_stop.json',source_sha256=sha('/docs/tables/opacity_reset_stop.json'),
        visual_review='PENDING',scientific_verdict=None))
    print('two stop events recorded; proposal remains unapplied',flush=True)

if __name__=='__main__':main()
