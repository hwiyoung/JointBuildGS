"""Small, source-pinned interim readout; reads saved statistics, never models.

Run with run_cpu.sh interim-snapshot interim_snapshot.py --commit <host HEAD>.
The time envelope is a stated planning assumption, not a measured throughput.
"""
import argparse
import hashlib
import json
import platform
import re
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}', args.commit)
    sources = []

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        sources.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest()))
        return json.loads(raw)

    cfg = read('/config/interim_snapshot_v1.json')
    out, docs = Path('/out'), Path('/docs')
    state = read(out/'checks/resource_resume_v1/state.json')
    handoff = read(out/'checks/tiled_post_v1/handoff_state.json')
    validation = read(out/'checks/tiled_post_v1/validation.json')
    observations = read(docs/'tables/monitor_v2_observations.json')['observations']
    site, prior, iteration = cfg['site'], cfg['prior'], cfg['iteration']
    results = ['nojudge_ALS_s0'] + [v+'_ALS_s0' for v in cfg['variants']]
    labels = dict(zip(results, ['판정만 끔', '판 1 고정·참값', '판 2 다이내믹·참값',
                               '판 3 다이내믹·약한 참값', '판 4 다이내믹·평균값']))
    saved = [read(out/'opacity_saved'/site/r/f'{iteration}.json') for r in results]
    rows = []
    reference = None
    for result in results[2:]:
        passed = read(out/'runs'/site/result/'PASS.json')
        obs = [o for o in observations if o['site'] == site and o['result'] == result
               and o['iteration'] == iteration and o['attempt'] == f"attempt_{passed['attempt']}"]
        assert len(obs) == 1 and obs[0]['stop'] is None
        ref = obs[0]['nojudge_train_psnr_legacy5']
        assert reference is None or reference == ref
        reference = ref
        rows.append(dict(result=result, psnr=obs[0]['train_psnr_legacy5'], reference=ref))
    fixed_pass = read(out/'runs'/site/results[1]/'PASS.json')
    log = out/'runs'/site/results[1]/f"attempt_{fixed_pass['attempt']}"/'run.log'
    raw = log.read_bytes()
    sources.append(dict(path=str(log), sha256=hashlib.sha256(raw).hexdigest()))
    matches = re.findall(r'\[ITER 30000\] Evaluating train: L1 \S+ PSNR (\S+)', raw.decode(errors='replace'))
    assert len(matches) == 1
    rows.insert(0, dict(result=results[1], psnr=float(matches[0]), reference=reference,
                        provenance='existing training evaluation, same five-camera selection'))
    psnr = {r['result']: r['psnr'] for r in rows}
    psnr[results[0]] = reference
    fates = []
    for result in results:
        p = docs/'tables/fate_cell_split'/site/f'{prior}__{result}.json'
        if p.exists():
            d = read(p)
            assert d['partition_counts_equal_combined']
            for cell in ['cell_0', 'cell_2']:
                g = d['regions'][cell]
                assert sum(g['counts'].values()) == g['seeds_planted']
                fates.append(dict(result=result, cell=cell, **g))
    timings = []
    health_stops = []
    for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']:
        for p in ['ALS', 'LoD2']:
            for v in cfg['variants']:
                unit = out/'runs'/s/f'{v}_{p}_s0'
                if (unit/'PASS.json').exists():
                    d = read(unit/'PASS.json')
                    rec = read(unit/f"attempt_{d['attempt']}"/'receipt.json')
                    timings.append(dict(site=s, result=unit.name, minutes=rec['seconds']/60))
                if (unit/'training_health_STOP.json').exists():
                    health_stops.append(read(unit/'training_health_STOP.json'))
    times = [r['minutes'] for r in timings]
    assert len(times) == state['training_complete']
    hist = []
    for s in ['B0_b10', 'B173nb_b10', 'R1rep_b10']:
        for p in ['ALS', 'LoD2']:
            base = Path('/ph/main_stage3_v1/PHD-MAIN-STAGE3-v1/runs')/s/f'nojudge_{p}_s0'
            post = read(base/'post/post.json')['seconds']
            run = read(base/'gpu/run.json')['seconds']
            # Both dictionaries contain cumulative timings, not disjoint steps.
            hist.append(dict(site=s, prior=p, post_minutes=max(post.values())/60,
                             run_minutes=max(run.values())/60))
    payload = dict(task_id=cfg['task_id'], at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
                   config=cfg, state=state, handoff=handoff,
                   tiled_validation=validation, saved_models=saved, psnr=rows,
                   fates=fates, training_timings=timings, historical_post_timings=hist,
                   health_stops=health_stops, sources=sources,
                   commit=args.commit,
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   python=platform.python_version(), optimizer_steps=0, scientific_verdict=None)
    lines = ['# 손실 학습 시험 — 현재 확인 가능한 중간 결과', '',
             f"기준 시각: {payload['at']}. 상태는 **부분 결과**다. scientific_verdict: null.", '',
             f"24회 중 학습 완료 {state['training_complete']}회, 품질 기준 중단 {state['training_health_stopped']}회, "
             f"실행 중 {sum(j['kind']=='training' for j in state['gpu_jobs'].values())}회, 대기 {state['pending_trainings']}회다. "
             f"새 학습의 후처리 완료 {state['post_complete']}회, 채점 완료 {state['measurement_complete']}회다.", '',
             '현재 전역 STOP 표시는 기존 실행기에서 검증된 조각 후처리 실행기로 바꾸기 위한 운영 대기다. '
             '실행 중 학습의 종료를 기다린다. 품질 기준으로 중단된 두 판은 별도 기록이며 완료로 세지 않는다.', '',
             '## B173 주변·항공 LiDAR: 네 판의 30,000회 저장 모델', '',
             '불투명도는 저장 모델에서 센 중앙값이다. 참값 맞음·틀림은 사전 계보 전체를 처음 배정한 참값 칸으로 구분한다. '
             'PSNR은 기존과 같은 다섯 학습 영상이며 전체 학습 영상 평균과 섞지 않았다. '
             '불투명도나 가우시안 수가 곧 형상 정확도라는 뜻은 아니다.', '',
             '| 판 | 전체 가우시안 수 | 전체 불투명도 | 사전 계보 불투명도 | 사전 맞음 불투명도 | 사전 틀림 불투명도 | PSNR dB | nojudge 대비 dB |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for d in saved:
        g = d['groups']; r = d['result']
        medians = ' | '.join(f"{g[k]['opacity_median']:.4f}" for k in ['all', 'prior_lineage', 'prior_gt_correct', 'prior_gt_incorrect'])
        lines.append(f"| {labels[r]} | {g['all']['count']:,} | {medians} | {psnr[r]:.3f} | {psnr[r]-reference:+.3f} |")
    lines += ['', '네 판 모두 30,000회 모델이 있다. 세 다이내믹 판의 같은 다섯 영상 PSNR은 기준보다 0.21~0.59 dB 낮으며, '
              '고정 판은 2.26 dB 낮다. 이 표만으로 3차원 면이 더 정확해졌는지는 판단할 수 없다.', '',
              '## 8.5 심긴 점의 운명: 현재 계산된 칸 0·칸 2', '',
              '| 판 | 칸 | 심긴 수 | 지워짐 % | 옛 자리 % | 지금 면 % | 둘 다 아님 % |',
              '|---|---|---:|---:|---:|---:|---:|']
    for d in fates:
        vals = ' | '.join(f"{100*d['shares'][k]:.2f}" for k in ['removed', 'old_place', 'current_surface', 'neither'])
        lines.append(f"| {labels[d['result']]} | {d['cell']} | {d['seeds_planted']:,} | {vals} |")
    lines += ['', '판 3·4의 이 표는 계산 대기다. 심긴 점의 운명은 자손을 포함한 기존 분류를 그대로 사용한다. '
              '점이 지워진 비율은 면 없음 넓이와 다른 값이다.', '',
              '## 형상과 채점: 남은 항목', '',
              '8.1 학습 후 칸별 정확도·보존·면 없음 넓이, 8.2 도착한 쪽, B173 날개 단면은 후처리 대기다. '
              '없는 값을 0이나 학습 없는 시험의 값으로 채우지 않았다. '
              '[기존 중간 보고](중간보고_v1.md)에 8.1 학습 없는 시험과 8.4 문턱 21행이 있으며, '
              '문턱은 모은 폭·단위 폭·300/N·최댓값을 각각 표시한다. '
              '단위 폭은 prop_ALS_s0·prop_ALS_s1의 같은 1단계 패치 채점으로 계산했다.', '',
              '## 조각 후처리의 동일성', '',
              '실제 두 16 m 영역에서 한꺼번에 처리한 결과와 삼각형 좌표·순서·색상 및 기존 채점 배열이 정확히 같았다. '
              '한 영역은 정점 번호가 달라 파일 바이트는 다르지만 기하와 채점값은 같았다. '
              '전체 장면을 두 방식으로 끝까지 비교한 결과는 아직 없다. '
              '[검증과 제한](메모리개선_v1.md)을 함께 읽는다.', '',
              '## 종료 시간: 잠정 계획', '',
              f"정상 완료 {len(times)}회의 학습 시간은 {min(times):.1f}~{max(times):.1f}분, 중앙값 {statistics.median(times):.1f}분이다. "
              '남은 학습은 GPU 두 개를 사용할 때 오늘 10월 27일 15~18시를 잠정 범위로 둔다. '
              '후처리의 GPU 점유와 시작 메모리 대기가 길면 늦어진다.', '',
              '이전 nojudge의 같은 후처리 단계 기록은 장면당 약 5~7.5분, 추가 run 단계는 약 0.4~2.8분이었다. '
              '새 모델의 조각 처리·CPU 채점·메모리 대기까지 합친 실측은 아직 없다. '
              '계획에는 한 판 20~40분을 가정한다. 중단된 두 판을 제외한 최대 22회의 직렬 후처리·채점은 '
              '7시간 20분~14시간 40분이며 학습과 일부 겹친다. 따라서 전체 정리는 오늘 밤~내일 오전을 잠정 범위로 둔다. '
              '이는 종료 보장이 아니며 첫 전체 장면의 실측 뒤 갱신해야 한다. 추가 오류나 장기 메모리 대기는 포함하지 않았다.', '',
              '## 바꾼 것', '',
              '기존 저장 통계에서 읽기 쉬운 중간 표와 출처 해시를 따로 뽑았다. 학습·손실·채점·판·중단 기준은 바꾸지 않았다. '
              '학습 설정과 모델을 다시 실행하지 않았다. 보고서 생성 첫 시도의 컨테이너 Git 경로 조회 오류는 '
              '호스트에서 확인한 커밋을 명시적으로 전달하도록 고쳐 검증했다. 학습·후처리 프로세스에는 영향이 없었다. 원자료와 시점은 '
              '[스냅샷 JSON](tables/interim_snapshot_v1.json)에 보존한다.', '']
    (docs/'tables/interim_snapshot_v1.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (docs/'중간현황_20261027_v1.md').write_text('\n'.join(lines))
    print(json.dumps(dict(status='PASS', models=len(saved), psnr=len(rows), fate_rows=len(fates),
                          training_complete=len(times), scientific_verdict=None)))


if __name__ == '__main__':
    main()
