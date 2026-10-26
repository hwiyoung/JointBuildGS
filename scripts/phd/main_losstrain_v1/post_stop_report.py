"""Factual same-arm third-stop report; no retry or research-rule changes."""
import json
from pathlib import Path
from inputs import OUT,save,sha


def main():
    unit=OUT/'runs/B173nb_b10/lt_fixgt_ALS_s0';event=OUT/'checks/fixed_post_host_oom'
    stop=json.loads((unit/'STOP_monitor_v2.json').read_text());assert stop['known_same_arm_stops']==3
    rows=[]
    for i in [0,1]:
        receipt=unit/f'post_attempt_{i}_receipt.json';r=json.loads(receipt.read_text());assert r['exit_code']==137
        detail=event/('failure_details.json' if i==0 else 'retry_failure_details.json');d=json.loads(detail.read_text())
        rows.append(dict(attempt=i,receipt=r,details=d,receipt_sha256=sha(receipt),detail_sha256=sha(detail)))
    models=[]
    for var in ['lt_fixgt','lt_dyngt']:
        root=OUT/'runs/B173nb_b10'/(var+'_ALS_s0');p=json.loads((root/'PASS.json').read_text())
        s=json.loads((OUT/'opacity_saved/B173nb_b10'/root.name/'30000.json').read_text())
        models.append(dict(result=root.name,attempt=p['attempt'],groups=s['groups'],model_sha256=s['sources']['model_sha256'],training_receipt=json.loads((root/f"attempt_{p['attempt']}/receipt.json").read_text())))
    plan=dict(status='PROPOSED_NOT_AUTHORIZED',training_restarts=0,additional_fixed_post_attempts=1,
        unchanged=['trained model','loss','scoring','variants','TSDF voxel 0.05 m','truncation 0.25 m','depth limit 300 m','no mesh cleanup','48 GiB container limit'],
        proposed_admission=dict(minimum_host_available_GiB=64,stable_seconds=60,large_cpu_and_tsdf_serial=True),
        reason_for_user_input='same fixed arm: initial 3001 stop plus two TSDF post OOM stops = three',scientific_verdict=None)
    data=dict(status='STOPPED_PARTIAL',stop=stop,post_attempts=rows,completed_models=models,next_action=plan,scientific_verdict=None)
    save('/docs/tables/post_stop.json',data);save(event/'proposed_next_action.json',plan)
    lines=['# 판 1 후처리 메모리 중단 보고','',
        '판 1과 판 2의 30,000회 학습은 완료했다. 판 1의 TSDF 후처리는 두 번 모두 호스트 전체 메모리 부족으로 종료됐다. 첫 3,001회 학습 중단까지 합쳐 같은 판 세 번째 중단이므로 사용자 지시에 따라 추가 실행을 보류한다. scientific_verdict: null.','',
        '| 후처리 시도 | 종료 시각 | 시간 초 | 종료 코드 | 마지막 로그의 완료 영상 | 종료 당시 프로세스 익명 RSS GiB |',
        '|---|---|---:|---:|---:|---:|']
    for r in rows:
        a=r['receipt'];d=r['details'];lines.append(f"| {r['attempt']} | {a['at']} | {a['seconds']:.3f} | {a['exit_code']} | {d['last_logged_completed_tsdf_views']}/203 | {d['host_killed_process_anon_rss_kB']/1024**2:.6f} |")
    lines+=['','두 사건 모두 커널의 global_oom과 해당 컨테이너·프로세스 PID가 확인된다. CUDA OOM이나 컨테이너 48 GiB 제한 초과라고 단정하지 않는다. 표의 영상 수는 마지막 완료 로그이며 정확한 실패 영상은 확인 불가다. 실패 순간의 화면 반지름과 PyTorch 메모리도 남지 않아 확인 불가로 둔다.','',
        '학습 모델, 두 후처리 로그·영수증, 미완료 후처리 폴더, 두 커널 발췌와 해시를 보존했다. 초기 중단 파일을 이전 실행기가 덮은 사건은 새 후처리 사건을 따로 저장한 뒤 승인 해시와 같은 9,100회 사본으로 복원했다.','',
        '## 완료 모델과 중단 기준','',
        '| 판 | 가우시안 수 | 전체 불투명도 중앙값(저장 모델) | 30,000회 같은 다섯 영상 PSNR dB | nojudge 대비 하락 dB |',
        '|---|---:|---:|---:|---:|',
        f"| 판 1 고정·참값 | {models[0]['groups']['all']['count']} | {models[0]['groups']['all']['opacity_median']:.9f} | 23.658566284 | 2.261134338 |",
        f"| 판 2 다이내믹·참값 | {models[1]['groups']['all']['count']} | {models[1]['groups']['all']['opacity_median']:.9f} | 25.706835938 | 0.212864685 |",'',
        'nojudge의 같은 시점·다섯 영상 PSNR은 25.919700623 dB다. 두 판 모두 3 dB 초과 하락 조건에 걸리지 않았다. 15,000·30,000회 출신·참값 칸 통계는 [관측 표](tables/monitor_v2_observations.md), 심긴 점은 [중간 보고](중간보고_v1.md)에 있다. nojudge는 재학습하지 않았다.','',
        '결과 메시가 없어 새 판의 8.1·8.2·8.3과 B173 날개 단면은 확인 불가다. 사용자 요청의 8.4 문턱은 기존 두 씨앗의 같은 패치 채점으로 독립 계산해 중간 보고에 추가했다. 21행을 패치별 배열에서 다시 확인한 차이는 0이다.','',
        '## 바꾼 것','',
        '첫 후처리 실패 뒤 가용 메모리 56 GiB를 기다렸다. 큰 CPU 채점을 TSDF와 직렬로 묶은 뒤 시작 대기선만 52 GiB로 조정했고, 53.644981384 GiB에서 같은 48 GiB 제한·같은 명령으로 한 번 재시도했다. 학습·손실·채점·TSDF 설정은 그대로였다. 그 재시도도 실패했으므로 재실행이 해결됐다고 보고하지 않는다.','',
        '## 다음 실행안 — 아직 실행하지 않음','',
        '저장 모델을 그대로 두고 재학습 없이 판 1 후처리만 한 번 더 실행하는 안이다. 기존 48 GiB 컨테이너 제한과 모든 계산 설정을 유지한다. 먼저 가용 메모리 64 GiB 이상이 60초 유지되는지 확인하고, 본 발주의 큰 CPU 작업과 TSDF를 직렬로 실행한다. 다른 서비스나 작업을 중지하지 않는다. 현재 이 안은 승인 전이며 실행하지 않았다.','',
        '문의 이유는 사용자의 최신 지시인 “같은 판이 두 번 넘게 멈출 때”에 해당하기 때문이다. 새 학습 판 3·4와 후속 묶음은 아직 시작하지 않았다. [반올림 전 기록](tables/post_stop.json).']
    Path('/docs/중단보고_후처리메모리_v1.md').write_text('\n'.join(lines)+'\n')
    print('post stop report PASS; next retry not authorized',flush=True)


if __name__=='__main__':main()
