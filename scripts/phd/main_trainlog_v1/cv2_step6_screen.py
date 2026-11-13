"""Step-6 screening (2026-11-13, user: 'make it for another building too'). Read-only; writes docs figures_concept_v2/step6_find/screen.json only.
For every GTJUDGE scene (site x prior): GT rows with the prior right (present, distance <= TAU), split by the image depth (MVS) PRESENT but > 0.5 m off
(image wrong) and ABSENT (no image depth), roof / wall, with the 30,000 completeness (|row_s| <= row_tau_m) of FINALTRAIN_30000 (this method),
2DGS_30000 (image only), mvs (image-depth mesh) and prior (prior surface). The step-6 case of the TRAINLOG order is 'image depth wrong, prior right'.
GT is used only to classify rows and to score. No pass criteria. scientific_verdict: null"""
import time
from common import *
import importlib.util
OUTD = D/'figures_concept_v2'/'step6_find'; TAU = 0.211856

def main():
    t0 = time.monotonic(); spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    out = []
    for stem in sorted(p.name for p in (GT/'scenes').iterdir() if (p/'rows.npz').exists()):
        row = loadz(GT/'scenes'/stem/'rows.npz', ['row_tau_m', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence', 'wall'])
        tau = row['row_tau_m']; wall = row['wall'].astype(bool); pr = row['prior_presence'].astype(bool) & (row['prior_distance_m'] <= TAU); mp = row['mvs_presence'].astype(bool)
        gd = GT/'scenes'/stem/'distances'; rs = {k: loadz(gd/f'{f}.npz', ['row_s'])['row_s'] for k, f in (('ours', 'FINALTRAIN_30000'), ('twodgs', '2DGS_30000'), ('image_depth_mesh', 'mvs'), ('prior_surface', 'prior'))}
        comp = lambda m: {k: round(float(nl.values(v[m], tau[m])['within_pct']), 1) for k, v in rs.items()} if m.any() else None
        for kind, km in (('roof', ~wall), ('wall', wall)):
            if not km.any(): continue
            for case, m in (('image_wrong', km & pr & mp & (row['mvs_distance_m'] > .5)), ('image_absent', km & pr & ~mp)):
                out.append(dict(scene=stem, surface=kind, case=case, rows=int(m.sum()), completeness_30000_pct=comp(m))); print('ROW', json.dumps(out[-1]), flush=True)
    OUTD.mkdir(parents=True, exist_ok=True); dump(OUTD/'screen.json', dict(at=now(), rule=__doc__, rows=out, seconds=round(time.monotonic()-t0, 1), scientific_verdict=None)); print('DONE', flush=True)

if __name__ == '__main__': main()
