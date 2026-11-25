"""PHD-MAIN-JUDGEVIDEO-v1 area table and check (CPU). judge_steps_B173_ALS.csv: per step the patches newly decided (count, area) and the cumulative area
share of each category after the step (the categories the video paints, jv_frames.stage_colours). Check: the result-scene areas per category = a direct
recount from the MVSFILTER patch table (patches4_ALS.csv.gz read again, rows = the scene patch_index list, category from its own columns), and the
'그 밖 판정' patches broken down by stored judgment and JUDGECHECK-v2 j_reason. scientific_verdict: null"""
import sys, json
sys.path.insert(0, '/repo/scripts/phd/main_judgevideo_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
import numpy as np, pandas as pd
from common import loadz, dump, now, sha
from pathlib import Path
import importlib.util
OUT = Path('/out'); JD = Path('/jdocs')
STAGES = ['j1', 'j2', 'j3', 'j4', 'res']; SNAME = {'j1': '① 영상 깊이 유무', 'j2': '② 변화 탐지', 'j3': '③ 영상 따름', 'j4': '④ 영상 점검', 'res': '판단 결과'}
SN = {1: '결측', 11: '제거(시선 검사)', 2: '일치', 3: '작은 차이(일치 목표)', 31: '영상 따름', 4: '되돌림(영상 점검)', 5: '그 밖(L 없음)', 0: '아직 안 정함'}
ORDER = [1, 11, 2, 3, 31, 4, 5, 0]
def stage_colours(step, stage):   # same rule as jv_frames.stage_colours (copied to avoid importing the drawing module)
    k = STAGES.index(stage); c = np.zeros(len(step), int)
    c[np.isin(step, [1, 11])] = step[np.isin(step, [1, 11])]
    if k >= 1: c[step == 2] = 2
    if k >= 2: c[step == 3] = 3; c[np.isin(step, [31, 4])] = 31
    if k >= 3: c[step == 4] = 4
    if k >= 4: c[step == 0] = 5
    return c
p = loadz(OUT/'scene_patches_ALS.npz'); A = p['area']; At = A.sum(); rows = []; prev = np.zeros(len(A), int)
for st in STAGES:
    c = stage_colours(p['step'], st); newm = (c != prev)
    r = dict(step=SNAME[st], new_patches=int(newm.sum()), new_area_m2=round(float(A[newm].sum()), 2))
    for k in ORDER: r[f'{SN[k]}_누적_%'] = round(100*float(A[c == k].sum())/At, 3)
    for k in ORDER: r[f'{SN[k]}_누적_m2'] = round(float(A[c == k].sum()), 2)
    rows.append(r); prev = c
df = pd.DataFrame(rows); df.to_csv(OUT/'judge_steps_B173_ALS.csv', index=False); df.to_csv(JD/'judge_steps_B173_ALS.csv', index=False)
# check: direct recount from the patch table
t = pd.read_csv('/art/phase-payloads/phd/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1/judge/patches4_ALS.csv.gz', usecols=['patch_index', 'patch_id', 'area', 'none_n', 'none_judgment', 'none_significant', 'mix_large', 'combo_D_returned', 'combo_D_judgment'])
t = t.set_index('patch_index').loc[p['patch_index']]; assert (t['patch_id'].values == p['patch_id']).all()
sig = t['none_significant'].astype(bool).values; j0 = t['none_judgment'].values; mix = pd.to_numeric(t['mix_large'], errors='coerce').values; ret = t['combo_D_returned'].astype(bool).values; n = t['none_n'].values
direct = {'결측': (~sig) & (n < 4) & (j0 != 3), '제거(시선 검사)': (~sig) & (j0 == 3), '일치': (~sig) & (j0 == 0) & (n >= 4), '작은 차이(일치 목표)': sig & (mix == 0),
          '영상 따름': sig & (mix == 1) & ~ret, '되돌림(영상 점검)': sig & (mix == 1) & ret}
direct['그 밖(L 없음)'] = ~np.any(np.stack(list(direct.values())), 0)
res = rows[-1]; ck = []
for k, m in direct.items():
    a = float(t['area'].values[m].sum()); ck.append(dict(category=k, video_m2=res[f'{k}_누적_m2'], direct_m2=round(a, 2), patches=int(m.sum()), equal=bool(abs(a-res[f'{k}_누적_m2']) < .01)))
jp = loadz('/art/phase-payloads/phd/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1/patch_ALS.npz', ['j_reason', 'j_region', 'geometry', 'L_m', 'n'])
om = direct['그 밖(L 없음)']; ii = p['patch_index'][om]
other = pd.DataFrame(dict(stored_judgment=t['combo_D_judgment'].values[om], j_reason=[str(v.tolist()) for v in jp['j_reason'][ii]], geometry=[str(np.ravel(v).tolist()) for v in jp['geometry'][ii]], L_finite=np.isfinite(jp['L_m'][ii]), area=t['area'].values[om]))
ob = other.groupby(['stored_judgment', 'j_reason', 'geometry', 'L_finite'])['area'].agg(['count', 'sum']).reset_index()
rec = dict(at=now(), rule=__doc__, total_area_m2=float(At), patches=int(len(A)), check_result_vs_direct=ck, all_equal=all(c['equal'] for c in ck), other_breakdown=json.loads(ob.to_json(orient='records', force_ascii=False)), scientific_verdict=None)
dump(OUT/'judge_steps_check.json', rec); dump(JD/'judge_steps_check.json', rec)
print(df.iloc[:, :3].to_string()); print(json.dumps(ck, ensure_ascii=False)); print(ob.to_string())
