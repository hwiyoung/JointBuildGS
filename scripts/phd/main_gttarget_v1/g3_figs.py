"""Stage 3 (order 9) figures other than the site figures (CPU): lost-point maps, share bars (table ra), TRAINERR cells 1-3 maps, unexplained points map.
usage: g3_figs.py lostmap | bars | cells | unexplained | all     -> /docs/figures/<name>.png + .json, plotted points /gt/figdata/<name>.npz
Lost points from every eligible GT row (GTJUDGE addendum11 final_data): method lost = judgment_mesh within tau and FINALTRAIN_30000 outside;
GTT lost = gtt_target within tau and gtt_s0_base outside. Frame = local training frame (m), +y = north."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
FIG = D/'figures'; FD = O/'figdata'
SC_KO = {'R1rep_b10__LoD2': 'R1 × LoD2', 'R1rep_b10__ALS': 'R1 × 항공 LiDAR', 'B0_b10__LoD2': 'B0 × LoD2', 'B0_b10__ALS': 'B0 × 항공 LiDAR', 'B173nb_b10__ALS': 'B173 × 항공 LiDAR', 'B173nb_b10__LoD2': 'B173 × LoD2'}
C_BOTH, C_M, C_G, C_BG = '#6a3d9a', '#1f78b4', '#e31a1c', '#d9d9d9'
def plt_():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    F = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(F); plt.rcParams['font.family'] = fm.FontProperties(fname=F).get_name(); plt.rcParams['axes.unicode_minus'] = False; return plt
def meta(name, **k): dump(FIG/f'{name}.json', dict(at=now(), figure=f'{name}.png', title=TITLE, points=f'payload figdata/{name}.npz', frame='local training frame (m), +y = north', **k, scientific_verdict=None))
def scenes(): return [s for s in STEMS if (O/'meshes'/f'{s}__gtt_s0_base/points.npz').exists()]
def lost_arrays(stem):
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool)
    ml = el & A['reference__judgment_mesh__within_tau1'].astype(bool) & ~A['reference__FINALTRAIN_30000__within_tau1'].astype(bool)
    tw = np.load(O/'meshes'/f'{stem}__gtt_target/points.npz')['reference__within_tau1'].astype(bool); bw = np.load(O/'meshes'/f'{stem}__gtt_s0_base/points.npz')['reference__within_tau1'].astype(bool)
    gl = el & tw & ~bw; kept = el & tw & bw; return A['reference__xyz'].astype('f8'), ml, gl, kept, A['reference__point_id']

def lostmap():
    plt = plt_(); ss = scenes(); fig, axs = plt.subplots(2, 3, figsize=(27, 18)); axs = axs.ravel(); out = {}
    for ax, stem in zip(axs, ss):
        X, ml, gl, kept, pid = lost_arrays(stem); rng = np.random.default_rng(0); kk = np.flatnonzero(kept); kk = rng.choice(kk, min(len(kk), 60000), replace=False)
        ax.scatter(X[kk, 0], X[kk, 1], s=.3, c=C_BG, lw=0, rasterized=True)
        for m, col, lab in [(ml & ~gl, C_M, '본 방법 판에서만 잃음'), (gl & ~ml, C_G, '참값 목표 판에서만 잃음'), (ml & gl, C_BOTH, '두 판 모두 잃음')]:
            ax.scatter(X[m, 0], X[m, 1], s=2, c=col, lw=0, rasterized=True, label=f'{lab} {int(m.sum()):,}')
        ax.set_aspect('equal'); ax.set_title(f'{SC_KO[stem]}', fontsize=15, loc='left'); ax.legend(markerscale=6, fontsize=11, loc='upper right'); ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')
        out[f'{stem}__point_id_method_lost'] = pid[ml]; out[f'{stem}__point_id_gtt_lost'] = pid[gl]
    for ax in axs[len(ss):]:
        ax.set_axis_off(); ax.text(.5, .5, 'B173 × LoD2: 결과 없음\n(15,000회 건강 점검 멈춤 3회)', ha='center', va='center', fontsize=16, transform=ax.transAxes)
    fig.suptitle(f'{TITLE} — 잃은 점 지도: 본 방법 판과 참값 목표 판 (위에서 본 그림, 회색 = 참값 목표 판 지킨 점 표본)', fontsize=19, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .96))
    FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/'lostmap.png', dpi=90); plt.close(fig); savez(FD/'lostmap.npz', **out)
    meta('lostmap', scenes=ss, colours={'both': C_BOTH, 'method only': C_M, 'gtt only': C_G, 'kept sample (60,000, rng 0)': C_BG})

def bars():
    plt = plt_(); R_ = json.loads((D/'tables/ra_share.json').read_text())['rows']; keys = ['가림 제외로 돌아옴', '중앙 깊이까지 쓰면 돌아옴', '돌아오지 않음']; cols = ['#17becf', '#9edae5', '#7f7f7f']
    pooled = [r for r in R_ if str(r.get('stem', '')).startswith('합(')]; r1 = [r for r in R_ if r.get('stem') in ('R1rep_b10__ALS', 'R1rep_b10__LoD2')]
    def sumrows(rows, arm):
        rr = [r for r in rows if r['arm'] == arm]; n = sum(r['lost_n'] for r in rr); return n, [100*sum(r[f'{k}_n'] for r in rr)/max(1, n) for k in keys]
    panels = [('다섯 장면 합', [(r['arm'], r['lost_n'], [r[f'{k}_pct'] for k in keys]) for r in pooled if r['arm'] != '참값 목표 판 씨앗 1']),
              ('R1 두 장면 합 (씨앗 1이 있는 장면)', [(a, *sumrows(r1, a)) for a in ['본 방법 판(FINALTRAIN, 덧붙임 6)', '참값 목표 판 씨앗 0', '참값 목표 판 씨앗 1']])]
    fig, axs = plt.subplots(1, 2, figsize=(22, 7.5)); data = {}
    for ax, (ttl, rows) in zip(axs, panels):
        for i, (arm, n, sh) in enumerate(rows):
            left = 0
            for k, v, c in zip(keys, sh, cols):
                ax.barh(i, v, left=left, color=c, edgecolor='white', label=k if i == 0 else None)
                if v >= 4: ax.text(left+v/2, i, f'{v:.0f} %', ha='center', va='center', fontsize=13)
                left += v
            data[f'{ttl}__{arm}'] = dict(lost_n=n, shares_pct=sh)
        ax.set_yticks(range(len(rows))); ax.set_yticklabels([f'{a}\n잃은 점 {n:,}' for a, n, _ in rows], fontsize=12); ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel('잃은 점 가운데 비율 (%)'); ax.set_title(ttl, fontsize=15, loc='left')
    axs[0].legend(loc='lower center', bbox_to_anchor=(1.05, -.32), ncol=3, fontsize=13, frameon=False)
    fig.suptitle(f'{TITLE} — 잃은 점이 다시 추출하면 돌아오는가 (표 라)', fontsize=18, weight='bold'); fig.tight_layout(rect=(0, .06, 1, .93)); fig.savefig(FIG/'ra_bars.png', dpi=100); plt.close(fig)
    savez(FD/'ra_bars.npz', keys=np.array(keys)); meta('ra_bars', values=data, note='여섯 장면 발주문 값(본 방법 판): 29 / 27 / 44 %')

def cells():
    plt = plt_(); cs = json.loads((R/'configs/phd/main_trainerr_v1/trainerr_v1.json').read_text())['cells']; fig, axs = plt.subplots(3, 3, figsize=(27, 25)); out = {}
    for row, (cell, c) in enumerate(cs.items()):
        stem = f"{c['site']}__{c['prior']}"; A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); B = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz'); case = c['case_id']
        T = np.load(O/'meshes'/f'{stem}__gtt_target/points.npz'); G = np.load(O/'meshes'/f'{stem}__gtt_s0_base/points.npz')
        arms = [('본 방법 판', A['reference__judgment_mesh__within_tau1'], A['reference__FINALTRAIN_30000__within_tau1'], {k: A[f'result__FINALTRAIN_30000__{k}'] for k in ['xyz', 'eligible_new', 'case_id', 'within_tau1']}),
                ('패치 다수결 판(A-1)', A['reference__gt_judgment_mesh__within_tau1'], B['reference__A1__within_tau1'], {k: B[f'result__A1__{k}'] for k in ['xyz', 'eligible_new', 'case_id', 'within_tau1']}),
                ('참값 목표 판', T['reference__within_tau1'], G['reference__within_tau1'], {k: G[f'result__{k}'] for k in ['xyz', 'eligible_new', 'case_id', 'within_tau1']})]
        for col, (arm, tw, rw, res) in enumerate(arms):
            ax = axs[row, col]
            if c['metric'] == 'completeness':
                m = A['reference__case_id'] == case; X = A['reference__xyz'][m]; tw_, rw_ = tw[m].astype(bool), rw[m].astype(bool)
                for mm, colr, lab in [(tw_ & rw_, '#33a02c', '목표·결과 모두 허용 거리 안'), (tw_ & ~rw_, C_G, '목표는 안, 결과는 밖(잃음)'), (~tw_ & rw_, '#ff7f00', '목표는 밖, 결과는 안'), (~tw_ & ~rw_, '#6a6a6a', '둘 다 밖')]:
                    ax.scatter(X[mm, 0], X[mm, 1], s=3, c=colr, lw=0, rasterized=True, label=f'{lab} {int(mm.sum()):,}')
                val = f'목표 {100*tw_.mean():.1f} → 결과 {100*rw_.mean():.1f} % (참값 점 {int(m.sum()):,})'
            else:
                e = res['eligible_new'].astype(bool) & (res['case_id'] == case); X = res['xyz'][e]; w = res['within_tau1'].astype(bool)[e]
                ax.scatter(X[w, 0], X[w, 1], s=1, c='#33a02c', lw=0, rasterized=True, label=f'허용 거리 안 {int(w.sum()):,}'); ax.scatter(X[~w, 0], X[~w, 1], s=2, c=C_G, lw=0, rasterized=True, label=f'허용 거리 밖 {int((~w).sum()):,}')
                val = f'학습 뒤 정확성 {100*w.mean():.1f} % (결과 점 {int(e.sum()):,})'
            out[f'{cell}__{col}__xyz'] = X
            ax.set_aspect('equal'); ax.legend(markerscale=5, fontsize=10, loc='upper right'); ax.set_title(f"칸 {cell[1]} · {SC_KO[stem]} {c['case_name']} {'완전성' if c['metric'] == 'completeness' else '정확성'} — {arm}\n{val}", fontsize=13, loc='left')
    fig.suptitle(f'{TITLE} — TRAINERR 칸 1·2·3 (위에서 본 그림)', fontsize=19, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .97)); fig.savefig(FIG/'cells_map.png', dpi=80); plt.close(fig)
    savez(FD/'cells_map.npz', **out); meta('cells_map', cells=list(cs))

def unexplained():
    plt = plt_(); ss = [s for s in STEMS if (O/'ca'/f'causes_{s}_gtt_s0.npz').exists()]; tot = 0; Z = {}
    for s in ss: z = loadz(O/'ca'/f'causes_{s}_gtt_s0.npz', ['xyz', 'group', 'unexplained', 'state']); Z[s] = z; tot += int((z['unexplained'] & (z['group'] == 1)).sum())
    if tot <= 100: dump(FIG/'unexplained_map.json', dict(at=now(), title=TITLE, unexplained_total=tot, drawn=False, rule='drawn only above 100 points (order 8.4)', scientific_verdict=None)); print('UNEXPLAINED', tot, 'not drawn'); return
    fig, axs = plt.subplots(2, 3, figsize=(27, 18)); axs = axs.ravel()
    for ax, s in zip(axs, ss):
        z = Z[s]; X = z['xyz']; g0 = z['group'] == 0; u = z['unexplained'] & (z['group'] == 1); l = (z['group'] == 1) & ~u
        ax.scatter(X[g0, 0], X[g0, 1], s=.3, c=C_BG, lw=0, rasterized=True); ax.scatter(X[l, 0], X[l, 1], s=1.5, c='#fdbf6f', lw=0, rasterized=True, label=f'그 밖의 잃은 점 {int(l.sum()):,}')
        ax.scatter(X[u, 0], X[u, 1], s=4, c='k', lw=0, rasterized=True, label=f'설명되지 않음 {int(u.sum()):,}'); ax.set_aspect('equal'); ax.legend(markerscale=5, fontsize=11); ax.set_title(SC_KO[s], fontsize=15, loc='left')
    for ax in axs[len(ss):]: ax.set_axis_off()
    fig.suptitle(f'{TITLE} — 설명되지 않는 잃은 점 (위에서 본 그림)', fontsize=19, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .96)); fig.savefig(FIG/'unexplained_map.png', dpi=90); plt.close(fig)
    meta('unexplained_map', unexplained_total=tot, source='payload ca/causes_<stem>_gtt_s0.npz')

if __name__ == '__main__':
    FD.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True); w = sys.argv[1]
    for f in ([lostmap, bars, cells, unexplained] if w == 'all' else [globals()[w]]): f()
