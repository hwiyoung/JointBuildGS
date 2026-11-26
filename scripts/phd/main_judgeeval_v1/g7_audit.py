"""4절 이름표 점검 그림(가3 정답). 뽑기 = 가2 규칙(사전 정보마다 정답 여섯 x 20, 씨앗 고정, 한 건물 5개까지(정답 종류 안), 지붕·벽은 넓이 비율, 모자라면 있는 만큼).
번호는 정답을 감춤(L-001, A-001…), 사전 정보 안 칸을 섞어 쪽(10칸 = 2 x 5)에 나눔. 칸마다 그림 둘:
  왼쪽 = 단면(옆 ±3 m, 두께 ±0.125 m): 드론 LiDAR(검정, 조금 크게, 아래) 위에 영상 깊이 점(연한 초록, 위), 사전 정보 면(보라), 0 ± τ_P·h_I ± τ_I 띠, 점선 = 패치 칸.
  오른쪽 = 패치 기둥만(옆 ±0.125 m, 세로 = 기둥 안 점의 범위): 점 하나하나, 영상(초록)·참값(검정)을 옆으로 조금 비켜 그림.
칸 아래: 건물, 자리, 지붕·벽, τ_P, τ_I, 기둥 안 영상 점, 기둥 안 참값 점, 0 ± τ_P 참값, h_I ± τ_I 참값, two_layer. 정답 이름 없음.
나오는 것: docs/audit/가/page_{L,A}_NN.png(+json), audit_sheet.csv, audit_key.csv, audit_sampling.json. 사용: GT_STAGE=ga3 g7_audit.py"""
from common import *
import pandas as pd
from scipy.spatial import cKDTree
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Patch
for f in ['/fonts/NotoSansCJK-Regular.ttc', '/fonts/NotoSansCJK-Bold.ttc']: fm.fontManager.addfont(f)
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'font.size': 6, 'axes.linewidth': .5})
AD = D/'audit/가'; ABBR = {'LoD2': 'L', 'ALS': 'A'}
def sample(f, A_, rng):
    out = []; notes = []
    for a in FWD:
        g = f[f.answer == a]
        if not len(g): notes.append(dict(answer=a, wanted=A_['per_answer'], got=0)); continue
        Ar = g.groupby('surface').area_m2.sum()
        want = {Ar.index[0]: A_['per_answer']} if len(Ar) == 1 else (lambda r: {'지붕': r, '벽': A_['per_answer'] - r})(int(round(A_['per_answer']*Ar.get('지붕', 0)/Ar.sum())))
        per = {}
        for s_, k in want.items():
            h = g[g.surface == s_]; taken = 0
            if k > 0:
                for i in rng.permutation(len(h)):
                    b = h.building.iloc[i]
                    if per.get(b, 0) >= A_['max_per_building']: continue
                    per[b] = per.get(b, 0) + 1; out.append(h.iloc[i]); taken += 1
                    if taken == k: break
            notes.append(dict(answer=a, surface=s_, wanted=k, got=taken, candidates=len(h)))
    return out, notes
def crop(t, kind, box):
    X = np.load(inp('image_points' if kind == 'mvs' else 'truth_points', tile=t), mmap_mode='r'); out = []
    for s in range(0, len(X), 20_000_000):
        q = np.asarray(X[s:s+20_000_000], np.float64); m = (q[:, 0] >= box[0]) & (q[:, 0] <= box[1]) & (q[:, 1] >= box[2]) & (q[:, 1] <= box[3]) & (q[:, 2] >= box[4]) & (q[:, 2] <= box[5]); out.append(q[m])
    return np.concatenate(out)
def main():
    c = cfg(); A_ = c['audit']; rng = np.random.default_rng(A_['seed']); AD.mkdir(parents=True, exist_ok=True); sheet = []; key = []; notes_all = []
    for prior in PRIORS:
        f = pd.read_csv(O/f'forward_{prior}_ga3.csv.gz'); rows, notes = sample(f, A_, rng); notes_all += [dict(prior=PN[prior], **n) for n in notes]
        rows = [rows[i] for i in rng.permutation(len(rows))]
        P = loadz(inp('patches', prior=prior), ['centre', 'normal', 'tangent1', 'prior_height_m', 'tile', 'tiles']); ok = np.isfinite(P['prior_height_m']) & np.isfinite(P['normal']).all(1)
        Ssurf = P['centre'][ok] + P['prior_height_m'][ok][:, None]*P['normal'][ok]; St = cKDTree(Ssurf); exs = []
        for k, r in enumerate(rows):
            i = int(r.patch_index); n = P['normal'][i]; u = P['tangent1'][i] - (P['tangent1'][i]@n)*n; u /= np.linalg.norm(u)
            exs.append(dict(label=f'{ABBR[prior]}-{k+1:03d}', ref=P['centre'][i] + P['prior_height_m'][i]*n, n=n, u=u, v=np.cross(n, u), H=5. if r.surface == '벽' else 10., tile=P['tiles'][P['tile'][i]], row=r))
        by = {}
        for e in exs: by.setdefault(e['tile'], []).append(e)
        for t, es in by.items():
            R = np.array([e['ref'] for e in es]); lo = R.min(0) - 11; hi = R.max(0) + 11; box = (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
            for kind in ['gt', 'mvs']:
                X = crop(t, kind, box); tr = cKDTree(X)
                for e in es: e[kind] = X[tr.query_ball_point(e['ref'], r=np.hypot(e['H'], 3.2))]
            for e in es: e['prior'] = Ssurf[St.query_ball_point(e['ref'], r=np.hypot(e['H'], 3.2))]
        for pg in range(0, len(exs), A_['cells_per_page']):
            part = exs[pg:pg+A_['cells_per_page']]; fig = plt.figure(figsize=(12.5, 7.4)); gs = fig.add_gridspec(2, 5, wspace=.38, hspace=.7)
            for j, e in enumerate(part):
                sub = gs[j // 5, j % 5].subgridspec(1, 2, width_ratios=[3, 1.15], wspace=.12); a1 = fig.add_subplot(sub[0]); a2 = fig.add_subplot(sub[1]); r = e['row']
                def loc(X, W):
                    d = X - e['ref']; t = d@e['n']; a = d@e['u']; b = d@e['v']; m = (np.abs(b) <= .125) & (np.abs(a) <= W) & (np.abs(t) <= e['H']); return a[m], t[m]
                hI = r.h_I_m; tp, ti = r.tau_P, r.tau_I
                am, tm = loc(e['mvs'], 3.0); ag, tg = loc(e['gt'], 3.0); ap, tpp = loc(e['prior'], 3.0)
                lo_ = min(0, hI if np.isfinite(hI) else 0) - 2; hi_ = max(0, hI if np.isfinite(hI) else 0) + 2; lo_ = max(lo_, -e['H']); hi_ = min(hi_, e['H'])
                for ax in [a1, a2]:
                    ax.add_patch(Rectangle((-.125, -tp), .25, 2*tp, color='#AFA9EC', alpha=.55, lw=0, zorder=1))
                    if np.isfinite(hI): ax.add_patch(Rectangle((-.125, hI - ti), .25, 2*ti, color='#97C459', alpha=.55, lw=0, zorder=1))
                a1.axvline(-.125, color='#5F5E5A', lw=.4, ls='--'); a1.axvline(.125, color='#5F5E5A', lw=.4, ls='--')
                a1.scatter(ap, tpp, s=2.2, color='#534AB7', lw=0, zorder=3); a1.scatter(ag, tg, s=1.6, color='k', lw=0, zorder=4); a1.scatter(am, tm, s=.6, color='#97C459', lw=0, zorder=5)   # 발주 4절: 영상 점을 참값 위에(참값은 조금 크게)
                a1.set_xlim(-3, 3); a1.set_ylim(lo_, hi_); a1.set_title(e['label'], fontsize=7, fontweight='bold', loc='left')
                cm = np.abs(am) <= .125; cg = np.abs(ag) <= .125; ys = np.r_[tm[cm], tg[cg], 0, hI if np.isfinite(hI) else 0]
                a2.scatter(am[cm] - .03, tm[cm], s=3, color='#3B6D11', lw=0, zorder=4); a2.scatter(ag[cg] + .03, tg[cg], s=3, color='k', lw=0, zorder=5)
                a2.axhline(0, color='#534AB7', lw=.6, ls=':'); a2.set_xlim(-.14, .14); a2.set_xticks([-.125, 0, .125]); a2.set_xticklabels(['', '', ''])
                yl, yh = ys.min() - .3, ys.max() + .3; a2.set_ylim(yl, yh); a2.set_title('기둥', fontsize=5.5, loc='left', color='#5F5E5A')
                for ax in [a1, a2]: ax.tick_params(labelsize=4.5, length=1.5, width=.4)
                nI = int(r.column_image_points) if np.isfinite(r.column_image_points) else 0; nG = int(r.gt_column) if np.isfinite(r.gt_column) else 0
                bI = int(r.gt_band_image) if np.isfinite(r.gt_band_image) and r.gt_band_image >= 0 else None
                a1.text(0, -.16, f"{r.building.replace('DEBY_LOD2_', '')} · {r.place} · {r.surface}\nτ_P {tp:.2f} · τ_I {ti:.2f} · two_layer {int(r.two_layer)}\n기둥: 영상 {nI} · 참값 {nG} · 0±τ_P 참값 {int(r.gt_band_prior)} · h_I±τ_I 참값 {'-' if bI is None else bI}",
                        transform=a1.transAxes, fontsize=4.6, va='top')
                sheet.append({'번호': e['label'], '사전 정보': PN[prior], '패치 번호': r.patch_id, '건물': r.building, '자리': r.place, '지붕·벽': r.surface, 'τ_P (m)': tp, 'τ_I (m)': ti, '쪽': f'{ABBR[prior]}-{pg//A_["cells_per_page"]+1:02d}', '보이는 것': '', '메모': ''})
                key.append({'번호': e['label'], '가3 정답': r.answer, '가2 정답': r.ga2_answer, 'h_I (m)': hI, '0±τ_P 참값': r.gt_band_prior, 'h_I±τ_I 참값': r.gt_band_image, '기둥 안 참값': r.gt_column, 'two_layer': r.two_layer})
            hd = [Patch(color='k', label='드론 LiDAR'), Patch(color='#534AB7', label='사전 정보 면'), Patch(color='#97C459', label='영상 깊이 점'), Patch(color='#AFA9EC', label='0 ± τ_P'), Patch(color='#97C459', alpha=.55, label='h_I ± τ_I')]
            fig.legend(handles=hd, loc='lower center', ncol=5, fontsize=6.5, frameon=False, bbox_to_anchor=(.5, -.01)); name = f'page_{ABBR[prior]}_{pg//A_["cells_per_page"]+1:02d}'
            fig.suptitle(f'{PN[prior]} 이름표 점검 {pg//A_["cells_per_page"]+1}쪽 · 칸마다 왼쪽 = 단면(옆 ±3 m), 오른쪽 = 패치 기둥 확대 · 세로 = 법선 거리 m(사전 정보 = 0)', fontsize=8)
            fig.savefig(AD/f'{name}.png', dpi=300, bbox_inches='tight', pad_inches=.08); plt.close(fig)
            dump(AD/f'{name}.json', dict(at=now(), page=name, labels=[e['label'] for e in part], source=str(O/f'forward_{prior}_ga3.csv.gz'), note='정답 이름은 audit_key.csv 에만', scientific_verdict=None)); print('PAGE', name, flush=True)
    pd.DataFrame(sheet).to_csv(AD/'audit_sheet.csv', index=False); pd.DataFrame(key).to_csv(AD/'audit_key.csv', index=False)
    dump(AD/'audit_sampling.json', dict(at=now(), seed=A_['seed'], rule=A_, counts=notes_all, scientific_verdict=None)); progress(f'점검 묶음(가): {len(sheet)}칸')
if __name__ == '__main__': main()
