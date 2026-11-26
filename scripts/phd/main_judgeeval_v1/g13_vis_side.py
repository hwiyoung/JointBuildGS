"""덧붙임 1 4절(이어서): ② 화소 표를 카메라 쪽(패치 법선 앞·뒤)으로 나눠 셈(judgevis2 visside, 분류는 judgevis 그대로), 4.5 놓친 변화의 방향, fig7_2 다시 그림.
- 점검: 앞 + 뒤 = step2 의 δ 1 % 화소 수(패치마다 같아야 함).
- 참고(채택 아님): 앞쪽 카메라 화소만으로 같은 화소 규칙을 썼을 때 ② 결과 넓이. 판단 규칙·값은 바꾸지 않는다.
- 4.5: 정답 영상인데 ①이 값 없음이고 ②가 사전 정보로 끝낸 넓이를 h_I 부호로 나눔(h_I < 0 = 면이 내려간 변화(벽은 법선 반대쪽, 곧 안쪽), > 0 = 올라간 변화(벽은 바깥쪽)).
- 그림 fig7_2_examples_v2: 끝점의 법선 거리를 '카메라 쪽 = 위'로 다시 그림(카메라마다 쪽이 달라 한 단면에 섞이면 뒤집혀 보임), 앞쪽 카메라 ●, 뒤쪽 카메라 ×.
사용: GT_STAGE=ga3 g13_vis_side.py"""
from common import *
import pandas as pd
import judge_lib as JL
from g11_figs import cams, read_depth, load, CLS, section_pts, save
from g12_vis_check import write
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
VB2 = O/'bin/judgevis2'
def build2():
    src = HERE/'judgevis2.cpp'; j = VB2.parent/'judgevis2.build.json'
    if VB2.exists() and j.exists() and json.loads(j.read_text())['source_sha256'] == sha(src) + sha(HERE/'judgevis.cpp'): return
    tmp = VB2.with_name('judgevis2.new'); subprocess.run(['g++', '-O3', '-fopenmp', '-std=c++17', '-Wall', '-I', str(HERE), str(src), '-o', str(tmp)], check=True); os.replace(tmp, VB2)
    dump(j, dict(at=now(), source_sha256=sha(src) + sha(HERE/'judgevis.cpp'), binary_sha256=sha(VB2)))
def main():
    c = cfg(); build2(); T = Timer(); rows = []; rows45 = []; rec = {}
    for prior in PRIORS:
        dest = O/'work'/STAGE/f'step2side_{prior}.npz'; S2 = loadz(O/'work'/STAGE/f'step2_{prior}.npz')
        if not dest.exists():
            P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'tangent1', 'prior_height_m']); ids = S2['patch_index']; n = P['normal'][ids]; ph = P['prior_height_m'][ids]; good = S2['good']; g = np.flatnonzero(good)
            s = P['centre'][ids] + np.nan_to_num(ph)[:, None]*np.nan_to_num(n); u = P['tangent1'][ids] - np.einsum('ij,ij->i', P['tangent1'][ids], np.nan_to_num(n))[:, None]*np.nan_to_num(n)
            un = np.linalg.norm(u, axis=1); u = u/np.where(un > 1e-9, un, 1)[:, None]; pb = O/'tmp'/f'vs_{prior}.bin'; ob = O/'tmp'/f'vs_{prior}.out'
            np.ascontiguousarray(np.c_[s, n, u, np.full(len(ids), c['truth']['column']['cell_half_m'][0])][g], '<f8').tofile(pb)   # g5_step2 과 같은 패치 줄
            subprocess.run([str(VB2), 'visside', str(VIS/'cams.bin'), str(VIS/'maps.txt'), str(pb), str(len(g)), str(ob)], check=True, env=dict(os.environ, OMP_NUM_THREADS='30'), stderr=subprocess.DEVNULL)
            out = np.full((len(ids), 8), np.nan); out[g] = np.fromfile(ob, '<f8').reshape(-1, 8); pb.unlink(); ob.unlink(); savez(dest, patch_index=ids, side=out)
        V = loadz(dest)['side']; C2 = S2['counts']; ok = np.isfinite(C2[:, 0]); same = bool(np.array_equal(V[ok][:, 0:4] + V[ok][:, 4:8], C2[ok][:, 0:4]))
        Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz'); assert np.array_equal(Z['patch_index'], S2['patch_index']); t = Z['answer'][:, 0]; hI = Z['h_I'][:, 0]
        J = loadz(O/'work'/STAGE/f'judgments_{prior}.npz'); r1 = J['r1']; r2 = J['r2']; Pk = loadz(inp('patches', prior=prior), ['kind', 'area']); kind = Pk['kind'][S2['patch_index']]; area = Pk['area'][S2['patch_index']]
        none = r1 == 2; f = V[:, 0:4]; b = V[:, 4:8]; go_front = np.where(np.nan_to_num((f[:, 1] > f[:, 2] + f[:, 3]) & (f[:, 1:4].sum(1) > 0)).astype(bool), 1, 0)
        for sn, sm in [('지붕', kind == 1), ('벽', kind == 2)]:
            if not sm.any(): continue
            for ti in [0, 1, 2, 3, 4]:
                m = none & sm & (t == ti)
                if not m.any(): continue
                fs = np.nansum(f[m], 0); bs = np.nansum(b[m], 0); tot = fs[1:].sum() + bs[1:].sum()
                rows.append(dict(prior=PN[prior], surface=sn, truth=FWD[ti], area_m2=area[m].sum(), patches=int(m.sum()), **{f'앞 {CLS[k][0]} %': 100*fs[k]/max(tot, 1) for k in [1, 2, 3]}, **{f'뒤 {CLS[k][0]} %': 100*bs[k]/max(tot, 1) for k in [1, 2, 3]},
                                 **{'뒤쪽 카메라 표 비율 %': 100*bs[1:].sum()/max(tot, 1), '② 본 판 ③으로 m²': area[m & (r2 == 1)].sum(), '참고: 앞쪽만 ③으로 m²': area[m & (go_front == 1)].sum()}))
            m = none & sm & (t == 1) & (r2 == 0)
            rows45.append(dict(prior=PN[prior], surface=sn, 정답영상_1값없음_m2=area[none & sm & (t == 1)].sum(), 그가운데_2사전정보_m2=area[m].sum(), 면이_내려간_변화_m2=area[m & (hI < 0)].sum(), 면이_올라간_변화_m2=area[m & (hI > 0)].sum(),
                               내려간_비율_pct=100*area[m & (hI < 0)].sum()/max(area[m].sum(), 1e-12), 참고_앞쪽만이면_3으로_m2=area[m & (go_front == 1)].sum()))
        rec[prior] = dict(front_plus_back_equals_step2=same, patches_checked=int(ok.sum()))
    write('t4_4_side_share', pd.DataFrame(rows), '② 화소 표를 카메라 쪽으로 나눔(①에서 값 없는 패치, δ 1 %, 못 봄 뺀 표 = 100 %). 뒤 = 카메라가 패치 법선 반대쪽(벽이면 건물 안쪽 반공간). 마지막 열은 참고(채택 아님): 앞쪽 카메라 화소만으로 같은 규칙')
    write('t4_5_missed_change', pd.DataFrame(rows45), '4.5 정답 영상인데 ①이 값 없음, ②가 사전 정보로 끝낸 넓이: h_I 부호로 나눔. 지붕: 내려간 = 참값이 사전 정보 면 아래. 벽: 내려간 = 법선 반대쪽(건물 안쪽)')
    fig2v2(); rec.update(at=now(), seconds=T.s(), scientific_verdict=None); dump(O/'work'/STAGE/'vis_side.json', rec); progress(f'4절 카메라 쪽 나눔·4.5·fig7_2 v2: {rec}'); print(rec)
def fig2v2():
    C_, W, H = cams(); maps = [l.split('\t')[0] for l in (VIS/'maps.txt').read_text().splitlines()]; L = load('LoD2'); meta0 = json.loads((D/'figures/fig7_2_examples.json').read_text())['examples']
    pos = {int(x): k for k, x in enumerate(L['i'])}; exs = [(e['truth'], pos[e['patch_index']]) for e in meta0]; cache = {}
    fig, axs = plt.subplots(2, len(exs), figsize=(3.4*len(exs), 7.6)); fig.subplots_adjust(hspace=.42); meta = []
    for j, (tn, k) in enumerate(exs):
        ref, n, u, v, P = section_pts(L, k, 3., 6.); cnt = {s: {x: 0 for x in range(4)} for s in ['앞', '뒤']}
        for row, sname in enumerate(['앞', '뒤']):
            ax = axs[row, j]; a, t, _, _ = P['mvs']; sg = 1 if sname == '앞' else -1
            ax.scatter(a, sg*t, s=.6, color='#97C459', lw=0); a, t, _, _ = P['gt']; ax.scatter(a, sg*t, s=1, color='k', lw=0); ax.axhline(0, color='#534AB7', lw=1)
            for im in range(len(C_)):
                Rm = C_[im, :9].reshape(3, 3); tt = C_[im, 9:12]; Y = Rm@ref + tt
                if Y[2] <= .05: continue
                uu = C_[im, 12]*Y[0]/Y[2] + C_[im, 14]; vv = C_[im, 13]*Y[1]/Y[2] + C_[im, 15]; cu, cv = int(round(uu)), int(round(vv))
                if not (0 <= cu < W and 0 <= cv < H): continue
                cc = -Rm.T@tt; side = '앞' if (cc - ref)@n > 0 else '뒤'
                if side != sname: continue
                if im not in cache: cache[im] = read_depth(maps[im])
                Dd = float(cache[im][cv, cu]); Z = Y[2]; cl = 0 if not Dd > 0 else (1 if Dd > 1.01*Z else (2 if Dd < .99*Z else 3)); cnt[side][cl] += 1
                if Dd > 0:
                    dr = ref - cc; dr /= np.linalg.norm(dr); e = cc + dr*Dd*np.linalg.norm(ref - cc)/Z - ref; ax.scatter([e@u], [sg*(e@n)], s=7, color=CLS[cl][1], lw=0, zorder=5)
            ax.set_xlim(-3, 3); ax.set_ylim(-6, 6); ax.text(.02, .97, '카메라 쪽 ↑', transform=ax.transAxes, fontsize=6, va='top', color='#5F5E5A')
            ax.set_title(f"정답 {tn} · {KN[int(L['kind'][k])]} · {sname}쪽 카메라 {sum(cnt[sname].values())}장" if row == 0 else f"{sname}쪽 카메라 {sum(cnt[sname].values())}장(건물 안쪽 반공간)", fontsize=6.5)
            ax.text(0, -.12, ' · '.join(f'{CLS[x][0]} {cnt[sname][x]}' for x in range(4)), transform=ax.transAxes, fontsize=5.8, va='top')
        meta.append(dict(truth=tn, patch_index=int(L['i'][k]), counts={s: {CLS[x][0]: cnt[s][x] for x in range(4)} for s in cnt}))
    fig.legend(handles=[Line2D([], [], marker='o', ls='', color=v[1], label=f'시선 끝: {v[0]}') for v in CLS.values()], loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, -.03))
    fig.suptitle('② 가시성(다시 그림): 위 줄 = 패치 법선 앞쪽 카메라, 아래 줄 = 뒤쪽 카메라. 세로 = 법선 거리, 카메라 쪽을 위로 뒤집어 그림(아래 줄의 점·면은 위아래가 바뀜)', fontsize=7.5)
    save(fig, 'fig7_2_examples_v2', dict(examples=meta, note='fig7_2_examples(앞 판)는 그대로 둠. 앞 판은 카메라 쪽이 다른 영상의 끝점을 한 단면에 법선 기준으로 그려, 뒤쪽 카메라의 막힘 끝점이 면 아래에 찍혔다'))
if __name__ == '__main__': main()
