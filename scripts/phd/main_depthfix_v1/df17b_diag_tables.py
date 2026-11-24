"""Question ① completion (11-24): per-point change of right-target views 판 0 → 판 1 and the counts of removed views by reason, from df17 outputs (CPU, read only).
Tables (docs/tables):
  diag_ga_change_<stem> : per group (lost / kept at 판 0), distribution of Δ = right views 판 1 − 판 0 per point (bins), all outward views and visible views only
  diag_ga_reason_<stem> : per group, number of (point, view) pairs right at 판 0 and not at 판 1, split into: back-facing disc removed (then: another disc owns,
                          image depth, nothing), 10 m rule weight 0; plus the same restricted to visible views (point not hidden, TARGETPATH 10 m rule).
판 2~4 maps keep the 판 1 owners and zero weights (switch 나/다 only rescale positive weights), so their right-view counts equal 판 1 (checked on the maps' weight>0 sets).
usage: df17b_diag_tables.py <stem>"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
BINS = [(-10**6, -20, '−20 이하'), (-19, -10, '−19 ~ −10'), (-9, -5, '−9 ~ −5'), (-4, -1, '−4 ~ −1'), (0, 0, '0'), (1, 10**6, '+1 이상')]

def main(stem):
    z = loadz(O/'points'/f'diag_ga_{stem}.npz'); kept = z['kept']; rows, rr = [], []
    for g, mk in [('잃은 점(판 0)', ~kept), ('지킨 점(판 0)', kept)]:
        for lab, a, b in [('모든 바깥 영상', 'right0', 'right1'), ('가려지지 않은 영상', 'right0_vis', 'right1_vis')]:
            d = (z[b] - z[a])[mk]; r = dict(stem=STEM_KO[stem], group=g, views=lab, points=int(mk.sum()), delta_median=float(np.median(d)) if len(d) else None,
                                            p0_median=float(np.median(z[a][mk])) if len(d) else None, p1_median=float(np.median(z[b][mk])) if len(d) else None)
            for lo, hi, nm in BINS: r[f'Δ {nm} 점'] = int(((d >= lo) & (d <= hi)).sum())
            rows.append(r)
        tot = int((z['right0'] - z['still'])[mk].sum())
        rr.append(dict(stem=STEM_KO[stem], group=g, points=int(mk.sum()), p0_right_pairs=int(z['right0'][mk].sum()), removed_pairs=tot,
                       back_then_other_disc=int((z['back_other_right'] + z['back_other_wrong'])[mk].sum()), back_then_other_disc_right=int(z['back_other_right'][mk].sum()),
                       back_then_image_depth=int(z['back_image'][mk].sum()), back_then_nothing=int(z['back_none'][mk].sum()), front10_weight0=int(z['front10'][mk].sum()),
                       other=int((z['same_owner_other'] + z['other_no_back'])[mk].sum()),
                       removed_pairs_visible_views=int(((z['right0_vis'] - z['right1_vis'])[mk]).clip(min=0).sum()),
                       removed_pairs_hidden_views=int(tot - ((z['right0_vis'] - z['right1_vis'])[mk]).clip(min=0).sum())))
    table(f'diag_ga_change_{stem}', rows); table(f'diag_ga_reason_{stem}', rr)
    # 판 2~4 = 판 1 right counts: same owner and weight>0 sets
    idx = json.loads((O/'maps/base/ga'/stem/'index.json').read_text())['views']; same = True
    for name in list(idx)[::40]:
        g = loadz(O/'maps/base/ga'/stem/f'{name}.npz', ['owner', 'weight'])
        for v in ['ga_na', 'ga_da', 'ga_na_da']:
            h = loadz(O/'maps/base'/v/stem/f'{name}.npz', ['owner', 'weight']); same &= bool(np.array_equal(g['owner'], h['owner']) and np.array_equal(g['weight'] > 0, h['weight'] > 0))
    dump(D/'tables'/f'diag_ga_p234_same_{stem}.json', dict(stem=stem, views_checked=len(list(idx)[::40]), owner_and_positive_weight_equal_to_p1=same, scientific_verdict=None))
    print('DIAGB', stem, same, json.dumps(rr, ensure_ascii=False)[:600], flush=True)

if __name__ == '__main__': main(sys.argv[1])
