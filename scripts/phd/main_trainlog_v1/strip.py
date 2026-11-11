"""Order 5.3 paper strip: six iterations x (surface, inner, section) + completeness curve; PNG 300 dpi and PDF. Same camera, band, colours as frames."""
from frames import *

def main():
    ctx = Ctx(); its = ctx.c['figures']['strip']['iterations']; names = [str(i) for i in its]
    st = loadz(A/'static.npz'); s30 = ctx.defs.section(state('30000')); u = s30['u'][(s30['v'] >= ctx.b0) & (s30['v'] < ctx.b0+1)]
    ctx.sec_xlim = (float(min(u.min(), st['gt_u'].min()))-1, float(max(u.max(), st['gt_u'].max()))+1)
    fig = plt.figure(figsize=(18, 11.5), facecolor='white'); gs = fig.add_gridspec(4, 6, height_ratios=[1, 1, .8, .75], hspace=.18, wspace=.06, left=.05, right=.99, top=.95, bottom=.06)
    for j, n in enumerate(names):
        ax = dict(surface=fig.add_subplot(gs[0, j]), inner=fig.add_subplot(gs[1, j]), section=fig.add_subplot(gs[2, j]))
        frame(ctx, n, 'result', fig=fig, axes=ax)
        ax['surface'].set_title(f'{int(n):,}회', fontsize=13, loc='center', color='#16263d', fontweight='bold'); ax['inner'].set_title(''); ax['section'].set_title('')
        if j: ax['section'].set_ylabel(''); ax['section'].set_yticklabels([])
        ax['section'].tick_params(labelsize=8); ax['section'].set_xlabel('지붕 긴 방향 (m)' if j == 0 else '', fontsize=9)
    for r, lab in enumerate(['표면 (메시)', '속 (가우시안 원반)', '단면 (보정 자리 1 m)']):
        fig.text(.012, [.84, .6, .39][r], lab, rotation=90, va='center', fontsize=12, color='#2e3a48')
    L = fig.add_subplot(gs[3, :]); ks = sorted(ctx.scores)
    for metric, ls_, lab in [('completeness_pct', '-', '본 방법 완전성'), ('accuracy_pct', (0, (4, 2)), '본 방법 정확성')]:
        L.plot(ks, [ctx.scores[k][1][metric] for k in ks], color='#D85A30', lw=1.8, ls=ls_, marker='o', ms=4, label=lab)
    for (lab, v), col in zip([('판단만', (ctx.refs['judgment'], None)), ('LGDM', ctx.refs['LGDM']), ('GeoGS', ctx.refs['GeoGS']), ('원래 판 30,000회', ctx.refs['original'])], ['#888780', '#1D9E75', '#7FA7D9', '#16263d']):
        L.axhline(v[0], color=col, lw=.9, label=lab+' 완전성')
        if v[1] is not None: L.axhline(v[1], color=col, lw=.9, ls=(0, (4, 2)))
    for n in its: L.axvline(n, color='#C9C7BE', lw=.8)
    L.set_xlim(-300, 30300); L.set_ylim(0, 102); L.set_ylabel('사례 자리 경우 1 (%)', fontsize=10); L.legend(loc='lower right', fontsize=8.5, ncol=3, frameon=False)
    L.set_xticks(its); L.set_xticklabels([f'{i:,}' for i in its]); L.set_xlabel('학습 반복', fontsize=10)
    h = [Patch(color=COL[0], label='일치'), Patch(color=COL[2], label='보정'), Patch(color=COL[1], label='보존'), Patch(color=COL[4], label='결측'), Patch(color=PINK, label='틀린 판정 계보'), Patch(color=NEU, label='가까운 목표 없음'),
         Patch(color=tuple(np.array(to_rgb(COL[2]))*.45+PALE*.55), label='흐린 색 = 묶이지 않음'), Patch(color=GREY, label='표면 τ 안'), Patch(color=RED, label='표면 위로 1 m'), Patch(color=BLUE, label='표면 아래로 1 m')]
    fig.legend(handles=h, loc='lower center', ncol=10, frameon=False, fontsize=9.5, bbox_to_anchor=(.5, .005))
    out = O/'figures'; out.mkdir(exist_ok=True)
    fig.savefig(out/'strip_B173_학습과정_v1.png', dpi=300, facecolor='white'); fig.savefig(out/'strip_B173_학습과정_v1.pdf', facecolor='white'); plt.close(fig)
    dump(out/'strip_B173_학습과정_v1.json', dict(at=now(), iterations=its, rows=['surface mesh (key iteration)', 'inner disks (drawing = lineage)', 'section band'], camera=dict(basis=ctx.Bs.tolist(), center=ctx.ctr.tolist(), projection='orthographic az180 el35'),
         band=dict(b0=ctx.b0, width_m=1), sources={n: sha(DER/'gaussians'/f'{n}.npz') for n in names}, meshes={n: sha(O/'gtj/meshes'/f'{STEM}__tl_{n}'/'final.ply') for n in names if (O/'gtj/meshes'/f'{STEM}__tl_{n}'/'final.ply').exists()},
         plate='새 판 (tl_B173nb_b10_ALS_s0 attempt2)', scientific_verdict=None))
    print('STRIP done', flush=True)
if __name__ == '__main__': main()
