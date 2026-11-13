"""Work ma (order 5): what is at the edge floaters of B173nb_b10 x ALS (CPU).
  points  : edge-floater faces (TRAINLOG floater_check rule) of the TRAINLOG tl_30000 uncut mesh and the control faces; image-depth points (all finite > 0 MVS
            pixels of every training view before the confidence mask, own FINALTRAIN camera) and SfM points (image points of the training initial cloud)
            within 0.3 / 1 m of each face vertex -> addendum3/ma/points.npz, tables/ma_points.csv
  photos  : two training views east of the floater centroid (elevation 20-60 deg), original and projected floater vertices (no occlusion test) -> figures/ma_photo_*.png
  states  : TRAINLOG record run tl_B173nb_b10_ALS_s0 attempt2 scene states: Gaussians within 0.5 m of edge-floater face centres per saved state -> tables/ma_states.csv"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
import time
MA = A3O/'ma'; STEM = 'B173nb_b10__ALS'; SITE = 'B173nb_b10'
TLM = PH/'main_trainlog_v1/PHD-MAIN-TRAINLOG-v1'; MESH = TLM/'gtj/meshes/B173nb_b10__ALS__tl_30000/final.ply'
RUN = TLM/'runs/B173nb_b10/tl_B173nb_b10_ALS_s0/attempt2/model'; SC = Path('/s0/fork_inputs/s61')/SITE

def faces():
    import shapely
    from shapely.geometry import shape
    c = json.loads((R/'configs/phd/main_trainlog_v1/trainlog_v1.json').read_text())['scope']; fp = shape(c['footprint']); g0 = float(c['ground_z'])
    m = o3d.io.read_triangle_mesh(str(MESH)); V = np.asarray(m.vertices, 'f8'); F = np.asarray(m.triangles).astype('i8'); del m
    ctr = V[F].mean(1); a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; A = .5*np.linalg.norm(np.cross(a, b), axis=1); h = ctr[:, 2]-g0
    de = shapely.distance(fp, shapely.points(ctr[:, 0], ctr[:, 1])); G = loadz(GT/'reference'/SITE/'dense.npz', ['xyz'])['xyz'].astype('f8'); T = cKDTree(G)
    dg = np.full(len(F), np.nan); q = (h >= 12) & (de <= 3); dg[q] = T.query(ctr[q])[0]
    edge = (de > 0) & (de <= 3) & (h >= 12) & (dg > 1.); ctrl = (de == 0) & (h >= 12) & (dg <= .2)
    return V, F, ctr, A, edge, ctrl, dict(footprint_area_m2=fp.area, ground_z=g0, mesh=str(MESH), mesh_sha256=sha(MESH), edge_faces=int(edge.sum()), edge_area_m2=float(A[edge].sum()),
                                          control_faces=int(ctrl.sum()), control_area_m2=float(A[ctrl].sum()))

def points():
    MA.mkdir(parents=True, exist_ok=True); t0 = time.monotonic(); V, F, ctr, A, edge, ctrl, info = faces()
    ve = np.unique(F[edge]); vc = np.unique(F[ctrl]); rng = np.random.default_rng(20261114)
    if len(vc) > 200000: vc = np.sort(rng.choice(vc, 200000, replace=False))
    Q = np.r_[V[ve], V[vc]]; lo = Q.min(0)-1.; hi = Q.max(0)+1.
    md = maps_dir(STEM, 'own'); index = json.loads((md/'index.json').read_text())['views']; img = []; nviews = 0
    for nm, mi in sorted(index.items()):
        d = np.load(SC/'maps/mvs'/f'{nm}.npy'); v, u = np.nonzero(np.isfinite(d) & (d > 0)); z = d[v, u].astype('f8'); K = np.asarray(mi['K']); E = np.asarray(mi['W2C'])
        Pc = np.c_[(u-K[0, 2])/K[0, 0]*z, (v-K[1, 2])/K[1, 1]*z, z]; Pw = (Pc-E[:3, 3])@E[:3, :3]; k = np.all((Pw >= lo) & (Pw <= hi), 1)
        if k.any(): img.append(Pw[k].astype('f4'))
        nviews += 1
    I = np.concatenate(img) if img else np.zeros((0, 3), 'f4'); TI = cKDTree(I)
    pc = o3d.io.read_point_cloud(str(SC/'scene_ALS/sparse/0/points3D.ply')); P = np.asarray(pc.points); org = np.load(SC/'scene_ALS/sparse/0/origin.npy'); assert len(org) == len(P)
    sfm = P[org == 0]   # origin 0 = image (SfM) points of the training initial cloud, 1 = ALS prior points
    TS = cKDTree(sfm) if len(sfm) else None; out = {}; rows = []
    for nm, vv in [('edge_floater', V[ve]), ('control', V[vc])]:
        r = dict(set=nm, vertices=len(vv))
        for rad in [.3, 1.]:
            ci = np.array([len(q) for q in TI.query_ball_point(vv, rad, workers=8)]) if len(I) else np.zeros(len(vv), int)
            cs = np.array([len(q) for q in TS.query_ball_point(vv, rad, workers=8)]) if TS is not None else np.zeros(len(vv), int)
            r[f'image_point_within_{rad}m_pct'] = pct(ci > 0); r[f'image_points_within_{rad}m_median'] = med(ci); r[f'sfm_point_within_{rad}m_pct'] = pct(cs > 0)
            out[f'{nm}_image_{rad}'] = ci.astype('i4'); out[f'{nm}_sfm_{rad}'] = cs.astype('i4')
        rows.append(r)
    savez(MA/'points.npz', edge_vertices=V[ve].astype('f4'), control_vertices=V[vc].astype('f4'), edge_face_centres=ctr[edge].astype('f4'), edge_face_area=A[edge].astype('f4'), **out)
    ctable('ma_points', rows); dump(MA/'points.json', dict(at=now(), **info, image_points_in_box=len(I), views=nviews, sfm_points=len(sfm), sfm_rule='image points of the training initial cloud scene_ALS/sparse/0/points3D.ply (origin.npy == 0)',
                                                          control_vertices_sampled=len(vc), seconds=time.monotonic()-t0, rows=rows, scientific_verdict=None))
    print('MA_POINTS', info, rows, len(I), len(sfm), flush=True)

def photos():
    from PIL import Image
    plt = korean_plt(); z = loadz(MA/'points.npz'); Q = z['edge_vertices'].astype('f8'); c0 = Q.mean(0); md = maps_dir(STEM, 'own'); index = json.loads((md/'index.json').read_text())['views']; cand = []
    for nm, mi in index.items():
        K = np.asarray(mi['K']); E = np.asarray(mi['W2C']); C = -E[:3, :3].T@E[:3, 3]; dv = C-c0; el = np.degrees(np.arctan2(dv[2], np.linalg.norm(dv[:2])))
        if not (C[0] > c0[0] and 20 <= el <= 60): continue
        X = Q@E[:3, :3].T+E[:3, 3]; zz = X[:, 2]; ok = zz > .1; zs = np.where(ok, zz, 1.); u = K[0, 0]*X[:, 0]/zs+K[0, 2]; v = K[1, 1]*X[:, 1]/zs+K[1, 2]
        ins = ok & (u >= 20) & (u < 1024-20) & (v >= 20) & (v < 741-20); cand.append((int(ins.sum()), nm, u, v, ins, float(el), float(np.degrees(np.arctan2(dv[1], dv[0])))))
    cand.sort(key=lambda t: -t[0]); used = []
    for n, nm, u, v, ins, el, az in cand[:2]:
        im = Image.open(SC/'images'/f'{nm}.jpg').convert('RGB'); sx = im.size[0]/1024; ph = np.asarray(im); uu, vv = u[ins]*sx, v[ins]*sx; pad = 120*sx
        x0, x1 = max(0, uu.min()-pad), min(im.size[0], uu.max()+pad); y0, y1 = max(0, vv.min()-pad), min(im.size[1], vv.max()+pad)
        fig, axs = plt.subplots(1, 2, figsize=(14, 6.5), dpi=110)
        for j, ax in enumerate(axs):
            ax.imshow(ph); ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_xticks([]); ax.set_yticks([])
            if j: ax.scatter(uu, vv, s=1.2, c='#FF00FF', alpha=.4, lw=0)
        axs[0].set_title('원본', fontsize=10); axs[1].set_title('뜬 면 꼭짓점 투영(분홍)', fontsize=10); fig.tight_layout()
        p = A3D/'figures'/f'ma_photo_{nm}.png'; fig.savefig(p, facecolor='white', bbox_inches='tight', pad_inches=.2); plt.close(fig)
        rec = dict(view=nm, projected_vertices_inside=n, elevation_deg=el, azimuth_from_floater_deg=az, crop_xyxy=[float(x0), float(y0), float(x1), float(y1)], image=str(SC/'images'/f'{nm}.jpg'),
                   rule='camera centre east of the floater centroid, elevation 20-60 deg; top 2 by projected edge-floater vertices inside the image (20 px margin); no occlusion test', scientific_verdict=None)
        dump(p.with_suffix('.json'), rec); used.append(rec)
    ctable('ma_photo_views', used); print('MA_PHOTOS', used, flush=True)

def states():
    import torch
    z = loadz(MA/'points.npz'); C = z['edge_face_centres'].astype('f8'); TC = cKDTree(C); lo = C.min(0)-.6; hi = C.max(0)+.6; rows = []
    for s in saves(RUN):
        S = load_state(RUN, s['name'], 'scene'); k = np.flatnonzero(np.all((S['xyz'] >= lo) & (S['xyz'] <= hi), 1)); d, _ = TC.query(S['xyz'][k]); g = k[d <= .5]
        tg = S['tag'][g]; rows.append(dict(name=s['name'], iteration=s['iteration'], gaussians=len(g), opacity_median=med(S['opacity'][g]), opacity_ge05_pct=pct(S['opacity'][g] >= .5) if len(g) else None,
                                           opacity_sum=float(S['opacity'][g].sum()), size_median_m=med(S['size'][g]), bound=int((tg == 1).sum()), released=int((tg == 2).sum()), background=int((tg == 0).sum())))
        print('MA_STATE', rows[-1], flush=True)
    ctable('ma_states', rows)

if __name__ == '__main__':
    {'points': points, 'photos': photos, 'states': states}[sys.argv[1]]()
