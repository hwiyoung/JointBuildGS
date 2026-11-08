"""A1-only continuation of add11.process; no training, rendering or mesh reads."""
import gzip
import add11 as b
from common import *
import numpy as np
import zipfile

CFG = json.loads((C / 'addendum12.json').read_text())
assert sha(C / 'addendum12.json') == json.loads((C / 'addendum12.lock.json').read_text())['config_sha256']
W = O / 'addendum12'
T = D / 'tables/addendum12'
OLD = D / 'tables/addendum11'
for folder in [W, T, W / 'distance_A1', W / 'interim_data', W / 'final_data']:
    folder.mkdir(parents=True, exist_ok=True)

inherited_meta = b.meta


def record(**kwargs):
    result = inherited_meta(**kwargs)
    result['inherited_config_sha256'] = result['config_sha256']
    result['config_sha256'] = sha(C / 'addendum12.json')
    result['addendum'] = 12
    return result


# Rebind only destinations and the requested method/tau list. All geometry,
# eligibility, statistics and point-array export are the existing add11 code.
b.W = W
b.T = T
b.A = dict(b.A, methods=['A1'], presentation_methods=['A1'], tau_multipliers=[1.])
b.meta = record
SCENES = CFG['required_scenes'] + [s for s in CFG['optional_scenes']
    if (O / 'scenes' / (s[0] + '__' + s[1]) / 'distances/A1.npz').exists()]
CASE_MAP = {'c3': ['B0_b10', 'ALS'], 'c1': ['B173nb_b10', 'ALS'],
            'c4': ['R1rep_b10', 'ALS'], 'c2': ['B0_b10', 'LoD2']}


def lock_inputs():
    paths = [C / 'addendum12.json', C / 'addendum12.lock.json',
             OLD / 'full_final.csv', OLD / 'presentation.json',
             D / 'README_거리지도자료.md']
    paths += [Path(__file__).with_name(name) for name in
        ['add12.py', 'add11.py', 'add2_scores.py', 'normal_line.py',
         'cylinder.py', 'cylinder.cpp', 'run_cpu.sh']]
    for site, prior in SCENES:
        root = O / 'scenes' / f'{site}__{prior}'
        paths += [root / 'rows.npz', root / 'stage1_cells.npz',
                  root / 'distances/prior.npz', root / 'distances/mvs.npz',
                  O / 'reference' / site / 'dense.npz',
                  D / 'tables/addendum2/stage1' / f'{site}__{prior}.csv']
        paths += list(b.sources(site, prior, 'A1')[:4])
    paths += [D / 'tables/addendum10' / f'{key}_reference_rows.csv.gz'
              for key in CASE_MAP]
    root = O / 'scenes/B0_b10__LoD2'
    paths += [root / 'rows.npz', root / 'stage1_cells.npz',
              root / 'distances/FINALTRAIN_30000.npz',
              O / 'addendum11/cache/B0_b10__LoD2/FINALTRAIN_30000.npz']
    for path in dict.fromkeys(paths):
        b.proof(path)
    dump(D / 'verification/addendum12_input_lock.json',
         record(sources=list(b.INPUTS.values()),
                spatial_index='add11 native Cylinder and same dense reference; previous trees were memory-only and destroyed at exit; rebuild once per physical region'))


def full_table():
    rows = [r for r in b.TABLES if r['case_id'] != 'prior_absent']
    old_fields = next(csv.reader((OLD / 'full_final.csv').open()))
    assert all(list(r) == old_fields for r in rows)
    b.write_csv(T / 'A1_full.csv', rows)
    b.write_csv(T / 'old_rule_checks.csv', b.CHECKS)
    return rows


def presentation():
    a1_rows = b.presentation()
    previous = json.loads((OLD / 'presentation.json').read_text())['rows']
    rows = []
    metrics = ['completeness_pct', 'accuracy_old_pct', 'accuracy_new_pct',
               'reference_mean_abs_m', 'reference_median_abs_m', 'reference_p95_abs_m',
               'result_mean_abs_m', 'result_median_abs_m', 'result_p95_abs_m',
               'reference_none_pct', 'result_none_pct']
    for a1 in a1_rows:
        ft = next(r for r in previous if r['group'] == a1['group']
                  and r['case_id'] == a1['case_id'] and r['method'] == 'FINALTRAIN_30000')
        for src in [a1, ft]:
            row = {k: v for k, v in src.items() if not k.endswith('_gap_to_best')}
            row['small'] = '적음' if row['n_gt'] < 1000 else ''
            for metric in metrics:
                row[metric + '_A1_minus_FINALTRAIN'] = (
                    a1[metric] - ft[metric] if a1[metric] is not None and ft[metric] is not None else None)
            rows.append(row)
    b.write_csv(T / 'presentation.csv', rows)
    dump(T / 'presentation.json', record(rows=rows,
         weighting='completeness: reference N; accuracy: eligible result N separately per rule; means: finite-hit N; median/p95: pooled finite distances',
         difference='A1 minus FINALTRAIN_30000; percentage points for percentages, metres for distances',
         FINALTRAIN_source=b.proof(OLD / 'presentation.json')))
    return rows


def check_add10(full, presentation_rows):
    checks = []
    for key, (site, prior) in CASE_MAP.items():
        path = D / 'tables/addendum10' / f'{key}_reference_rows.csv.gz'
        counts = {case: [0, 0] for case in [0, 1, 2, 3, 4, 'all']}
        with gzip.open(path, 'rt', newline='') as handle:
            for row in csv.DictReader(handle):
                if int(row['eligible']) != 1:
                    continue
                case = int(row['case_id'])
                for category in ['all'] + ([case] if case in range(5) else []):
                    counts[category][0] += 1
                    counts[category][1] += row['A1_status'] == 'in'
        for case, (n, correct) in counts.items():
            score = next(r for r in full if r['site'] == site and r['prior'] == prior
                         and r['surface'] == 'all' and r['case_id'] == case)
            pct = 100 * correct / n if n else None
            difference = abs(score['completeness_pct'] - pct) if n else 0.
            assert n == score['n_gt'] and difference < 1e-10
            checks.append(dict(scene=f'{site}__{prior}', case_id=case,
                               n_gt=n, add10_completeness_pct=pct, difference_pp=difference))
    rounded = []
    for group, expected in CFG['expected_completeness_pct'].items():
        for case, target in zip([0, 1, 2, 4], expected):
            row = next(r for r in presentation_rows if r['method'] == 'A1'
                       and r['group'] == group and r['case_id'] == case)
            difference = abs(row['completeness_pct'] - target)
            assert difference <= .05000001, (group, case, row['completeness_pct'], target)
            rounded.append(dict(group=group, case_id=case, requested_rounded_pct=target,
                                calculated_pct=row['completeness_pct'], matches_one_decimal=True))
    return dict(row_table_checks=checks, requested_values=rounded)


def check_pair():
    site, prior, method = 'B0_b10', 'LoD2', 'FINALTRAIN_30000'
    root = O / 'scenes' / f'{site}__{prior}'
    row = loadz(root / 'rows.npz')
    cells = loadz(root / 'stage1_cells.npz')
    scores = loadz(root / 'distances' / (method + '.npz'), b.SCORE_KEYS)
    cache = loadz(O / 'addendum11/cache/B0_b10__LoD2' / (method + '.npz'))
    scores['sample_s'] = cache['sample_s']
    scores['sample_observed_cylinder_1m'] = cache['observed']
    current = b.metric_rows(site, prior, [method], True,
        prepared=dict(row=row, cells=cells, scores={method: scores}, steep={method: cache['steep']}),
        accuracy_rule='normal_cylinder_1m', extended=True)
    previous = list(csv.DictReader((OLD / 'full_final.csv').open()))
    checks = []
    for r in current:
        if r['case_id'] == 'prior_absent':
            continue
        old = next(x for x in previous if x['site'] == site and x['prior'] == prior
                   and x['method'] == method and x['surface'] == r['surface']
                   and x['case_id'] == str(r['case_id']))
        for metric in ['completeness_pct', 'accuracy_old_pct', 'accuracy_new_pct']:
            value = float(old[metric]) if old[metric] else None
            difference = abs(r[metric] - value) if value is not None else 0.
            assert (value is None) == (r[metric] is None) and difference < 1e-10
            checks.append(dict(surface=r['surface'], case_id=r['case_id'],
                               metric=metric, difference_pp=difference))
    b.write_csv(T / 'FINALTRAIN_pair_check.csv', checks)
    return dict(scene=f'{site}__{prior}', method=method,
                saved_add11_distance_and_observation_cache_reused=True,
                new_geometry_queries=0, checks=checks)


def check_npz(full):
    manifests = []
    for path in sorted((W / 'distance_A1').glob('*.npz')):
        site, prior = path.stem.split('__')
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            assert {n.split('__')[1] for n in archive.namelist()
                    if n.startswith('result__')} == {'A1'}
            for name in archive.namelist():
                with archive.open(name) as handle:
                    version = np.lib.format.read_magic(handle)
                    _, _, dtype = np.lib.format._read_array_header(handle, version)
                    assert dtype.kind != 'f' or dtype == np.dtype('float32')
        z = loadz(path, ['reference__case_id', 'reference__eligible',
            'reference__A1__within_tau1', 'result__A1__case_id',
            'result__A1__eligible_new', 'result__A1__eligible_old', 'result__A1__within_tau1'])
        for case in [0, 1, 2, 3, 4, 'all']:
            score = next(r for r in full if r['site'] == site and r['prior'] == prior
                         and r['surface'] == 'all' and r['case_id'] == case)
            for direction, suffix, metric in [('reference', '', 'completeness_pct'),
                    ('result', 'new', 'accuracy_new_pct'), ('result', 'old', 'accuracy_old_pct')]:
                prefix = 'reference__' if direction == 'reference' else 'result__A1__'
                mask = z[prefix + ('eligible' if not suffix else 'eligible_' + suffix)].astype(bool)
                if case != 'all':
                    mask &= z[prefix + 'case_id'] == case
                within = z[('reference__A1__' if direction == 'reference' else prefix) + 'within_tau1']
                value = 100 * (mask & within.astype(bool)).sum() / mask.sum() if mask.any() else None
                assert (value is None and score[metric] is None) or abs(value - score[metric]) < 1e-10
        manifests.append(dict(scene=path.stem, path=str(path), bytes=path.stat().st_size, sha256=sha(path)))
    assert len(manifests) == len(SCENES)
    return manifests


def write_report(rows, checks):
    lines = ['완전성/바꾼 정확성(%), 차이=A1−본 방법(%p).', '',
             '|장면·경우|A1|본 방법|차이|', '|---|---:|---:|---:|']
    for group in ['ALS_pooled', 'B0_LoD2']:
        for case in [0, 1, 2, 4]:
            a, f = [next(r for r in rows if r['group'] == group and r['case_id'] == case
                         and r['method'] == m) for m in ['A1', 'FINALTRAIN_30000']]
            lines.append('|'+('ALS합산' if group == 'ALS_pooled' else 'B0 LoD2')+f' {case}|'
                +f"{a['completeness_pct']:.1f}/{a['accuracy_new_pct']:.1f}|"
                +f"{f['completeness_pct']:.1f}/{f['accuracy_new_pct']:.1f}|"
                +f"{a['completeness_pct']-f['completeness_pct']:+.1f}/{a['accuracy_new_pct']-f['accuracy_new_pct']:+.1f}|")
    maximum = max(x['difference_pp'] for x in b.CHECKS)
    lines += ['', '가중: 완전성=참값 수, 정확성=규칙별 포함 결과 점 수, 평균 거리=유한 거리 점 수.',
        f'완전성은 덧붙임10 참값 행 및 지정한 소수 첫째 자리 값과 일치. 기존 규칙 대조 최대 차이 {maximum:.6f}%p. FINALTRAIN B0 LoD2 재집계 차이 0%p.',
        '필수 네 장면과 선택 R1 LoD2를 포함했다. 모든 NPZ 재집계는 표와 일치한다.',
        '덧붙임11 색인은 메모리에만 있어 같은 코드·참값으로 지역당 1회 복원했다. 새 관측 검사는 이전 제외점만, 미저장 거리는 새로 포함된 비가파른 점만 보충했다.',
        'A1_full.csv: 두 규칙 정확성, 제외 수, 두 방향 평균·중앙값·95%·면 없음. presentation.csv: 두 방법과 차이. distance_A1/: 장면별 점 자료.',
        '학습·렌더·메시 읽기/생성 없음. scientific_verdict: null.']
    text = '\n'.join(lines) + '\n'
    assert len(text) <= 1000, len(text)
    path = D / '보고_덧붙임12.md'
    path.write_text(text)
    return path


def deliver(full, rows, checks, manifests):
    report = write_report(rows, checks)
    # Carry forward the exact array schema, replacing only the package population.
    readme = (D / 'README_거리지도자료.md').read_text()
    begin = readme.index('장면마다')
    end = readme.index('\n\n접두사')
    readme = readme[:begin] + ('이 묶음은 A1(정답 판단 학습)의 점별 자료다. distance_A1/ 아래 필수 네 장면과 선택 R1 LoD2의 NPZ 다섯 개를 제공한다. 참값 공통 배열과 reference__A1__*, result__A1__*만 들어 있다. 부동소수 배열은 float32이며 원래 점 순서를 유지한다.') + readme[end:]
    readme_path = D / 'README_A1거리지도자료.md'
    readme_path.write_text(readme)
    verification = record(status='PASS', scenes=SCENES,
        add10_completeness=checks['add10'], FINALTRAIN_pair=checks['pair'],
        old_rule_checks=b.CHECKS, old_rule_maximum_difference_pp=max(r['difference_pp'] for r in b.CHECKS),
        point_data=manifests, point_data_recount='all five scenes, cases 0-4 and all, completeness and both accuracy rules',
        spatial_indices=len(b.TREES), index_code_reused=True, previous_index_serialized=False,
        training=False, rendering=False, mesh_read=False, mesh_regeneration=False)
    vp = D / 'verification/addendum12.json'
    dump(vp, verification)
    # Ensure inherited documents and scoring source files remain byte-identical.
    for item in b.INPUTS.values():
        path = Path(item['path'])
        if str(path).startswith('/repo/scripts/') or str(path).startswith('/docs/'):
            assert sha(path) == item['sha256'], str(path)
    selections = [(report, report.name), (readme_path, readme_path.name), (vp, 'verification.json')]
    selections += [(p, 'tables/addendum12/' + p.name) for p in sorted(T.glob('*')) if p.is_file()]
    selections += [(p, 'distance_A1/' + p.name) for p in sorted((W / 'distance_A1').glob('*.npz'))]
    selections += [(C / name, 'configs/' + name) for name in ['addendum12.json', 'addendum12.lock.json']]
    selections += [(D / 'verification/addendum12_input_lock.json', 'input_lock.json')]
    hashes = {name: sha(path) for path, name in selections}
    archive = O / 'delivery/PHD-MAIN-GTJUDGE-v1_A1정확성.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', allowZip64=True) as z:
        for path, name in selections:
            z.write(path, name, compress_type=zipfile.ZIP_STORED if path.suffix == '.npz' else zipfile.ZIP_DEFLATED)
        z.writestr('SHA256SUMS', ''.join(h + '  ' + name + '\n' for name, h in hashes.items()))
        z.writestr('manifest.json', json.dumps(record(files=hashes, scenes=SCENES), ensure_ascii=False, indent=2))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name, expected in hashes.items():
            digest = hashlib.sha256()
            with z.open(name) as handle:
                for chunk in iter(lambda: handle.read(8 << 20), b''):
                    digest.update(chunk)
            assert digest.hexdigest() == expected, name
    dump(D / 'verification/addendum12_archive.json', record(status='PASS_ZIP_CRC_AND_MEMBER_SHA256',
         path=str(archive), bytes=archive.stat().st_size, sha256=sha(archive), members=len(selections) + 2))
    print('ADD12_DELIVERED', archive.name, archive.stat().st_size, flush=True)


def main():
    lock_inputs()
    for scene in SCENES:
        site, prior = scene
        phase = 'interim' if scene in CFG['required_scenes'] else 'final'
        b.process(site, prior, ['A1'], phase)
        source = W / (phase + '_data') / f'{site}__{prior}.npz'
        target = W / 'distance_A1' / source.name
        assert not target.exists()
        source.rename(target)
    full = full_table()
    rows = presentation()
    checks = dict(add10=check_add10(full, rows), pair=check_pair())
    manifests = check_npz(full)
    deliver(full, rows, checks, manifests)
    for tree, _ in b.TREES.values():
        tree.close()


if __name__ == '__main__':
    main()
