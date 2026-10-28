"""Track the six required ALS runs and prove their presence in an interim ZIP."""
import hashlib
import json
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def snapshot(d=Path('/docs'), o=Path('/out'), c=Path('/config')):
    cfg = read(c / 'priority_delivery_v1.json')
    records = []
    members = []
    for key in cfg['keys']:
        path = d / 'tables/meshes' / (key + '.json')
        receipt = read(path, {})
        state = read(o / 'status' / ('mesh_' + key + '.json'), {})
        records.append(dict(key=key, status=receipt.get('status', state.get('stage', 'PENDING')),
                            finished_at=receipt.get('finished_at')))
        members.append('tables/meshes/' + key + '.json')
    figures = {r['case']: r for r in read(d / 'tables/case_figures.json', {'cases': []})['cases']}
    cases = []
    for name in cfg['cases']:
        receipt = figures.get(name, {})
        paths = [f'figures/{name}/view_{i}.png' for i in range(1, cfg['views_per_case'] + 1)]
        for row in receipt.get('rows', []):
            if not row.get('empty', False):
                paths.append('figures/web/' + Path(row['glb']).name)
        ready = (receipt.get('status') == 'PASS' and receipt.get('views') == cfg['views_per_case']
                 and len(receipt.get('rows', [])) == 6
                 and all((d / p).is_file() and (d / p).stat().st_size > 0 for p in paths))
        cases.append(dict(case=name, status='PASS' if ready else 'PENDING', members=paths))
        members.extend(paths)
    passed = sum(r['status'] == 'PASS' for r in records)
    completed_cases = sum(r['status'] == 'PASS' for r in cases)
    validation = read(d / 'tables/priority_validation.json', {})
    verified = validation.get('status') == 'PASS' and validation.get('completed') == 6
    members.append('tables/priority_validation.json')
    return dict(status='READY' if passed == 6 and completed_cases == 7 and verified else 'PENDING',
                deadline_kst=cfg['deadline_kst'], completed=passed, required=6,
                validation_status=validation.get('status', 'PENDING'),
                completed_cases=completed_cases, required_cases=7, records=records,
                cases=cases, required_members=members, scientific_verdict=None)


def update():
    d, o = Path('/docs'), Path('/out')
    state = snapshot()
    p = d / 'tables/priority_six.json'
    tmp = p.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(p)
    lines = ['# 설명용 필수 여섯 개', '', '마감: 2026-10-30 09:30 한국 시각. [이 발주에서 냄]', '',
             '| 평가 지역 | 방법 | 상태 | 완료 시각 |', '|---|---|---|---|']
    for r in state['records']:
        site, _, run = r['key'].split('__')
        lines.append(f"| {site} | {'판정 끔' if run == 'nojudge_ALS_s0' else '판 4'} | {r['status']} | {r['finished_at'] or '아직 완료되지 않음'} |")
    lines += ['', f"메시 {state['completed']}/6개, 사례 그림 {state['completed_cases']}/7개 완료.",
              '수치는 mesh_comparison 표와 대상별 원본 기록에 있다. PNG는 사례마다 고정 시점 7개이며 웹용 GLB를 함께 넣는다.',
              '여섯 개 및 사례 그림이 모두 준비되면 정기 시각과 별개로 중간 묶음을 즉시 만든다.', '', 'scientific_verdict: null']
    (d / 'tables/priority_six.md').write_text('\n'.join(lines) + '\n')
    marker = o / 'status/delivery_priority.json'
    if state['status'] == 'READY' and not marker.exists():
        from deliver import package
        archive = package()
        with zipfile.ZipFile(archive) as z:
            manifest = {r['name']: r for r in json.loads(z.read('manifest.json'))['files']}
            for name in state['required_members']:
                data = z.read(name)
                assert hashlib.sha256(data).hexdigest() == manifest[name]['sha256'], name
            for r in state['records']:
                assert json.loads(z.read('tables/meshes/' + r['key'] + '.json'))['status'] == 'PASS'
            assert json.loads(z.read('priority_status.json'))['status'] == 'READY'
        delivered = dict(file=str(archive), status='PASS', required_meshes=6, required_cases=7,
                         checked_members=len(state['required_members']),
                         at=datetime.now(timezone(timedelta(hours=9))).isoformat(), scientific_verdict=None)
        marker.write_text(json.dumps(delivered, ensure_ascii=False, indent=2) + '\n')
    return state


if __name__ == '__main__':
    print(json.dumps(update(), ensure_ascii=False))
