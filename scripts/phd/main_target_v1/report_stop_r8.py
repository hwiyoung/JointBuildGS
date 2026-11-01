"""Report the observed independent LoD2 CUDA stop without restarting training."""
import re
from common import *
from report_stage0 import plt, save


def read(path):
    return json.loads(path.read_text())


def main():
    run = OUT/'r8/runs/tg_B173nb_b10_LoD2_s0_r8'
    mon = run/'model/target_monitor'
    curve = [json.loads(x) for x in (mon/'curve.jsonl').read_text().splitlines()]
    memory = [json.loads(x) for x in (mon/'memory_1000.jsonl').read_text().splitlines()]
    reference = next(r for r in curve if r['iteration'] == 6000)
    first = next(r for r in curve if r['iteration'] >= 7000 and r['gaussians'] > 3*reference['gaussians'])
    last = curve[-1]
    log = (run/'train.log').read_text()
    error = next(x for x in log.splitlines() if x.startswith('torch.cuda.OutOfMemoryError:'))
    progress = int(re.findall(r'(\d+)/30000', log)[-1])
    checkpoints = []
    for it in [7000, 15000, 30000]:
        point = run/f'model/point_cloud/iteration_{it}/point_cloud.ply'
        states = list((run/f'model/jbgs_complete/iteration_{it}').glob('checkpoint.pth'))
        checkpoints.append(dict(iteration=it, point_cloud_exists=point.exists(), state_paths=[str(p) for p in states]))
    assert checkpoints[0]['point_cloud_exists'] and checkpoints[0]['state_paths']
    assert all(not r['point_cloud_exists'] and not r['state_paths'] for r in checkpoints[1:])
    als = read(OUT/'r8/runs/tg_B173nb_b10_ALS_s0_r8/receipt.json')
    assert als['status'] == 'TRAINING_COMPLETE_30000'
    payload = dict(at=stamp(), status='STOPPED_CUDA_OOM_AWAIT_USER', stop=read(OUT/'r8/STOP_LoD2.json'),
                   training_receipt=read(run/'receipt.json'), launch=read(run/'launch.json'),
                   last_displayed_iteration=progress, last_health=last, reference_6000=reference,
                   last_periodic=memory[-1], first_100_step_record_above_3x=first,
                   last_count_ratio=last['gaussians']/reference['gaussians'], error=error,
                   checkpoints=checkpoints, als_receipt=als, automatic_retry=False,
                   sources={str(p):sha(p) for p in [run/'train.log', mon/'curve.jsonl', mon/'memory_1000.jsonl', run/'receipt.json',run/'launch.json']},
                   scientific_verdict=None)
    dump(OUT/'r8/diagnostics/LoD2_stop/summary.json', payload)
    dump(DOC/'tables/r8_LoD2_stop.json', payload)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    xs = [r['iteration'] for r in curve]
    axes[0].plot(xs, [r['gaussians']/1e6 for r in curve], label='전체')
    axes[0].axhline(3*reference['gaussians']/1e6, color='#be4b45', ls='--', label='6,000회 × 3')
    axes[0].set_ylabel('가우시안 수 (백만)')
    for tag, label, color in [('0','배경','#61a8a7'),('1','패치','#a94e83'),('2','풀림','#e09c36')]:
        axes[1].plot(xs, [r['tags'][tag]/1e6 for r in curve], label=label, color=color)
    axes[1].set_ylabel('꼬리표별 수 (백만)')
    for key, label in [('allocated_bytes','현재 할당'),('peak_allocated_bytes','누적 최대 할당'),('peak_reserved_bytes','누적 최대 예약')]:
        axes[2].plot([r['iteration'] for r in memory], [r[key]/2**30 for r in memory], '-o', ms=3, label=label)
    axes[2].set_ylabel('GPU GiB')
    for ax in axes:
        ax.set_xlabel('반복'); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.subplots_adjust(top=.8, bottom=.2, wspace=.3)
    save(fig, 'r8_LoD2_stop', 'r8 LoD2: CUDA 메모리 부족 중단 기록', payload,
         '수 곡선 100회 기록 · 3배 검사는 1,000회마다 · 메모리 마지막 기록 14,000회 · 추가 학습 없음')
    rows=[]
    for r in [reference, next(x for x in curve if x['iteration']==memory[-1]['iteration']), first, last]:
        rows.append(f"| {r['iteration']:,} | {r['gaussians']:,} | {r['gaussians']/reference['gaussians']:.6f} | {r['tags']['0']:,} | {r['tags']['1']:,} | {r['tags']['2']:,} |")
    report = '\n'.join([
        '# r8 LoD2 실행 중단 기록', '',
        f"- 중단 시각: {payload['training_receipt']['at']}. 진행 표시 {progress:,}회 직후 forward 렌더링에서 CUDA 메모리 부족. 종료 코드 1.",
        '- 물리 GPU 1을 독립 사용했다(오류문의 GPU 0은 컨테이너 내부 번호). r8 항공 LiDAR는 30,000회 정상 종료했으며 영향을 받지 않았다.',
        '- 7,000회 채점 PLY와 최적화 전체 상태는 보존했다. 15,000·30,000회 PLY와 전체 상태는 없다. 자동 재시도하지 않는다.',
        '', '| 반복 | 전체 | 6,000회 대비 | 배경 | 패치 | 풀림 |', '|---:|---:|---:|---:|---:|---:|', *rows, '',
        f"3배 한계는 {3*reference['gaussians']:,}개다. 마지막 정기 검사 {memory[-1]['iteration']:,}회는 한계 이내였다. 100회 기록에서 처음 넘은 때는 {first['iteration']:,}회지만, 잠긴 3배 검사 간격은 1,000회다. 다음 15,000회 검사·저장 전에 CUDA 오류가 발생했다. 간격과 멈춤 문턱을 바꾸지 않았다.", '',
        f"마지막 건강 기록의 불투명도 중앙값은 {last['prior_opacity_median']:.9f}, 법선 방향 최대 폭 초과는 {last['max_normal_excess_m']:.9g} m다.", '',
        '```text', error, '```', '',
        '![가우시안 수와 메모리](figures/r8_LoD2_stop.png)', '',
        'r8 결정 4의 건강 검사 중단·질문 조건에 따라 LoD2 추가 학습은 후속 결정을 기다린다. 저장된 모델의 읽기 전용 채점은 계속한다. 나머지 여섯 판은 시작하지 않는다. scientific_verdict: null.', '',
        '수치·원본 파일 해시·저장 상태 목록: [JSON](tables/r8_LoD2_stop.json).', ''
    ])
    (DOC/'실행중단_r8_LoD2.md').write_text(report)
    print('R8_LOD2_STOP_REPORTED', progress, last['gaussians'], flush=True)


if __name__ == '__main__':
    main()
