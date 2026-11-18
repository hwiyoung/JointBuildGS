"""PHD-MAIN-JUDGESTRUCT-v1 공통. 학습·새 광도 점수·새 기하 계산 없음, CPU만. scientific_verdict: null.
JUDGEABL-v1 공통(그리고 그것이 옮겨 쓰는 JUDGEPROBE-v1·JUDGECHECK-v2 함수)을 그대로 읽어 쓴다."""
import sys, json
sys.path.insert(0, '/repo/scripts/phd/main_judgeabl_v1')
from common import *          # JUDGEABL common: J, JC, JP, JA, PH, C, D, O, R, CASE, MATCH, JUD, PLACE, REGIONS, CASES, plane_distance, loadz, dump, sha, now, Timer, wq
import numpy as np
JABL = PH/'main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1'
JABL_DOC = R/'docs/experiments/phd/main_judgeabl_v1'
JC_DOC = R/'docs/experiments/phd/main_judgecheck_v2'
CN = [CASE[c] for c in CASES]
STATE = {0: CASE[0], 1: CASE[1], 2: CASE[2], 4: CASE[4], 3: '네 경우 밖', -2: '동률', -3: '참값 점 3개 미만', -9: '참값 없음'}
STATE_ORDER = [0, 1, 2, 4, 3]
PN = {'LoD2': 'LoD2', 'ALS': '항공 LiDAR'}
SURF = {'LoD2': [('지붕', [1]), ('벽', [2]), ('모두', [1, 2])], 'ALS': [('지붕', [1])]}
def cfg():
    lock = json.loads((C/'judgestruct_v1.lock.json').read_text()); assert sha(C/'judgestruct_v1.json') == lock['config_sha256'], 'config changed after lock'
    return json.loads((C/'judgestruct_v1.json').read_text())
def progress(s):
    with (D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def issue(s):
    with (D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def write(name, df, note='', sub='tables', md=None):
    import pandas as pd
    T = D/sub; T.mkdir(parents=True, exist_ok=True); df.to_csv(T/f'{name}.csv', index=False)
    (T/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df if md is None else md(df)
    lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False):
        lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x))) for x in r) + ' |')
    (T/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
