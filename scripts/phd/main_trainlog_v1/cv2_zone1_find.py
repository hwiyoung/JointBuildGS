"""Concept video v2 side check (2026-11-13, user: 'find a real image-error -> 보존 place for zone 1'). Read-only; writes docs figures_concept_v2/zone1_find/zone1_find.json only.
Patch classes over all valid FT target patches of B173 x ALS (judge_region 0 일치, 2 보정, 1 보존, 4 결측):
  image depth = MVS patch mean point (centre + normal x mvs_mean_m); 'image wrong' = its distance to GT dense > 0.5 m;
  'prior kept right' = 보존 patch whose chosen target is within TAU (0.211856 m) of GT; 'prior kept wrong' = 보존 target > 0.5 m from GT.
  wanted = 보존 & image wrong & prior kept right (the zone-1 story in the request: image depth wrong, judgment keeps the prior).
  Mode 'agree' (argv[1] == 'agree'): wanted = 일치 & image wrong & chosen target within TAU of GT (most image-wrong patches are judged 일치, not 보존;
  this asks whether 'image wrong, target still right' clusters under that label). Writes zone1_find_agree.json.
Candidates: 3 m xy cells ranked by the patch area of 'wanted'; for the top cells (non-overlapping), a 12 x 8 m box on the cell's 'wanted' centroid, long axis = the
principal xy axis of the 'wanted' patches within 6 m (the spots_v5 window size used for zone 1). For each box: patch counts by judgment, wanted / kept-wrong /
image-wrong counts, mean normal z, height, and the 30,000 mesh completeness inside the box (GTJUDGE rows, |row_s| <= row_tau_m, normal_line.values) for this
method, judgment off (203-view) and image-only 2DGS (203-view); and whether the box centre is inside the ① camera crop.
GT is used only to classify patches and to score. No pass criteria. scientific_verdict: null"""
import sys
from cv2_frames import *
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
import importlib.util
OUTD = FIGD/'zone1_find'

def main(mode='keep'):
    t0 = time.monotonic(); S = Static(); st = loadz(V2/'static.npz'); sj = json.loads((V2/'static.json').read_text()); g0 = S.ground
    G = loadz(Path(sj['gt']), ['xyz'])['xyz'].astype(float); T = cKDTree(G)
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'normal', 'sigma', 'judge_region', 'region', 'centre', 'mvs_mean_m', 'area'])
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0) & np.isin(tg['judge_region'], [0, 1, 2, 4])
    iv = np.flatnonzero(valid); J = tg['judge_region']; A = tg['area']; mv = np.isfinite(tg['mvs_mean_m'])
    MP = tg['centre']+tg['normal']*np.where(mv, tg['mvs_mean_m'], 0.)[:, None]
    dm = np.full(len(J), np.nan); q = iv[mv[iv]]; dm[q], _ = T.query(MP[q], k=1)
    dt = np.full(len(J), np.nan); dt[iv], _ = T.query(tg['target'][iv], k=1)
    img_wrong = np.nan_to_num(dm, nan=0) > .5
    keep = valid & (J == 1); wanted = keep & img_wrong & (dt <= TAU); kept_wrong = keep & (dt > .5)
    if mode == 'agree': wanted = valid & (J == 0) & img_wrong & (dt <= TAU)
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, overall=dict(
        valid_patches=int(valid.sum()), by_judgment={JN[j]: int((valid & (J == j)).sum()) for j in (0, 2, 1, 4)},
        image_wrong_by_judgment={JN[j]: int((valid & img_wrong & (J == j)).sum()) for j in (0, 2, 1, 4)},
        keep_n=int(keep.sum()), keep_prior_right_n=int((keep & (dt <= TAU)).sum()), keep_prior_wrong_n=int(kept_wrong.sum()),
        keep_image_wrong_n=int((keep & img_wrong).sum()), wanted_n=int(wanted.sum()), wanted_area_m2=round(float(A[wanted].sum()), 2),
        keep_image_right_prior_wrong_n=int((keep & ~img_wrong & (dt > .5)).sum()), mode=mode,
        agree_image_wrong_target_right_n=int((valid & (J == 0) & img_wrong & (dt <= TAU)).sum()), agree_image_wrong_target_wrong_n=int((valid & (J == 0) & img_wrong & (dt > .5)).sum()),
        agree_image_wrong_normal_z_abs_median=round(float(np.median(np.abs(tg['normal'][valid & (J == 0) & img_wrong, 2]))), 2)))
    print('OVERALL', json.dumps(rec['overall'], ensure_ascii=False), flush=True)
    # candidate boxes
    W = np.flatnonzero(wanted); P = tg['target'][W]; cell = np.floor(P[:, :2]/3).astype(int); keys, inv = np.unique(cell, axis=0, return_inverse=True)
    score = np.bincount(inv.ravel(), weights=A[W], minlength=len(keys)); order = np.argsort(-score)
    spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    row = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'row_tau_m']); RX = row['xyz'].astype(float)
    fams = dict(ours=(O/'gtj/scenes'/STEM/'distances', 'tl_30000'), nojudge=(V2/'gtj/scenes'/STEM/'distances', 'cmp_nojudge_30000_v203'), img2dgs=(V2/'gtj/scenes'/STEM/'distances', 'cmp_2dgs_30000_v203'))
    rs = {k: loadz(r/f'{f}.npz', ['row_s'])['row_s'] for k, (r, f) in fams.items()}
    u0, v0, u1, v1 = st['crop']; boxes = []; cands = []
    for ci in order[:40]:
        if len(cands) >= 6 or score[ci] <= 0: break
        m = inv.ravel() == ci; c = P[m, :2].mean(0)
        if any(b.contains(shapely.points(c[0], c[1])) for b in boxes): continue
        near = np.linalg.norm(P[:, :2]-c, axis=1) <= 6; Q = P[near, :2]-P[near, :2].mean(0)
        ax_ = np.linalg.eigh(Q.T@Q)[1][:, -1] if len(Q) >= 3 else np.array([1., 0.]); nx = np.array([-ax_[1], ax_[0]])
        poly = Polygon([c-6*ax_-4*nx, c+6*ax_-4*nx, c+6*ax_+4*nx, c-6*ax_+4*nx]); boxes.append(poly)
        inb = valid & shapely.contains_xy(poly, tg['target'][:, 0], tg['target'][:, 1])
        rin = shapely.contains_xy(poly, RX[:, 0], RX[:, 1]) & (RX[:, 2] >= S.zr[0]) & (RX[:, 2] <= S.zr[1])
        comp = {k: round(float(nl.values(v[rin], row['row_tau_m'][rin])['within_pct']), 1) if rin.any() else None for k, v in rs.items()}
        h = tg['target'][inb & wanted, 2]-g0; nz = np.abs(tg['normal'][inb & wanted, 2])
        u, w, _ = S.pix(np.array([[c[0], c[1], float(np.median(tg['target'][inb & wanted, 2]))]]))
        cands.append(dict(centre_xy=c.tolist(), axis_xy=ax_.tolist(), box_xy=[list(map(float, p)) for p in poly.exterior.coords][:4], cell_wanted_area_m2=round(float(score[ci]), 2),
                          box_patches=int(inb.sum()), box_by_judgment={JN[j]: int((inb & (J == j)).sum()) for j in (0, 2, 1, 4)},
                          box_wanted_n=int((inb & wanted).sum()), box_kept_wrong_n=int((inb & kept_wrong).sum()), box_image_wrong_n=int((inb & img_wrong).sum()),
                          wanted_height_median_m=round(float(np.median(h)), 2), wanted_normal_z_abs_median=round(float(np.median(nz)), 2),
                          wanted_image_error_median_m=round(float(np.nanmedian(dm[inb & wanted])), 2), gt_rows_in_box=int(rin.sum()), completeness_30000_pct=comp,
                          in_camera_crop=bool(u0 <= u[0] <= u1 and v0 <= w[0] <= v1), camera_uv=[float(u[0]), float(w[0])]))
        print('CAND', json.dumps(cands[-1], ensure_ascii=False), flush=True)
    rec['candidates'] = cands; rec['seconds'] = round(time.monotonic()-t0, 1); OUTD.mkdir(parents=True, exist_ok=True); dump(OUTD/('zone1_find_agree.json' if mode == 'agree' else 'zone1_find.json'), rec); print('DONE', rec['seconds'], flush=True)

if __name__ == '__main__': main(sys.argv[1] if len(sys.argv) > 1 else 'keep')
