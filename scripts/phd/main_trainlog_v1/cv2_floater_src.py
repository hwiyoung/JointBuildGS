"""Concept video v2 side check, part 2 (2026-11-13): where do the roof-height floaters along the building edge come from. Read-only; prints and writes
docs figures_concept_v2/floater_check/floater_source.json only.
Edge floaters of a mesh = faces of the UNCUT original-rule mesh outside the LoD2 footprint by at most 3 m, >= 12 m above the scope ground, farther than 1 m from
GT dense (same selection as cv2_floater.py part 2). For each of this method (tl_30000), judgment off (cmp_nojudge_30000_v203) and image-only 2DGS
(cmp_2dgs_30000_v203): their area, the east-half share, the area within 0.25 / 0.5 m of the prior ALS surface (defs prior_ALS.npz, open3d distance), and the
area within 1 m (xy) of the edge floaters of this method (same place or not).
For this method's edge floaters also: the judgment of the nearest valid target (FT targets, judge_region) when one lies within 0.5 m of the face centre.
GT is used only to tell on-surface from off-surface faces. scientific_verdict: null"""
from cv2_frames import *
from shapely.geometry import shape
from scipy.spatial import cKDTree
OUTF = FIGD/'floater_check'

def area(V, F): a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; return .5*np.linalg.norm(np.cross(a, b), axis=1)

def main():
    t0 = time.monotonic(); c = cfg(); S = Static(); sj = json.loads((V2/'static.json').read_text()); g0 = S.ground
    fp = shape(c['scope']['footprint']); cx, cy = fp.centroid.x, fp.centroid.y
    G = loadz(Path(sj['gt']), ['xyz'])['xyz'].astype(float); T = cKDTree(G)
    pr = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F']); sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh()
    tm.vertex.positions = o3d.core.Tensor(pr['V'].astype('f4')); tm.triangle.indices = o3d.core.Tensor(pr['F'].astype('i4')); sc.add_triangles(tm)
    tg = loadz(FT/'targets'/f'{STEM}.npz', ['target', 'normal', 'sigma', 'judge_region', 'region'])
    valid = (tg['region'] >= 0) & np.isfinite(tg['target']).all(1) & np.isfinite(tg['sigma']) & (tg['sigma'] > 0); TT = cKDTree(tg['target'][valid]); JR = tg['judge_region'][valid]
    rec = dict(at=now(), rule=__doc__, meshes={}, scientific_verdict=None); ours_xy = None
    for name, p in [('ours_30000', O/'gtj/meshes'/f'{STEM}__tl_30000'/'final.ply'), ('nojudge_30000', V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_30000_v203'/'final.ply'),
                    ('2dgs_30000', V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_30000_v203'/'final.ply')]:
        m = o3d.io.read_triangle_mesh(str(p)); V = np.asarray(m.vertices, float); F = np.asarray(m.triangles).astype('i8'); del m
        ctr = V[F].mean(1); h = ctr[:, 2]-g0; de = shapely.distance(fp, shapely.points(ctr[:, 0], ctr[:, 1])); cand = (de > 0) & (de <= 3) & (h >= 12)
        dg, _ = T.query(ctr[cand], k=1); idx = np.flatnonzero(cand)[dg > 1.0]; Q = ctr[idx]; A = area(V, F[idx])
        ang = np.degrees(np.arctan2(Q[:, 1]-cy, Q[:, 0]-cx)) % 360; east = (ang < 90) | (ang >= 270)
        dp = sc.compute_distance(o3d.core.Tensor(Q.astype('f4'))).numpy()
        r = dict(mesh=str(p), mesh_sha256=sha(p), edge_floater_area_m2=round(float(A.sum()), 1), east_share_pct=round(float(100*A[east].sum()/max(A.sum(), 1e-9)), 1),
                 within_0p25m_of_prior_pct=round(float(100*A[dp <= .25].sum()/max(A.sum(), 1e-9)), 1), within_0p5m_of_prior_pct=round(float(100*A[dp <= .5].sum()/max(A.sum(), 1e-9)), 1),
                 prior_distance_median_m=round(float(np.median(dp)), 3), height_above_ground_p10_p50_p90=np.percentile(h[idx], [10, 50, 90]).round(2).tolist())
        if name == 'ours_30000':
            ours_xy = cKDTree(Q[:, :2]); dt, it = TT.query(Q, k=1); near = dt <= .5
            r['nearest_target_within_0p5m_area_pct'] = round(float(100*A[near].sum()/max(A.sum(), 1e-9)), 1)
            r['nearest_target_judgment_area_pct'] = {JN.get(int(j), str(int(j))): round(float(100*A[near & (JR[it] == j)].sum()/max(A[near].sum(), 1e-9)), 1) for j in np.unique(JR[it[near]])}
        else:
            d2, _ = ours_xy.query(Q[:, :2], k=1); r['same_place_as_ours_within_1m_xy_pct'] = round(float(100*A[d2 <= 1].sum()/max(A.sum(), 1e-9)), 1)
        rec['meshes'][name] = r; print('SRC', name, json.dumps(r, ensure_ascii=False), flush=True); del V, F, ctr
    rec['seconds'] = round(time.monotonic()-t0, 1); OUTF.mkdir(parents=True, exist_ok=True); dump(OUTF/'floater_source.json', rec); print('DONE', rec['seconds'], flush=True)

if __name__ == '__main__': main()
