"""Host helper: print the numbers the report needs from the tables (facts only), as compact markdown blocks.

  python3 tu_report_numbers.py > /tmp/...md
"""
import json
from pathlib import Path

D = Path(__file__).resolve().parents[3] / 'docs/experiments/phd/main_trainunit_v1'
T = D / 'tables'
SITE = {'B0_b10': 'B0', 'R1rep_b10': 'R1', 'B173nb_b10': 'B173 주변'}
PR = {'ALS': '항공 LiDAR', 'LoD2': 'LoD2'}


def rows(name):
    p = T / f'{name}.json'
    return json.loads(p.read_text())['rows'] if p.exists() else []


def f(v, d=1):
    return '—' if v is None else f'{v:.{d}f}'


def main():
    summ = rows('summary_runs')
    print('## 장면 전체 완전성 / 정확성 (%)\n')
    print('| 장면 | 사전 정보 | 기준 | 씨앗 반복 | 가 | 다 |\n|---|---|---|---|---|---|')
    for site in SITE:
        for prior in PR:
            cells = []
            for run in ['기준', '씨앗반복', '가', '다']:
                r = next((x for x in summ if x['site'] == site and x['prior'] == prior and x['run'] == run), None)
                cells.append('결과 없음' if not r or r['status'] != '있음' else f"{f(r['완전성_장면 전체'])} / {f(r['정확성_장면 전체'])}")
            print(f'| {SITE[site]} | {PR[prior]} | ' + ' | '.join(cells) + ' |')
    comp = rows('comparisons')
    print('\n## 네 비교 (장면 전체, %p; 흔들림 폭 = |씨앗 반복 − 기준|)\n')
    print('| 장면 | 사전 정보 | 값 | 흔들림 폭 | 1 씨앗−기준 | 2 가−나 | 3 나−다 | 4 다−기준 |\n|---|---|---|---|---|---|---|---|')
    for site in SITE:
        for prior in PR:
            for metric in ['완전성_장면 전체', '정확성_장면 전체']:
                r = next((x for x in comp if x['site'] == site and x['prior'] == prior and x['metric'] == metric), None)
                if not r:
                    continue
                print(f"| {SITE[site]} | {PR[prior]} | {metric.split('_')[0]} | {f(r['흔들림폭_씨앗'], 2)} | {f(r['비교1_씨앗반복-기준'], 2)} | "
                      f"{f(r['비교2_가-나'], 2)} | {f(r['비교3_나-다'], 2)} | {f(r['비교4_다-기준'], 2)} |")
    st = rows('run_stats')
    print('\n## 메모리와 시간\n')
    print('| 단위 | 사전 정보 | 판 | 상태 | 학습 영상 | 영상당 학습 횟수 | 학습 시간 (시간) | 가우시안 최종 / 최대 | GPU 예약 최대 (GiB) | PSNR 학습 5장 / 평가 |\n|---|---|---|---|---|---|---|---|---|---|')
    for r in st:
        print(f"| {r['unit']} | {PR[r['prior']]} | {r['label']} | {r.get('status', 'FINALTRAIN 완료')} | {r['train_images']} | {f(r['iterations_per_image'])} | "
              f"{f(r['train_seconds'] / 3600 if r['train_seconds'] else None, 2)} | {r['final_gaussians'] or '—'} / {r['max_gaussians'] or '—'} | "
              f"{f(r['peak_reserved_GiB'], 1)} | {f(r['psnr_train_5views'], 2)} / {f(r['psnr_test'], 2)} |")
    band = rows('cells_boundary_band')
    if band:
        print('\n## 칸 경계 띠 (원래 칸 경계 ±2 m 안 참값 점)\n')
        print('| 장면 | 사전 정보 | 판 | 부분 | 점 수 | 완전성 | 뜬 면 비율 | 면 없음 |\n|---|---|---|---|---|---|---|---|')
        for r in band:
            if r.get('status') != '있음':
                continue
            print(f"| {SITE[r['site']]} | {PR[r['prior']]} | {r['run']} | {r['part']} | {r['rows']} | {f(r['completeness_pct'])} | {f(r['floating_pct'])} | {f(r['no_surface_pct'])} |")


if __name__ == '__main__':
    main()
