"""Concept video v2 side check (2026-11-13, user request): what are the floating mesh pieces outside the building (east edge, roof height) seen in ② of the frames.
Read-only on all inputs; no training, no meshing, no scoring change. Writes docs figures_concept_v2/floater_check/ (floater_check.json, floater_map.png, floater_photos.png).
  1. uncut meshes (the original-rule final.ply before the building-scope cut: this method tl_30000 and judgment off cmp_nojudge_30000_v203):
     face area by planar distance outside the LoD2 footprint (0 inside; 0-1 m = the 1 m buffer kept in the frames; 1-3, 3-10, >10 m) x height above
     the scope ground (<0.3 m = below the scope z_min, 0.3-12 m, >=12 m), east half share, and the area farther than 1 m from GT dense.
  2. the largest concentration of this method's roof-height floaters = off-GT (>1 m) faces outside the footprint by at most 3 m and >= 12 m above
     the scope ground (5 m bins along the footprint edge, the top bin and its two neighbours; first run without the 3 m / 12 m limits picked the bare
     ground 14 m north of the building, which GT does not cover) projected into the real training views (render receipt K, W2C; pixel centre at integer u); the three views with the most projected points
     inside the image (20 px margin), photo crops plain and with the projected points.
GT is used only to tell on-surface from off-surface faces (distance). scientific_verdict: null"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainlog_v1')
from cv2_frames import *
from shapely.geometry import shape
from scipy.spatial import cKDTree
OUT = FIGD/'floater_check'; IMG = Path('/p/fork_inputs/s61')/SITE/f'scene_{PRIOR}'/'images'

def area(V, F): a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; return .5*np.linalg.norm(np.cross(a, b), axis=1)

def main():
    t0 = time.monotonic(); OUT.mkdir(parents=True, exist_ok=True)
    c = cfg(); S = Static(); sj = json.loads((V2/'static.json').read_text()); g0 = S.ground
    fp = shape(c['scope']['footprint']); cx, cy = fp.centroid.x, fp.centroid.y
    G = loadz(Path(sj['gt']), ['xyz'])['xyz'].astype(float); T = cKDTree(G)
    rr = json.loads((O/'gtj/renders'/f'{STEM}__tl_30000'/'receipt.json').read_text())
    rec = dict(at=now(), rule=__doc__, render_box=rr['box'], footprint_area_m2=fp.area, scope_xy_buffer_m=c['scope']['xy_buffer_m'], meshes={}, scientific_verdict=None)
    keep = None
    for name, p in [('ours_30000', O/'gtj/meshes'/f'{STEM}__tl_30000'/'final.ply'), ('nojudge_30000', V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_30000_v203'/'final.ply')]:
        m = o3d.io.read_triangle_mesh(str(p)); V = np.asarray(m.vertices, float); F = np.asarray(m.triangles).astype('i8'); del m
        ctr = V[F].mean(1); A = area(V, F); h = ctr[:, 2]-g0
        de = shapely.distance(fp, shapely.points(ctr[:, 0], ctr[:, 1])); ang = np.degrees(np.arctan2(ctr[:, 1]-cy, ctr[:, 0]-cx)) % 360; east = (ang < 90) | (ang >= 270)
        dg = np.full(len(F), np.nan); o = de > 0; dg[o], _ = T.query(ctr[o], k=1); off = o & (dg > 1.0)
        bins = [('inside', de == 0), ('out_0_1m', (de > 0) & (de <= 1)), ('out_1_3m', (de > 1) & (de <= 3)), ('out_3_10m', (de > 3) & (de <= 10)), ('out_gt10m', de > 10)]
        hb = [('h_lt0.3', h < .3), ('h_0.3_12', (h >= .3) & (h < 12)), ('h_ge12', h >= 12)]
        tab = {bn: {hn: round(float(A[bs & hs].sum()), 1) for hn, hs in hb} for bn, bs in bins}
        r = dict(mesh=str(p), mesh_sha256=sha(p), faces=int(len(F)), area_m2=round(float(A.sum()), 1), area_by_distance_outside_footprint_and_height_m2=tab,
                 outside_area_m2=round(float(A[o].sum()), 1), outside_off_gt_1m_area_m2=round(float(A[off].sum()), 1), outside_off_gt_east_share_pct=round(float(100*A[off & east].sum()/max(A[off].sum(), 1e-9)), 1),
                 outside_max_distance_m=round(float(de.max()), 2), vertex_bbox_min=V.min(0).tolist(), vertex_bbox_max=V.max(0).tolist())
        rec['meshes'][name] = r; print('MESH', name, json.dumps(r)[:900], flush=True)
        if name == 'ours_30000':
            off_all = off; off = off & (de <= 3) & (h >= 12)   # roof-height floaters hugging the building
            pos = shapely.line_locate_point(fp.exterior, shapely.points(ctr[off, 0], ctr[off, 1])); L = fp.exterior.length; nb = int(np.ceil(L/5))
            hist = np.bincount(np.minimum((pos/5).astype(int), nb-1), weights=A[off], minlength=nb); top = int(np.argmax(hist))
            sel = np.isin(np.minimum((pos/5).astype(int), nb-1), [(top-1) % nb, top, (top+1) % nb])
            keep = dict(P=ctr[off][sel], A=A[off][sel], h=h[off][sel], de=de[off][sel])
            rec['concentration'] = dict(edge_bin_m=5, top_bin=top, top_bins_area_m2=round(float(A[off][sel].sum()), 1), share_of_off_gt_outside_pct=round(float(100*A[off][sel].sum()/A[off].sum()), 1),
                                        centroid_xyz=keep['P'].mean(0).tolist(), height_above_ground_median_m=float(np.median(keep['h'])), distance_outside_footprint_median_m=float(np.median(keep['de'])),
                                        distance_outside_footprint_max_m=float(keep['de'].max()))
            # map: plan view of all outside off-GT faces coloured by height, footprint, GT
            fig, ax = plt.subplots(figsize=(9, 9), dpi=110); g = G[::40]; ax.scatter(g[:, 0], g[:, 1], s=.2, c='#B4B2A9', lw=0, rasterized=True)
            mm = off_all & (h >= .3); q = ctr[mm]; sc = ax.scatter(q[:, 0], q[:, 1], s=.3, c=np.clip(h[mm], 0, 25), cmap='viridis', vmin=0, vmax=25, lw=0, rasterized=True)
            x, y = fp.exterior.xy; ax.plot(x, y, color=NAVY, lw=1.2); xb, yb = shape(c['scope']['buffered_footprint']).exterior.xy; ax.plot(xb, yb, color=NAVY, lw=.8, ls='--')
            pc = keep['P'].mean(0); ax.plot(pc[0], pc[1], 'x', color=RED, ms=10, mew=2); ax.set_aspect('equal'); ax.set_xlabel('x m (동 →)'); ax.set_ylabel('y m (북 →)')
            fig.colorbar(sc, ax=ax, shrink=.6, label='지면 위 높이 m'); ax.set_title('건물 밖, 참값에서 1 m 넘게 떨어진 메시 면, 지면 0.3 m 위 (본 방법 30,000회, 자르기 전)', fontsize=10)
            fig.savefig(OUT/'floater_map.png', bbox_inches='tight', facecolor='white'); plt.close(fig)
        del V, F, ctr, A
    # photos
    P = keep['P']; rs = np.random.default_rng(0).choice(len(P), min(4000, len(P)), replace=False); Q = P[rs]; views = []
    for v in rr['views']:
        if v.get('virtual', False): continue
        K = np.asarray(v['K']); E = np.asarray(v['W2C']); X = Q@E[:3, :3].T+E[:3, 3]; z = X[:, 2]; ok = z > .1; zz = np.where(ok, z, 1.)
        u = K[0, 0]*X[:, 0]/zz+K[0, 2]; w = K[1, 1]*X[:, 1]/zz+K[1, 2]; ins = ok & (u >= 20) & (u < v['width']-20) & (w >= 20) & (w < v['height']-20)
        views.append((int(ins.sum()), v['name'], u, w, ins, K, E, float(np.median(z[ins])) if ins.any() else np.nan))
    views.sort(key=lambda t: -t[0]); pick = views[:3]
    fig, axs = plt.subplots(3, 2, figsize=(12, 15), dpi=100); used = []
    for i, (n, nm, u, w, ins, K, E, zm) in enumerate(pick):
        im = Image.open(IMG/f'{nm}.jpg').convert('RGB'); sx = im.size[0]/rr['views'][0]['width']; ph = np.asarray(im)
        uu, ww = u[ins]*sx, w[ins]*sx; pad = 80*sx; x0, x1 = max(0, uu.min()-pad), min(im.size[0], uu.max()+pad); y0, y1 = max(0, ww.min()-pad), min(im.size[1], ww.max()+pad)
        for j in (0, 1):
            ax = axs[i, j]; ax.imshow(ph); ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_xticks([]); ax.set_yticks([])
            if j == 1: ax.scatter(uu, ww, s=1.5, c='#FF00FF', alpha=.35, lw=0)
        axs[i, 0].set_title(f'{nm} · 점 {n:,}개 · 거리 중앙값 {zm:.0f} m', fontsize=10, loc='left'); used.append(dict(name=nm, points_inside=n, depth_median_m=zm, image_size=list(im.size), crop_xyxy=[float(x0), float(y0), float(x1), float(y1)]))
    axs[0, 1].set_title('같은 자리 + 뜬 면 위치(분홍)', fontsize=10, loc='left')
    fig.tight_layout(); fig.savefig(OUT/'floater_photos.png', facecolor='white'); plt.close(fig)
    rec['photo_views'] = used; rec['photo_rule'] = 'top-3 real views by projected concentration points inside the image (20 px margin); points sampled 4,000 of the concentration'
    rec['seconds'] = round(time.monotonic()-t0, 1); dump(OUT/'floater_check.json', rec); print('DONE', rec['seconds'], json.dumps(rec['concentration']), used, flush=True)

if __name__ == '__main__': main()
