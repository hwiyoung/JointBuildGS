"""Check 6 tables: rule simulations (order 6.1) and the user-decided reference simulation (check6_addendum_v1), plus the confirm-run selection."""
from common import *
def main():
    rule, ref = [], []
    for stem, fam, kind, cell in [('B0_b10__LoD2', 'vdrop_own', 'rule', 'c3'), ('B0_b10__LoD2', 'vdrop_gt', 'rule', 'c3'), ('R1rep_b10__ALS', 'refsim_gt_bg', 'reference', 'c2'), ('R1rep_b10__ALS', 'refsim_own_bg', 'reference', 'c2')]:
        p = O/'sim'/f'{stem}__{fam}'/'eval.json'
        if not p.exists(): continue
        rows = [r for r in json.loads(p.read_text())['rows'] if r['cell'] == cell]
        extra = json.loads((O/'sim'/f'{stem}__{fam}'/('drop_views.json' if fam.startswith('vdrop') else 'prep.json')).read_text())
        for r in rows:
            r = dict(r, simulation=('4-가 영상 빼기(틀린 결과 면을 재현한 영상)' if kind == 'rule' else '3-라 배경 무리 빼기(참고, 범인 후보 아님)'),
                     removed=(f"영상 {len(extra['drop'])}/{extra['views']}장" if fam.startswith('vdrop') else f"가우시안 {extra['dropped']}/{extra['in_range']}개(기록 범위)"),
                     cls_label=r['cls'] if kind == 'rule' else f"{r['cls']}(참고)")
            (rule if kind == 'rule' else ref).append(r)
    table('check6_simulation', rule); table('check6_reference', ref)
    table('check6_confirm_runs', [dict(selection='6.2: 장면 × 판마다 회복률 20 % 이상인 범인 후보 중 가장 큰 것', culprit_candidates='없음(4.5 범인 후보 표, 여섯 칸 × 판)', runs=0,
                                       note='확인 학습을 돌리지 않음. 4-가 영상 빼기 모의는 범인 무리가 아니라 스위치 대상이 없다')])
    print('C6', [(r['cell'], r['arm'], round(r['recovery_pct'], 1), r['cls']) for r in rule+ref])
if __name__ == '__main__': main()
