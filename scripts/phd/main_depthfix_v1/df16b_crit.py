"""Append the 6절 criteria values (tables/res_criteria.csv) for the listed arms to a summary md written by df16_md.py (host python, stdlib).
usage: python3 df16b_crit.py <name> <arm,arm,...>   (arms as p1,p3; rows whose 'arm' is one of them). Values only, no verdict."""
import csv, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3]; D = R/'docs/experiments/phd/main_depthfix_v1'
name, arms = sys.argv[1], [f'판 {a[1:]}' for a in sys.argv[2].split(',')]
def f(x, d=1):
    try: return f'{float(x):.{d}f}'
    except (TypeError, ValueError): return '—'
rows = [r for r in csv.DictReader(open(D/'tables/res_criteria.csv')) if r['arm'] in arms]
L = ['', '## 6절 판정 기준 값 (기준 추출, 씨앗 0; 값만 싣는다)', '',
     '- 열: 주 지표(잃은 %)와 비교 판의 값, 상대 변화 %, 절대 변화 %p, 판 0 두 씨앗 차이 %p(주 지표), 지킬 값 1 변화 %p, 정확도·완전도 변화 %p, 함께 볼 값 변화 %p와 그 판 0 두 씨앗 차이 %p, 뜬 면 비(이 판 ÷ 비교 판), 30,000회 가우시안 수 비.',
     '- 씨앗 차이 칸은 판 0 씨앗 0·1이 모두 채점된 장면만 값이 있다. 판정은 사람이 한다.', '',
     '| 장면 | 판 | 비교 판 | 주 지표 % | 비교 판 주 지표 % | 상대 변화 % | 절대 변화 %p | 판 0 씨앗 차이 %p | 지킬 값 1 변화 %p | 정확도 변화 %p | 완전도 변화 %p | 함께 볼 값 변화 %p | 함께 볼 값 씨앗 차이 %p | 뜬 면 비 | 가우시안 수 비 |',
     '|' + '---|'*15]
for r in rows:
    L.append('| ' + ' | '.join([r['scene'], r['arm'], r['against'], f(r['main_lost_pct']), f(r['against_main_lost_pct']), f(r['main_rel_change_pct']), f(r['main_abs_change_pp'], 2),
             f(r['p0_seed_diff_main_pp'], 2), f(r['keep1_change_pp'], 2), f(r['accuracy_change_pp'], 2), f(r['completeness_change_pp'], 2), f(r['also_fixed_change_pp'], 2),
             f(r['p0_seed_diff_also_fixed_pp'], 2), f(r['floating_ratio'], 2), f(r['gaussians_ratio'], 2)]) + ' |')
p = D/f'{name}.md'; p.write_text(p.read_text().rstrip('\n') + '\n' + '\n'.join(L) + '\n'); print('CRIT', len(rows), p)
