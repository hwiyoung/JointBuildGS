"""PHD-MAIN-JUDGEVIDEO-v1 prep (CPU, no training, no new judgment): the B173 scene patches of the ALS prior with their STORED values.
Inputs (read only):
  MVSFILTER-v1 bundle 나5 patch table judge/patches4_ALS.csv.gz (columns none_n, none_judgment, none_significant, d_m, L_m, mix_large, combo_D_returned, combo_D_judgment)
  JUDGEPROBE-v1 patch_ALS.npz (JUDGECHECK-v2 per-patch values, same row order; checked by patch order = patch_index) for centre, normal, tangent1, area,
  prior_height_m, mvs_mean_m, sigma_P, u_M (place of the patch and its heights).
Scene = TRAINLOG-v1 scope (trainlog_v1.json scope.buffered_footprint and z range) applied to the patch centre (derive_states.scope_mask).
Step of each patch (painting order of the video; the judgment itself is read, not recomputed):
  1 image depth present?   none_n < 4 -> missing (결측); none_judgment == 3 -> removed by the sight check (제거, grey hatch)
  2 change detection       not significant (none_significant False) with none_judgment == 0 -> agree (일치)
  3 follow the image       significant: mix_large == 0 -> small difference, agree target (작은 차이); mix_large == 1 -> image depth (영상 따름)
  4 image check            significant, mix_large == 1 and combo_D_returned == 1 -> returned to the prior (되돌림)
  anything else stays 'not decided' (아직 안 정함) and is counted.
Final judgment code (mix boundary panel, treatment W) = none_judgment, big & returned -> 1, small -> 0 (mf19 panel_lo); checked against combo_D_judgment
on the big patches. scientific_verdict: null"""
import sys, json
sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
import numpy as np, pandas as pd
from common import cfg, sha, dump, now, loadz, savez
from derive_states import scope_mask
from pathlib import Path
MF = Path('/art/phase-payloads/phd/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1/judge/patches4_ALS.csv.gz')
JP = Path('/art/phase-payloads/phd/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1/patch_ALS.npz')
OUT = Path('/out'); JD = Path('/jdocs')
COLS = ['patch_index', 'patch_id', 'kind', 'area', 'none_n', 'none_judgment', 'none_significant', 'region', 'building', 'd_m', 'L_m', 'mix_large', 'combo_D_returned', 'combo_D_judgment']
STEPN = {0: '아직 안 정함', 1: '① 결측', 11: '① 제거(시선 검사)', 2: '② 일치', 3: '③ 작은 차이(일치 목표)', 31: '③ 영상 따름', 4: '④ 되돌림(영상 점검)'}
def main():
    c = cfg(); t = pd.read_csv(MF, usecols=COLS); z = loadz(JP, ['centre', 'normal', 'tangent1', 'area', 'prior_height_m', 'mvs_mean_m', 'sigma_P', 'u_M', 'd_m', 'L_m', 'n', 'kind'])
    assert len(t) == len(z['area']) and np.array_equal(t['patch_index'].values, np.arange(len(t)))
    P = z['centre'].astype(float); sel = scope_mask(P, c); ix = np.flatnonzero(sel); s = t.iloc[ix].reset_index(drop=True)
    ck = dict(rows_table=len(t), scene_patches=int(len(ix)), area_equal=bool(np.allclose(s['area'].values, z['area'][ix])), n_equal=bool(np.array_equal(s['none_n'].values, z['n'][ix])),
              d_equal_or_both_nan=bool(np.all(np.isclose(s['d_m'].values, z['d_m'][ix], equal_nan=True))), L_equal_or_both_nan=bool(np.all(np.isclose(s['L_m'].values, z['L_m'][ix], equal_nan=True))))
    n = s['none_n'].values; j0 = s['none_judgment'].values.astype(int); sig = s['none_significant'].astype(bool).values
    mix = pd.to_numeric(s['mix_large'], errors='coerce').values; ret = s['combo_D_returned'].values.astype(bool)
    step = np.zeros(len(s), int)
    step[(~sig) & (n < 4)] = 1; step[(~sig) & (j0 == 3)] = 11; step[(~sig) & (j0 == 0) & (step == 0)] = 2
    step[sig & (mix == 0)] = 3; step[sig & (mix == 1)] = 31; step[sig & (mix == 1) & ret] = 4
    fin = j0.copy(); fin[sig & (mix == 1) & ret] = 1; fin[sig & (mix == 0)] = 0
    JN = {'일치': 0, '사전정보 사용': 1, '영상 깊이 사용': 2, '제거': 3, '결측': 4, '미판정': 9}; cd = s['combo_D_judgment'].map(JN).values
    big = sig & (mix == 1); ck['final_equals_combo_D_on_big'] = bool(np.array_equal(fin[big], cd[big])); ck['final_equals_combo_D_outside_sig'] = bool(np.array_equal(fin[~sig], cd[~sig]))
    xt = pd.crosstab([pd.Series(sig, name='significant'), pd.Series(j0, name='none_judgment')], pd.Series([STEPN[v] for v in step], name='step'), values=s['area'], aggfunc='sum').fillna(0).round(2)
    ck['crosstab_area_m2'] = json.loads(xt.to_json()); ck['n_lt4_by_judgment'] = {str(k): int(v) for k, v in pd.Series(j0[n < 4]).value_counts().items()}
    ck['sig_mix_missing'] = int((sig & ~np.isfinite(mix)).sum()); ck['not_decided_patches'] = int((step == 0).sum()); ck['not_decided_by_judgment'] = {str(k): int(v) for k, v in pd.Series(j0[step == 0]).value_counts().items()}
    # drawing heights: patch on the prior surface; image-depth point; target height of the final judgment (agree = precision-weighted mean, jc2 region-0 rule)
    hP = z['prior_height_m'][ix].astype(float); hM = z['mvs_mean_m'][ix].astype(float); sP = z['sigma_P'][ix].astype(float); uM = z['u_M'][ix].astype(float)
    with np.errstate(invalid='ignore', divide='ignore'): wavg = (hP/sP**2 + hM/uM**2)/(1/sP**2 + 1/uM**2)
    tgt = np.where(fin == 2, hM, np.where(fin == 0, np.where(np.isfinite(wavg), wavg, hP), hP))
    savez(OUT/'scene_patches_ALS.npz', patch_index=ix, patch_id=np.array(s['patch_id'].astype(str).tolist()), step=step, final=fin, area=s['area'].values.astype(float), centre=P[ix], normal=z['normal'][ix], tangent1=z['tangent1'][ix],
          prior_h=hP, mvs_h=hM, target_h=tgt, L=s['L_m'].values.astype(float), d=s['d_m'].values.astype(float), n=n.astype(int), sig=sig.astype(bool), mix=mix.astype(float), ret=ret.astype(bool))
    rec = dict(at=now(), rule=__doc__, inputs={str(MF): sha(MF), str(JP): sha(JP)}, checks=ck, scientific_verdict=None); dump(OUT/'scene_patches_ALS.json', rec)
    print(json.dumps(ck, ensure_ascii=False, indent=1)[:4000])
main()
