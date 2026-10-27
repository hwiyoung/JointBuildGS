"""Read-only runtime/artifact audit; writes only a dated operational report.

No training, mesh, scoring, queue admission or scientific setting is changed.
"""
import json
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from inputs import OUT, save, sha


def read(path):
    return json.loads(path.read_text())


def main():
    state_path = OUT/'checks/resource_resume_v1/state.json'
    state = read(state_path)
    rows, timings, peaks = [], dict(post=[], run=[], axes=[]), []
    for site in ['B0_b10', 'B173nb_b10', 'R1rep_b10']:
        for prior in ['ALS', 'LoD2']:
            for variant in ['lt_fixgt', 'lt_dyngt', 'lt_dynsoft', 'lt_dynnow']:
                result = f'{variant}_{prior}_s0'
                unit = OUT/'runs'/site/result
                passed = read(unit/'PASS.json') if (unit/'PASS.json').exists() else None
                model = unit/f"attempt_{passed['attempt']}"/'model/point_cloud/iteration_30000/point_cloud.ply' if passed else None
                row = dict(site=site, prior=prior, result=result,
                    training_complete=passed is not None,
                    model_30000_exists=model.is_file() if model else False,
                    health_stopped=(unit/'training_health_STOP.json').exists(),
                    mesh_complete=(unit/'post_stage_PASS.json').exists(),
                    core_scored=(OUT/'patch_z'/f'{site}__{prior}__{result}.json').exists(),
                    full_post_complete=(unit/'post_PASS.json').exists(),
                    full_measure_complete=(unit/'measure_PASS.json').exists())
                assert not passed or row['model_30000_exists'], str(unit)
                rows.append(row)
                for mode in ['post', 'run']:
                    for path in unit.glob(mode+'_attempt_*_receipt.json'):
                        record = read(path)
                        if record.get('exit_code') != 0:
                            continue
                        # Receipts include any wait within Docker. Keep the raw duration;
                        # this is not a computation-only benchmark.
                        timings[mode].append(dict(site=site, prior=prior, result=result,
                            seconds=record['seconds'], receipt=str(path)))
                path = unit/'measure_PASS.json'
                if path.exists():
                    for step in read(path)['steps']:
                        if step['step']=='axes' and 'seconds' in step:
                            timings['axes'].append(dict(site=site, prior=prior, result=result,
                                seconds=step['seconds'], receipt=str(path)))
                path = unit/'post/tiled_tsdf/merged.json'
                if row['mesh_complete'] and path.exists():
                    record = read(path)
                    peaks.append(dict(site=site, prior=prior, result=result,
                        cgroup_peak_gib=record['merge_cgroup_peak_gb'], receipt=str(path), sha256=sha(path)))
    counts = {k: sum(r[k] for r in rows) for k in [
        'training_complete','model_30000_exists','health_stopped','mesh_complete',
        'core_scored','full_post_complete','full_measure_complete']}
    summary = {k:dict(n=len(values), minimum_minutes=min(v['seconds'] for v in values)/60,
        median_minutes=statistics.median(v['seconds'] for v in values)/60,
        maximum_minutes=max(v['seconds'] for v in values)/60) for k,values in timings.items() if values}
    result = dict(at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), counts=counts,
        queue_snapshot=state, units=rows, timings=timings, timing_summary=summary,
        successful_mesh_cgroup_peaks=peaks,
        limitations=['Completed TSDF samples are ALS; LoD2 peak RAM and duration remain unmeasured.',
            'Observed TSDF equivalence covers two 16 m real-input regions, not a full-scene legacy comparison.',
            'Estimates exclude new failures and additional host-memory contention.'],
        queue_changed=False, training_restarted=False, scientific_verdict=None)
    doc = Path('/docs')
    save(doc/'tables/post_completion_audit.json', result)
    n=counts; pmin=min(p['cgroup_peak_gib'] for p in peaks);pmax=max(p['cgroup_peak_gib'] for p in peaks)
    lines=['# 저장된 모델의 남은 후처리 완료 방안', '', f"확인: {result['at']}", '',
        '**완료된 학습 모델의 후처리는 재학습 없이 계속할 수 있다.** 현재 장애를 모델 소실이나 학습 중단과 혼동하지 않는다.', '',
        '| 단계 | 확인된 수 |', '|---|---:|',
        f"| 30,000회 학습 완료 및 모델 파일 존재 | {n['training_complete']} |",
        f"| 메시와 핵심 패치 채점 완료 | {n['core_scored']} |",
        f"| 가상 시점까지 후처리 완료 | {n['full_post_complete']} |",
        f"| 8.3 추가 지표까지 채점 완료 | {n['full_measure_complete']} |", '',
        f"별도로 학습 중단 {n['health_stopped']}개가 있으며, 대기열의 진행 중 학습은 JSON에 기록했다. "
        '이 기록의 19개 완료 모델과 진행 중 1개가 정상 완료하면, 최종 30,000회 모델로 후처리할 수 있는 범위는 20개다. '
        '중단 4개를 후처리로 완료 판으로 바꾸지 않는다.', '',
        '## 현재 대기 원인', '',
        f"대기열 상태는 {state['status']}, 전체 중지 표시는 {state['stops']}다. "
        f"호스트 여유 메모리는 {state['available_GiB']:.2f} GiB, 후처리 시작 조건은 {state['required_post_GiB']} GiB를 60초 유지하는 것이다. "
        '진행 중인 CPU 8.3 채점이 공유 잠금을 잡고 있으며, 실행기는 CPU 채점과 큰 후처리를 동시에 배정하지 않는다. '
        '따라서 지금 GPU 하나가 쉬는 것은 후처리 오류 증거가 아니다.', '',
        f"성공한 {len(peaks)}개 조각 TSDF의 컨테이너 최대 사용량은 {pmin:.3f}~{pmax:.3f} GiB다. "
        '현재 한도 40 GiB 안에서 완료했다. 모두 항공 LiDAR 결과이므로 아직 처리하지 않은 LoD2까지 메모리 상한을 보장하지 않는다.', '',
        '## 완료 경로', '',
        '1. 진행 중인 마지막 학습과 CPU 채점은 유지한다. 학습 종료 후 약 14 GiB의 현재 컨테이너 사용량이 해제되면 후처리 입장 여건이 좋아진다. 실제 여유 메모리는 다시 확인한다.',
        '2. 저장된 30,000회 모델을 같은 영상·카메라·5 cm 복셀·25 cm 절단 거리로 조각별 TSDF 처리한다. 이미 끝난 메시와 표는 다시 계산하지 않는다.',
        '3. 결과를 빨리 읽으려면 남은 LoD2의 메시와 보존 면적·면 없음 넓이를 먼저 채점하고, 가상 시점 및 8.3 추가 지표를 뒤에 배정한다. 이는 처리 순서 제안이며 현재 실행기의 순서를 변경한 것은 아니다.',
        '4. 큰 후처리는 한 번에 하나씩 유지한다. LoD2에서 한도를 넘는 경우에는 실패 단계가 타일 통합인지 최종 합치기인지 먼저 구분한다. 타일 통합은 더 작은 조각, 합치기는 디스크 기반 병합으로 대응할 수 있으나, 구현·동일성 검증을 마친 뒤 적용해야 한다.', '',
        '## 예상 시간과 조건', '',
        '완료된 실행에서 가상 시점 단계는 약 1.4~2.6분, 8.3 CPU 채점은 약 9~33분/판이다. '
        '메시 단계는 대기 시간을 뺀 기존 기록상 대략 8~17분/판이다. '
        '현재 실행 중 작업 뒤 핵심 채점을 우선 배정하면 남은 최대 9개 메시·핵심 채점에 약 2~3시간, '
        '추가 지표·검증·전달까지 포함하면 약 6~12시간을 운영 계획 범위로 잡는다. '
        '이는 LoD2가 기존 ALS와 비슷한 실행량이라는 가정이며 완료 약속이나 측정된 LoD2 시간은 아니다. '
        '새 오류·자원 대기가 생기면 그만큼 늘어난다. 현재 순서를 그대로 두면 추가 지표가 핵심 표보다 먼저 실행될 수 있다.', '',
        '## 바꾼 것', '',
        '이 조사는 완료 모델·메시·채점 영수증과 실제 최대 메모리를 따로 세었다. '
        '학습·손실·채점 규칙·판·메모리 조건·실행 순서는 바꾸지 않았다. '
        '별도 중단 판 목록에서는 하위 폴더 체크포인트 누락을 수정했다. '
        '그 수정은 남은 정상 모델의 후처리 가능성과 별개다.', '',
        '[모델별 상태 및 계산 근거](tables/post_completion_audit.json). scientific_verdict: null.']
    (doc/'후처리_완료방안_v1.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(counts=counts, peak_gib=[pmin,pmax], summary=summary), ensure_ascii=False))


if __name__=='__main__':
    main()
