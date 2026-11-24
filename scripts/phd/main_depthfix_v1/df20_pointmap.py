"""Order 7 point maps (CPU): top view per scene, one panel per arm compared with 판 0 (seed 0, base extraction).
Main-metric points (image depth wrong, 판 0 target right): lost at 판 0 & kept at the arm (green), kept at 판 0 & lost at the arm (red).
Keep-value-1 points (prior wrong, 판 0 target wrong): fixed at the arm only (blue), fixed at 판 0 only (orange). Other points light gray.
usage: df20_pointmap.py <stem> <arm>[,<arm>...]   writes /docs/figures/pointmap_<stem>.png/.pdf/.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = font_manager.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
def main(stem, arms):
    arms = arms.split(','); P = loadz(O/'points'/f'pts_{stem}.npz', ['xyz', 'case_id', 'target_ok']); R = loadz(O/'points_out'/f'res_{stem}.npz')
    w0 = (R['p0_s0'] & 1).astype(bool); m2 = (P['case_id'] == 2) & P['target_ok']; m1 = (P['case_id'] == 1) & ~P['target_ok']; xy = P['xyz'][:, :2]
    fig, ax = plt.subplots(1, len(arms), figsize=(6.5*len(arms), 6.5), squeeze=False, constrained_layout=True); meta = []
    for i, a in enumerate(arms):
        if f'{a}_s0' not in R: ax[0, i].set_title(f'판 {a[1]} 결과 없음'); continue
        w = (R[f'{a}_s0'] & 1).astype(bool); A = ax[0, i]; A.scatter(xy[::7, 0], xy[::7, 1], s=.2, c='0.85')
        groups = [('잃음 → 지킴', m2 & ~w0 & w, '#2ca02c'), ('지킴 → 잃음', m2 & w0 & ~w, '#d62728'), ('고침(이 판만)', m1 & ~w0 & w, '#1f5fd6'), ('고침(판 0만)', m1 & w0 & ~w, '#ff7f0e')]
        for lab, mk, col in groups: A.scatter(xy[mk, 0], xy[mk, 1], s=1.5, c=col, label=f'{lab} ({int(mk.sum()):,})')
        A.set_aspect('equal'); A.set_title(f'판 {a[1]} 대 판 0'); A.legend(fontsize=8, markerscale=6, loc='best'); A.set_xlabel('x (m)'); A.set_ylabel('y (m)')
        meta.append(dict(arm=a, **{lab: int(mk.sum()) for lab, mk, _ in groups}))
    fig.suptitle(f'{STEM_KO[stem]}: 판 0에서 바뀐 점 (위에서 본 지도, 기준 추출)'); p = D/'figures'/f'pointmap_{stem}'; fig.savefig(p.with_suffix('.png'), dpi=100); fig.savefig(p.with_suffix('.pdf')); plt.close(fig)
    dump(p.with_suffix('.json'), dict(stem=stem, panels=meta, rule=__doc__, scientific_verdict=None)); print('PMAP', stem, json.dumps(meta, ensure_ascii=False), flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
