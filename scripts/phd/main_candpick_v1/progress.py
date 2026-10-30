"""Compact live execution accounting, separate from scored outcomes."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from result_io import save


def main():
    cfg = json.loads(Path('/config/candpick_v1.json').read_text()); rows = []
    for unit in cfg['units']:
        for spec in cfg['arm_order']:
            arm = f"cp_{spec['start']}_sh{spec['sh_degree']}_{unit}"; root = Path('/out/runs') / arm
            complete = root / 'complete.json'; progress = root / 'progress.json'
            if complete.exists():
                d = json.loads(complete.read_text()); state, step = 'COMPLETE', 3000
            elif progress.exists():
                d = json.loads(progress.read_text()); state, step = 'RUNNING', d['iteration']
            elif list(root.glob('attempt_*.json')): d, state, step = {}, 'PREPARING', 0
            else: d, state, step = {}, 'NOT_STARTED', None
            failures = sorted(root.glob('failure_*.json'))
            attempts = sorted(root.glob('attempt_*.json'))
            if state != 'COMPLETE' and failures and attempts and failures[-1].stat().st_mtime > attempts[-1].stat().st_mtime:
                state = 'ERROR'
            rows.append(dict(arm=arm, status=state, iteration=step,
                elapsed_seconds=d.get('elapsed_seconds'), recorded_failures=len(failures)))
    at = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    n = sum(r['status'] == 'COMPLETE' for r in rows)
    report = dict(at=at, completed=n, designed=24, rows=rows, scientific_verdict=None)
    save(Path('/docs/progress.json'), report)
    text = ['# 후보 고르기 시험 실행 상태', '', f'갱신: {at}', '',
        f'학습 완료 **{n}/24판**. 실행 중 수치는 마지막 100회 기록 기준이다. 채점과 기준 충족은 results/status.json 및 기준 표에서 별도로 확인한다.', '',
        '| 판 | 실행 상태 | 반복 |', '|---|---|---:|']
    text += [f"| {r['arm']} | {r['status']} | {r['iteration'] if r['iteration'] is not None else '—'} |" for r in rows]
    text += ['', '설정은 candpick_v1.json의 고정 해시를 사용한다. 학습 손실은 전체 사진의 L1+D-SSIM이며 후보의 불투명도·색만 갱신한다. 매 판 종료 시 바탕과 후보 기하의 학습 전후 메모리 해시를 대조한다.', '', 'scientific_verdict: null', '']
    Path('/docs/progress.md').write_text('\n'.join(text))
    print(json.dumps(report))


if __name__ == '__main__': main()
