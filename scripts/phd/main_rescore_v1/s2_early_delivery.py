"""Immutable delivery of completed stage-2 outputs while R1 processing continues."""
from common import *
import common, shutil, zipfile
from add3_publish import FAMILIES, NAMES, pct
from publish_tables import CELL_NAMES

def main():
    cfg()
    live = D
    snapshot = live / 'early_delivery_20261104'
    assert not snapshot.exists(), 'Do not overwrite the early delivery'
    snapshot.mkdir()
    common.D = snapshot
    completed, pending, inputs = [], [], []
    for site in ['B0_b10', 'R1rep_b10']:
        tables = {k: [] for k in range(3, 9)}
        for prior in ['ALS', 'LoD2']:
            for family in FAMILIES + (['fusion_mvswalls', 'judgment_mesh_mvswalls', 'oracle_mvswalls'] if prior == 'ALS' else []):
                key = f'{site}__{prior}__{family}'
                p = O / 'scores' / key / 'values.json'
                if not p.exists():
                    pending.append(dict(key=key, status='진행 중', reason='FINALTRAIN 완료 영수증 대기' if family == 'FINALTRAIN_30000' else '학습 시점 메시 계산·채점 중'))
                    continue
                v = json.loads(p.read_text())
                b = dict(site=site, prior=prior, key=key, method=NAMES[family], status='PASS', source=str(p), source_sha256=sha(p), surface=v['mesh'], surface_sha256=v['mesh_sha256'])
                assert 'r8' not in b['method']
                tables[3].append(dict(b, **v['scene']))
                for cell in v['cells']:
                    r = dict(b, **cell, cell_name=CELL_NAMES[cell['cell']])
                    tables[4].append(r)
                    if family in ['baseline_30000', 'judgment_mesh', 'oracle', 'FINALTRAIN_30000', 'judgment_mesh_mvswalls', 'oracle_mvswalls']:
                        tables[7].append(r)
                tables[5].extend(dict(b, **r) for r in v['offsets'])
                tables[8].append(dict(b, **v['band']))
                completed.append(b)
                if family in ['prior', 'mvs']:
                    inputs.append(dict(b, reuse='원래 입력 면·새 τ·cells_v2·기둥·400점/m²의 기존 점수 및 점 위치 재사용'))
                target = snapshot / 'scores' / key / 'values.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        for p in sorted((live / 'tables').glob(f'target_quality_{site}__*.json')):
            tables[6].extend(json.loads(p.read_text())['rows'])
        for k, rows in tables.items():
            table(f'{site}_table{k}', rows)
        lines = ['| 사전 정보 | 방법 | 완전성 % | 정확성 % | 참값 거리 cm | 결과 거리 cm |', '|---|---|---:|---:|---:|---:|']
        for r in tables[3]:
            lines.append('| ' + ' | '.join([r['prior'], r['method'], *[pct(r[k]) for k in ['completeness', 'accuracy', 'gt_mean_m', 'result_mean_m']]]) + ' |')
        lines += ['', '- 완료된 결과만 수록. 진행 중 항목은 `tables/pending.md`.', '- 표 3~8: `tables/' + site + '_table*.{json,csv,md}`.', '- scientific_verdict: null.']
        (snapshot / (LABELS[site] + '_비교방법_채점.md')).write_text('\n'.join(lines) + '\n')
    assert sum(r['site'] == 'B0_b10' for r in completed) == 23
    table('pending', pending)
    table('input_reuse', inputs)
    for p in sorted((live / 'tables').glob('*check_*.json')):
        for ext in ['.json', '.csv', '.md']:
            q = p.with_suffix(ext)
            if q.exists(): shutil.copy2(q, snapshot / 'tables' / q.name)
    reviews = {}
    for p in sorted((O / 'validation').glob('visual_*.json')):
        obj = json.loads(p.read_text())
        rows = obj.get('rows', [obj])
        for r in rows: reviews[r.get('name', r.get('figure', p.stem))] = r
        dest = snapshot / 'validation' / p.name
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(p, dest)
    figs = []
    for p in sorted((live / 'figures').glob('*.png')):
        # Each completed image already received its single visual inspection.
        assert p.stem in reviews, (p.stem, list(reviews))
        assert reviews[p.stem]['status'] == 'PASS' and reviews[p.stem]['review_count'] == 1
        for ext in ['.png', '.json']:
            q = p.with_suffix(ext)
            assert q.exists()
            dest = snapshot / 'figures' / q.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(q, dest)
        figs.append(p.name)
    # Unchanged figure 6.2 is copied from the sealed stage-1 delivery.
    for p in (live.parent / 'addendum3_stage1' / 'figures').glob('그림6_2.*'):
        shutil.copy2(p, snapshot / 'figures' / p.name)
    for name in ['issues.md', 'progress.md']:
        shutil.copy2(live / name, snapshot / name)
    b0 = [r for r in completed if r['site'] == 'B0_b10']
    r1 = [r for r in completed if r['site'] == 'R1rep_b10']
    lines = [
        '| 항목 | 완료분 |', '|---|---|',
        f'| B0 | {len(b0)}/23판; 본 방법 30,000회 두 사전 정보 포함; 표 3~8 |',
        f'| R1 | {len(r1)}/23판; 진행 중 결과는 별도 목록 |',
        '| 그림 6.1 | 이름표 넷 수정; 새 화살표 둘 모두 항공 LiDAR 칸 2 |',
        '| B0 그림 7.3~7.7 | 항공 LiDAR·LoD2 총 10장 |',
        '| 깊이 점검 그림 | B0 3장·R1 2장 |',
        '| 그림 6.2 | 단계 1 완료본 그대로 포함 |',
        '', '| B0 본 방법 | 완전성 % | 정확성 % |', '|---|---:|---:|',
    ]
    for r in b0:
        if r['key'].endswith('__FINALTRAIN_30000'):
            v = json.loads(Path(r['source']).read_text())['scene']
            lines.append(f"| {r['prior']} | {100*v['completeness']:.2f} | {100*v['accuracy']:.2f} |")
    lines += [
        '', '- [B0 채점](B0_비교방법_채점.md) · [R1 완료분 채점](R1_비교방법_채점.md) · [진행 중 항목](tables/pending.md).',
        '- [그림 6.1](figures/fig6_1_실험지역.png): 채광창 89.27 m², R1 계단 185.94 m². LoD2 대체 없음.',
        '- 기존 B173 긴 벽 이름표는 칸 4가 9.31 m²여서 생략 유지.',
        '- 학습 없음. 메시·점수·검사 캐시 재사용; 새 계산은 고정된 학습 시점 메시 규칙 적용.',
        '- 기존 재현 검사 PASS를 재사용. 새 그림의 시각 검토는 각각 1회.',
        '- R1 본 방법 및 후속 그림·계보 검사는 완료 후 최종 묶음에 추가.',
        '- scientific_verdict: null.',
    ]
    (snapshot / '완료분_보고.md').write_text('\n'.join(lines) + '\n')
    for directory in [R / 'scripts/phd/main_rescore_v1', C]:
        dest = snapshot / ('scripts' if directory.name == 'main_rescore_v1' and directory.parent.name == 'phd' else 'configs')
        dest.mkdir(exist_ok=True)
        for p in sorted(directory.iterdir()):
            if p.is_file() and p.suffix in ['.py', '.sh', '.json']:
                shutil.copy2(p, dest / p.name)
    files = {str(p.relative_to(snapshot)): sha(p) for p in sorted(snapshot.rglob('*')) if p.is_file()}
    manifest = dict(created_at=now(), status='PARTIAL_COMPLETED_OUTPUTS', completed_scores=len(completed), pending=pending, newly_reviewed_figures=len(figs), files=files, scientific_verdict=None)
    dump(snapshot / 'manifest.json', manifest)
    archive = O / 'PHD-MAIN-RESCORE-v1-stage2-completed-first.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(snapshot.rglob('*')):
            if p.is_file(): z.write(p, p.relative_to(snapshot))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name, digest in files.items(): assert hashlib.sha256(z.read(name)).hexdigest() == digest
    receipt = dict(archive=str(archive), bytes=archive.stat().st_size, sha256=sha(archive), members=len(files)+1, crc='PASS', member_sha256='PASS', completed_scores=len(completed), pending=len(pending), scientific_verdict=None)
    dump(live / 'early_delivery.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
