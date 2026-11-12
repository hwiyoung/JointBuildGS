"""Concept video v2: may the r27 fork renderer stand in for the absent official 2DGS image when the 2DGS 7,000 state is meshed?
Compares concept_v2/gtj/renders/..__chk_2dgs_30000 (imgonly_2dgs_s0 30,000 through the r27 fork, RESCORE render_model) with RESCORE's own
renders/B173nb_b10__LoD2__2DGS_30000 (official 2DGS renderer) view by view (matched by camera name): depth max |diff| where both > 0, depth-mask
agreement, RGB max level diff. Pass = every view: depth masks identical, depth max |diff| <= 1 mm, RGB max diff <= 1 level. CPU.
scientific_verdict: null"""
from common import *
V2 = O/'concept_v2'; RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'

def main():
    a = json.loads((V2/'gtj/renders/B173nb_b10__ALS__chk_2dgs_30000/receipt.json').read_text()); b = json.loads((RS/'renders/B173nb_b10__LoD2__2DGS_30000/receipt.json').read_text())
    bf = {v['name']: v['file'] for v in b['views']}; rows = []
    for v in a['views']:
        za = loadz(V2/'gtj/renders/B173nb_b10__ALS__chk_2dgs_30000'/v['file']); zb = loadz(RS/'renders/B173nb_b10__LoD2__2DGS_30000'/bf[v['name']])
        ma, mb = za['depth'] > 0, zb['depth'] > 0; both = ma & mb
        rows.append(dict(name=v['name'], mask_diff_pixels=int((ma != mb).sum()), depth_max_abs_diff_m=float(np.abs(za['depth'][both]-zb['depth'][both]).max()) if both.any() else 0.,
                         rgb_max_diff=int(np.abs(za['rgb'].astype(int)-zb['rgb'].astype(int)).max())))
    ok = all(r['mask_diff_pixels'] == 0 and r['depth_max_abs_diff_m'] <= 1e-3 and r['rgb_max_diff'] <= 1 for r in rows)
    out = dict(at=now(), rule=__doc__, views=len(rows), worst_mask_diff_pixels=max(r['mask_diff_pixels'] for r in rows), worst_depth_max_abs_diff_m=max(r['depth_max_abs_diff_m'] for r in rows),
               worst_rgb_max_diff=max(r['rgb_max_diff'] for r in rows), pass_=ok, rows=rows, scientific_verdict=None)
    dump(V2/'check_2dgs_renderer.json', out); print('CHECK', out['views'], out['worst_mask_diff_pixels'], out['worst_depth_max_abs_diff_m'], out['worst_rgb_max_diff'], ok, flush=True)

if __name__ == '__main__': main()
