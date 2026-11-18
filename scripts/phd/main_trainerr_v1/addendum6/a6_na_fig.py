"""Work na figure (order 10 value figure 'what survives a reset'): survival share by decile of four values, six scenes at 3,000, lines by the patch group. CPU.
-> figures/na_survival.png (+ json); values from tables/na_bins (the plotted rows are copied to payload addendum6/na/fig_survival.npz)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
FIG = A6D/'figures'
VALS = [('views_with_gradient_share', '기울기를 받는 영상의 비율'), ('up_share_depth', '깊이 손실에서 올리는 쪽 영상의 비율'), ('abs_photo', '광도 기울기 절댓값의 합'), ('consistency_photo', '광도 부호 일관성')]
SUB = [('조각: 지킨 점의 조각', '#9e9e9e'), ('조각: 잃은 점의 조각', '#1f5fd6'), ('조각: 고친 점의 조각', '#2ca02c'), ('조각: 목표도 결과도 틀린 점의 조각', '#d62728'), ('조각: 묶인 조각 없음', '#000000')]
RUN_KO = {'sb3_R1_LoD2_record': 'R1 × LoD2', 'tl_R1_ALS_own': 'R1 × 항공 LiDAR', 'tl_B0_b10_LoD2_s0': 'B0 × LoD2', 'ba3_B0_ALS_record': 'B0 × 항공 LiDAR', 'tl_B173nb_b10_ALS_s0': 'B173 × 항공 LiDAR', 'sb4_B173_LoD2_record': 'B173 × LoD2'}

def main():
    plt = korean_plt(); rows = json.loads((A6D/'tables/na_bins.json').read_text())['rows']; out = {}
    fig, axs = plt.subplots(len(VALS), 6, figsize=(30, 17), sharey=True)
    for i, (vk, vko) in enumerate(VALS):
        for j, run in enumerate(RUN_KO):
            ax = axs[i, j]
            for sub, col in SUB:
                rr = sorted([r for r in rows if r['run'] == run and r['reset'] == 3000 and r['value'] == vk and r['subset'] == sub and r['bin'] >= 0], key=lambda r: r['bin'])
                if not rr: continue
                x = [r['bin']+1 for r in rr]; y = [r['alive_pct'] for r in rr]; big = [r['n'] >= 30 for r in rr]
                ax.plot(x, y, color=col, lw=2.2 if '잃은' in sub else 1.4, label=sub.replace('조각: ', '') if (i == 0 and j == 0) else None)
                ax.scatter([a for a, b in zip(x, big) if not b], [a for a, b in zip(y, big) if not b], s=18, facecolors='none', edgecolors=col)
                out[f'{run}__{vk}__{sub}'] = np.array([x, y, [r['n'] for r in rr]], 'f8')
            ax.set_ylim(0, 100); ax.grid(alpha=.3); ax.set_xticks([1, 5, 10])
            if i == 0: ax.set_title(RUN_KO[run], fontsize=14)
            if j == 0: ax.set_ylabel(f'{vko}\n재설정 뒤 살아남은 비율 (%)', fontsize=11)
            if i == len(VALS)-1: ax.set_xlabel('값의 십분위 칸 (1 = 가장 작음, 장면 안 모든 가우시안 기준)')
    axs[1, 0].annotate('값이 클수록 많이 살아남는다', xy=(10, 75), xytext=(2.5, 85), arrowprops=dict(arrowstyle='->', lw=2), fontsize=12, weight='bold', bbox=dict(fc='white', ec='k'))
    axs[0, 0].legend(fontsize=10, loc='upper left'); fig.suptitle('재설정 뒤 살아남는 비율은 이 값에 따라 달라진다 (3,000회 재설정, 빈 동그라미 = 칸 안 가우시안 30개 미만)', fontsize=17, weight='bold')
    fig.tight_layout(rect=(0, 0, 1, .96)); FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG/'na_survival.png', dpi=95); plt.close(fig)
    savez(A6O/'na/fig_survival.npz', **out); dump(FIG/'na_survival.json', dict(at=now(), figure='na_survival.png', table='tables/na_bins.csv', values='payload addendum6/na/fig_survival.npz', reset=3000, scientific_verdict=None))
    print('NA6_FIG', flush=True)

if __name__ == '__main__' and len(sys.argv) == 1: main()

def record():
    """order 4.3 figure: opacity of the in-range Gaussians at the saved states 3000_pre_reset, 3000, 3100 (the only saved states in 3000-3100), survived vs deleted
    (survival = present in the first whole-scene dump after the reset, work na). -> figures/na_record_opacity.png (+ json, payload addendum6/na/fig_record_opacity.npz)"""
    plt = korean_plt(); runs = [('sa1_R1_ALS_record6000', 'R1 × 항공 LiDAR'), ('sb1_B0_LoD2_record6000', 'B0 × LoD2'), ('sb2_B0_ALS_record6000', 'B0 × 항공 LiDAR')]
    fig, axs = plt.subplots(1, 3, figsize=(27, 9), sharey=True); out = {}; xs = [0, 1, 2]; lab = ['3,000회\n재설정 직전', '3,000회\n재설정 직후', '3,100회\n(첫 점검)']
    for ax, (run, ko) in zip(axs, runs):
        z = loadz(A6O/'na'/f'grads_{run}_3000.npz', ['uid', 'alive', 'inside_rows']); ins = z['inside_rows']; uid = z['uid'][ins]; al = z['alive'][ins]; m = RUNS4[run]['model']
        o = np.argsort(uid); vals = {}
        for k, st in enumerate(['3000_pre_reset', '3000', '3100']):
            s = loadz(m/'trainlog/states'/f'{st}.npz', ['uid', 'opacity']); v = np.full(len(uid), np.nan); p = np.clip(np.searchsorted(uid[o], s['uid']), 0, len(uid)-1); ok = uid[o][p] == s['uid']; v[o[p[ok]]] = s['opacity'][ok]; vals[st] = v
        Y = np.stack([vals[s] for s in ['3000_pre_reset', '3000', '3100']], 1); out[f'{run}__opacity'] = Y; out[f'{run}__alive'] = al
        rng = np.random.default_rng(0)
        for flag, col, nm in [(True, '#2ca02c', '살아남은 것'), (False, '#d62728', '지워진 것')]:
            mm = np.flatnonzero(al == flag); pick = rng.choice(mm, min(150, len(mm)), replace=False) if len(mm) else []
            for i in pick: ax.plot(xs, Y[i], color=col, alpha=.08, lw=.8)
            q = np.nanquantile(Y[mm], [.25, .5, .75], axis=0) if len(mm) else np.full((3, 3), np.nan)
            ax.plot(xs, q[1], '-o', color=col, lw=3, ms=8, label=f'{nm} {len(mm):,}개 (중앙값, 띠 = 25–75 %)'); ax.fill_between(xs, q[0], q[2], color=col, alpha=.18)
        ax.axhline(.05, color='k', ls='--', lw=1.5); ax.text(2.05, .05, '지우는 문턱 0.05', va='center', fontsize=11)
        ax.set_yscale('log'); ax.set_ylim(.005, 1.); ax.set_xticks(xs); ax.set_xticklabels(lab, fontsize=12); ax.set_xlim(-.2, 2.6); ax.grid(alpha=.3)
        ax.set_title(f'{ko} (기록 범위 안 가우시안)', fontsize=14, loc='left'); ax.legend(loc='lower left', fontsize=11)
        if not np.isfinite(Y[:, 2]).any(): ax.text(1, .3, '3,100회 저장 없음', ha='center')
    axs[0].set_ylabel('불투명도 (로그 눈금)', fontsize=12)
    axs[0].annotate('재설정: 모두 0.01', xy=(1, .01), xytext=(.35, .0065), arrowprops=dict(arrowstyle='->', lw=1.8), fontsize=12)
    fig.suptitle('재설정 뒤 100회 동안 불투명도가 올라간 정도: 살아남은 것과 지워진 것 (저장된 상태는 3,000·3,100회 둘뿐)', fontsize=17, weight='bold'); fig.tight_layout(rect=(0, 0, 1, .93))
    fig.savefig(FIG/'na_record_opacity.png', dpi=100); plt.close(fig); savez(A6O/'na/fig_record_opacity.npz', **out)
    dump(FIG/'na_record_opacity.json', dict(at=now(), figure='na_record_opacity.png', states=['3000_pre_reset', '3000', '3100'], note='no saved state between 3000 and 3100 (records every 100 there)', values='payload addendum6/na/fig_record_opacity.npz', scientific_verdict=None))
    print('NA6_RECFIG', flush=True)

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'record': record()
