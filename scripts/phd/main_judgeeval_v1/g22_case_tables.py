"""덧붙임 2 2.5절(판단 다시 돌리지 않음, 이미 있는 패치 값으로 표만. 참값 h_I·정답은 갈래 나누기와 채점에만).
가 t6_image_case_v2: 정답 영상 -> 판 4 판정 두 자료(① 같다)와 정답 영상 -> ① 값 없음(② 사전 정보 / ③으로).
  ① '값 없음' 조건(judge_lib.py step1, 16~17줄): ok = (n >= 4) & isfinite(L) & isfinite(d), 아니면 값 없음. n = 본 길이(지붕 10 / 벽 5 m) 원통 안 영상 점 수, d = 그 점 평균 − 사전 정보 높이, L = 저장 한계 L_m = 1.96(√(u_M² + σ_P² + σ_W²) + |r|) (g4_step1.py 34줄 점검식). (ㄷ)은 어느 항이 없는지도 셈.
  까닭(코드 조건 차례로, 서로 겹치지 않게): (ㄱ) n < 4 이고 정답 영상 자리가 길이 안(|h_I| ≤ 반길이), (ㄴ) n < 4 이고 정답 영상 자리가 길이 밖(|h_I| > 반길이; 채점용 갈래),
  (ㄷ) n ≥ 4 인데 L 없음, (ㄹ) 그 밖(n ≥ 4, L 있음, d 없음).
나 t7_step3_catch: 정답 영상 틀림·정답 영상이 ③에 도착(① 다르다 -> ③, ① 값 없음 -> ② -> ③)한 넓이와 ③ 출력.
그림 fig_d6_sections: 가-1·가-2 에서 넓은 차례 둘씩(같은 넓이는 패치 번호 차례), 덧붙임 1 5절 단면과 같은 꼴.
사용: GT_STAGE=ga3 g22_case_tables.py"""
from common import *
import pandas as pd
import judge_lib as JL
import g8_score as G8
from g11_figs import save, load, section_pts
import matplotlib.pyplot as plt
A2 = json.loads((C/'judgeeval_v1_add2.json').read_text()); assert sha(C/'judgeeval_v1_add2.json') == json.loads((C/'judgeeval_v1_add2.lock.json').read_text())['config_sha256']
TD = D/'tables/마'; BINS = A2['step2_5']['bins_hI_m'] + [np.inf]; PL = '판 4'
def write(name, df, note=''):
    TD.mkdir(parents=True, exist_ok=True); df.to_csv(TD/f'{name}.csv', index=False)
    fm = lambda x: '' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:,.2f}' if isinstance(x, float) else (f'{x:,}' if isinstance(x, (int, np.integer)) and not isinstance(x, bool) else str(x)))
    L = ['| ' + ' | '.join(map(str, df.columns)) + ' |', '|' + '---|'*len(df.columns)] + ['| ' + ' | '.join(fm(x) for x in r) + ' |' for r in df.itertuples(index=False)]
    (TD/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(L) + '\n')
def med(x): return float(np.median(x)) if len(x) else np.nan
def bins(r, w, m, a, pre=''):
    for lo, hi in zip(BINS[:-1], BINS[1:]): r[f'{pre}|h_I| {lo:g}~{hi:g} m' if np.isfinite(hi) else f'{pre}|h_I| > {lo:g} m'] = w[m & (a >= lo) & (a < hi)].sum()
def main():
    c = cfg(); T = Timer(); r6 = []; r7 = []; chk = dict(at=now(), scientific_verdict=None); picks = []
    for prior in PRIORS:
        d = G8.Data(prior, c); F = loadz(O/'work'/STAGE/f'judge4_v2_{prior}.npz'); assert np.array_equal(F['patch_index'], d.idx)
        j4 = F[f'J4_{PL}']; st = F[f'stage_{PL}']; ok = F[f'ok_{PL}']; r1 = d.r1(); r2 = d.r2(); S1 = d.S1; S3 = d.S3
        hI = np.abs(loadz(O/'work'/STAGE/f'truth_{prior}.npz', ['h_I'])['h_I'][:, 0]); n = S1['n'][:, 2]; dd = S1['d_mean'][:, 2]; L = S1['L_m']; H = S1['Hs'][:, 2]
        # 코드 조건 그대로 다시 내어 맞댐
        okc = (n >= 4) & np.isfinite(L) & np.isfinite(dd); assert np.array_equal(okc, r1 != JL.NONE), 'none condition replay differs'
        why = np.full(len(n), 3, np.int8); why[(n < 4) & (hI <= H)] = 0; why[(n < 4) & ~(hI <= H)] = 1; why[(n >= 4) & ~np.isfinite(L)] = 2
        mx = pd.read_csv(TD/'t1_matrix4_v2.csv'); mx = mx[(mx.plan == PL) & (mx.prior == PN[prior])]
        for sn, sm in G8.surfaces(d):
            for (vn, vm), (un, w) in [(v, u) for v, u in G8.UV(d)] + [((vn_, vm_), ('패치', np.ones(len(d.t)))) for vn_, vm_ in G8.versions(d)]:
                if un == '점': continue
                m = sm & vm & (d.t == 1)
                # 가-1
                g = m & (j4 == 0); r = dict(part='가-1 정답 영상 -> 두 자료(① 같다)', prior=PN[prior], surface=sn, version=vn, unit=un, total=w[g].sum()); bins(r, w, g, hI)
                r.update({'|d| 중앙값 m': med(np.abs(dd[g])), 'L 중앙값 m': med(L[g]), '|h_I| 중앙값 m': med(hI[g]), '(가) |h_I| ≤ L': w[g & (hI <= L)].sum(), '(나) |h_I| > L, |d| ≤ L': w[g & (hI > L) & (np.abs(dd) <= L)].sum(),
                          '그 밖': w[g & (hI > L) & ~(np.abs(dd) <= L)].sum(), 'v2 목표 맞음 %': 100*w[g & ok].sum()/w[g].sum() if w[g].sum() else np.nan,
                          '(가) 목표 맞음 %': 100*w[g & (hI <= L) & ok].sum()/w[g & (hI <= L)].sum() if w[g & (hI <= L)].sum() else np.nan, '(나) 목표 맞음 %': 100*w[g & (hI > L) & ok].sum()/w[g & (hI > L)].sum() if w[g & (hI > L)].sum() else np.nan})
                assert np.isclose(r['(가) |h_I| ≤ L'] + r['(나) |h_I| > L, |d| ≤ L'] + r['그 밖'], r['total']); r6.append(r)
                if un == '넓이':
                    mc = mx[(mx.surface == sn) & (mx.version == vn) & (mx.unit == '넓이') & (mx.truth == '영상')]
                    assert np.isclose(float(mc['두 자료'].iloc[0]), r['total']), ('가-1 cell', sn, vn)
                # 가-2
                for after, gm in [('② 사전 정보', r2 == 0), ('② -> ③', r2 == 1), ('모두', np.ones(len(r2), bool))]:
                    g = m & (r1 == JL.NONE) & gm; r = dict(part=f'가-2 정답 영상 -> ① 값 없음 ({after})', prior=PN[prior], surface=sn, version=vn, unit=un, total=w[g].sum())
                    names = ['(ㄱ) n<4, 정답 자리 길이 안', '(ㄴ) n<4, 정답 자리 길이 밖', '(ㄷ) n≥4, L 없음', '(ㄹ) 그 밖']
                    for k, nm in enumerate(names):
                        gg = g & (why == k); r[nm] = w[gg].sum(); r[f'{nm[:3]} n 중앙값'] = med(n[gg]); r[f'{nm[:3]} |h_I| 중앙값 m'] = med(hI[gg])
                    gL = g & (why == 2)
                    for tk in ['u_M', 'sigma_P', 'sigma_W', 'r_m']: r[f'(ㄷ) 중 {tk} 없음'] = w[gL & ~np.isfinite(S1[tk])].sum()
                    r['(ㄱ)+(ㄴ) 중 n = 0'] = w[g & (n == 0)].sum(); r['v2 목표 맞음 %'] = 100*w[g & ok].sum()/w[g].sum() if w[g].sum() else np.nan
                    assert np.isclose(sum(r[x] for x in names), r['total']); r6.append(r)
                # 나
                for tn, tv in [('영상 틀림', 2), ('영상', 1)]:
                    mt = sm & vm & (d.t == tv)
                    for path, pm in [('① 다르다 -> ③', r1 == JL.DIFF), ('① 값 없음 -> ② -> ③', (r1 == JL.NONE) & (r2 == 1)), ('모두', st == 3)]:
                        g = mt & pm & (st == 3); tot = w[g].sum(); cons = np.where(r1 == JL.DIFF, S3['from1_cons'], S3['from2_cons'])
                        r = dict(truth=tn, path=path, prior=PN[prior], surface=sn, version=vn, unit=un, arrived=tot, step3_prior=w[g & (j4 == 3)].sum(), step3_image=w[g & (j4 == 1)].sum())
                        r['③ 사전 정보 %'] = 100*r['step3_prior']/tot if tot else np.nan; r['③ 영상 %'] = 100*r['step3_image']/tot if tot else np.nan
                        if tv == 2:
                            gi = g & (j4 == 1); bins(r, w, gi, hI, '③ 영상 낸 것: '); r['③ 영상 낸 것: 일관된 점 중앙값'] = med(cons[gi]); r['③ 사전 정보 낸 것: 일관된 점 중앙값'] = med(cons[g & (j4 == 3)])
                        r7.append(r)
                        if path == '모두' and un == '넓이':
                            mc = mx[(mx.surface == sn) & (mx.version == vn) & (mx.unit == '넓이') & (mx.truth == ('사전 정보·영상 틀림' if tv == 2 else '영상'))]
                            assert np.isclose(float(mc['영상'].iloc[0]) + float(mc['사전 정보·영상 틀림'].iloc[0]), tot), ('나 arrival', tn, sn, vn)
        if prior == 'LoD2':
            for part, g in [('가-1 정답 영상 -> 두 자료', (d.t == 1) & (j4 == 0) & (d.kind == 1)), ('가-2 정답 영상 -> ① 값 없음', (d.t == 1) & (r1 == JL.NONE) & (d.kind == 1))]:
                ii = np.flatnonzero(g); ii = ii[np.lexsort((ii, -d.area[ii]))][:2]; picks += [(part, int(k)) for k in ii]
            ext = dict(n=n, d=dd, L=L, why=why, j4=j4, st=st, ok=ok, hT=F[f'hT_{PL}'], r2=r2)
    write('t6_image_case_v2', pd.DataFrame(r6), '2.5 가: 정답 영상이 다른 판정으로 간 까닭(판 4). 넓이 m² 또는 패치 수. ① 값 없음 조건은 judge_lib.py step1 16~17줄 그대로, (ㄴ)은 참값으로만 가른 채점용 갈래. 목표 맞음은 v2')
    write('t7_step3_catch', pd.DataFrame(r7), '2.5 나: ③에 도착한 정답 영상 틀림·정답 영상 패치와 ③ 출력(판 4). ③ 도착 넓이 = 4 × 4 행렬 그 줄의 영상 + 사전 정보·영상 틀림 칸 합(점검 통과)')
    chk.update(none_condition_replay=True, reason_sum=True, arrival_equals_matrix=True, seconds=T.s()); dump(TD/'checks_2_5.json', chk)
    # 그림
    L_ = load('LoD2'); Z = loadz(O/'work'/STAGE/'truth_LoD2.npz', ['h_I', 'tau_P', 'tau_I']); WN = ['(ㄱ) n<4·길이 안', '(ㄴ) n<4·길이 밖', '(ㄷ) L 없음', '(ㄹ) 그 밖']
    fig, axs = plt.subplots(1, 4, figsize=(16, 5)); meta = []
    for ax, (part, k) in zip(axs, picks):
        ref, nn, u, v, P = section_pts(L_, k, 1.5, 10.); a, t, _, _ = P['mvs']; ax.scatter(a, t, s=1, color='#97C459', lw=0, label='영상 깊이 점'); a, t, _, _ = P['gt']; ax.scatter(a, t, s=1.4, color='k', lw=0, label='드론 LiDAR')
        hI = Z['h_I'][k, 0]; tp = Z['tau_P'][k, 0]; ti = Z['tau_I'][k, 0]; dk = ext['d'][k]; Lk = ext['L'][k]; hT = ext['hT'][k]
        ax.axhspan(-tp, tp, color='#AFA9EC', alpha=.4, label='0 ± τ_P'); ax.axhspan(hI - ti, hI + ti, color='#97C459', alpha=.35, label='h_I ± τ_I (정답 영상 자리)')
        if np.isfinite(dk) and np.isfinite(Lk): ax.axhspan(dk - Lk, dk + Lk, xmin=0, xmax=.08, color='#D85A30', alpha=.5, label='① d ± L (왼쪽 띠)'); ax.axhline(dk, color='#D85A30', lw=.8, ls=':', label=f'① d {dk:+.2f}')
        if np.isfinite(hT): ax.axhline(hT, color='#185FA5', lw=1.2, label=f'목표 h_T v2 {hT:+.2f}')
        ax.axhline(0, color='#534AB7', lw=1); ax.axvline(-.125, color='#5F5E5A', lw=.4, ls='--'); ax.axvline(.125, color='#5F5E5A', lw=.4, ls='--')
        ys = [0, hI] + ([dk - Lk, dk + Lk] if np.isfinite(dk) and np.isfinite(Lk) else []); ax.set_ylim(min(ys) - 1, max(ys) + 1); ax.set_xlim(-1.5, 1.5); ax.set_xlabel('옆 거리 (m)'); ax.set_ylabel('법선 거리 (m, 사전 정보 = 0)')
        extra = f"L {Lk:.2f}" if part.startswith('가-1') else f"{WN[ext['why'][k]]} · ② {'③으로' if ext['r2'][k] == 1 else '사전 정보'}"
        ax.set_title(f"{part}\n{L_['b'][k].replace('DEBY_LOD2_', '')} · |h_I| {abs(hI):.2f} · n {int(ext['n'][k])} · {extra} · 목표 {'맞음' if ext['ok'][k] else '틀림'}", fontsize=6.5); ax.legend(fontsize=5, loc='upper right')
        meta.append(dict(part=part, patch_index=int(L_['i'][k]), h_I=float(hI), n=int(ext['n'][k]), d=float(dk), L=float(Lk), h_T_v2=float(hT), target_ok=bool(ext['ok'][k])))
    fig.suptitle('2.5 가 본보기(LoD2 지붕, 넓은 차례 둘씩, 단면 옆 ±1.5 m, 두께 ±0.125 m)', fontsize=8); fig.tight_layout(); save(fig, 'fig_d6_sections', dict(examples=meta))
    progress(f'덧붙임 2 2.5절 표 t6·t7, 그림 d6: {T.s():.0f} s'); print(json.dumps(jsafe(chk), ensure_ascii=False))
if __name__ == '__main__': main()
