"""4.1절 '함께 낼 것': 방법 A 융합 점 수, 실제로 쓰인 값(fusion.log), 영상마다 살아남은 화소 비율의 분포 → tables/t4_A_fusion. 참값 읽지 않음.
사용: mf7c_fusion_table.py [box 이름 ...]  (없으면 campus)"""
import sys, re
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC

def one(name, mask_json):
    a = json.loads(mask_json.read_text()); log = (O/'fusion'/name/'fusion.log').read_text(errors='replace')
    used = {k: v for k, v in re.findall(r'fusion\.cc:\d+\] (\w+): ([^\n]+)', log)}
    r = [x['survived']/x['valid'] for x in a['per_image'] if x['valid'] > 0]
    q = np.quantile(r, [0, .1, .25, .5, .75, .9, 1])
    return dict(workspace=name, fused_points=a['fused_points'], images=len(a['per_image']), images_with_depth=len(r), pixels_valid=a['pixels_valid'], pixels_survived=a['pixels_survived'],
                survived_pct=a['survived_pct'], **{f'per_image_q{int(p*100)}_pct': 100*float(v) for p, v in zip([0, .1, .25, .5, .75, .9, 1], q)},
                per_image_mean_pct=100*float(np.mean(r)), used_options=used, check3=a.get('check3'))

def main(names):
    MC.cfg(); rows = []
    for n in names:
        mj = O/'masks'/('A.json' if n == 'campus' else f'{n}_A.json'); rows.append(one(n, mj))
    T_ = Path('/docs/tables'); T_.mkdir(exist_ok=True)
    dump(T_/'t4_A_fusion.json', dict(rows=rows, note='방법 A: 융합 점 수, fusion.log 에 찍힌 실제 값, 영상마다 살아남은 화소 비율(살아남은/유효 깊이 화소) 분포', scientific_verdict=None))
    L = ['# t4_A_fusion', '', '4.1절. 방법 A(COLMAP stereo_fusion 기본값). 영상마다 살아남은 화소 비율 = 살아남은 화소 / 유효 깊이 화소. 실제 값은 fusion.log 에서 읽음.', '', 'scientific_verdict: null', '',
         '| 작업 공간 | 융합 점 | 영상(깊이 있음) | 살아남은 화소 / 유효 | 영상마다 비율 최소·10·25·50·75·90 %·최대 / 평균 |', '|---|---|---|---|---|']
    for r in rows:
        L.append(f"| {r['workspace']} | {r['fused_points']:,} | {r['images']} ({r['images_with_depth']}) | {r['pixels_survived']:,} / {r['pixels_valid']:,} ({r['survived_pct']:.1f} %) | "
                 + ' · '.join(f"{r[f'per_image_q{p}_pct']:.1f}" for p in [0, 10, 25, 50, 75, 90, 100]) + f" / {r['per_image_mean_pct']:.1f} |")
    L += ['', '실제로 쓰인 값(fusion.log):', '']
    for r in rows: L.append(f"- {r['workspace']}: " + ', '.join(f'{k} {v}' for k, v in r['used_options'].items()))
    (T_/'t4_A_fusion.md').write_text('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__': main(sys.argv[1:] or ['campus'])
