"""Step-6 look (2026-11-13, user: 'show me the B0 x LoD2 glass wall in photos first'). Read-only; writes docs figures_concept_v2/step6_find/<scene>_look.png
and .json only. No training, no meshing.
Case rows = GTJUDGE GT rows of the scene (rows.npz) that are wall rows with the prior right (present, distance <= TAU) and the image depth (MVS) wrong
(absent or > 0.5 m) = the step-6 case 'image depth wrong, prior right'. Scored by the 30,000 meshes of GTJUDGE distances (FINALTRAIN_30000 this method,
2DGS_30000 image only, mvs image-depth mesh, prior prior surface): completeness |row_s| <= row_tau_m.
Views = the site's training cameras (GTJUDGE views/<site>.json, 1024 x 741 grid = fork_inputs images). A case row counts for a view when it projects inside
the image, faces the camera (row normal . (camera - row) > 0, angle <= 75 deg) and is not hidden by the prior mesh (ray to the row hits the prior surface no
earlier than 0.5 m before it) and (r3) is not hidden in the view's MVS depth map (7 x 7 window median more than OCC m nearer); shown views only from cameras within NEAR_M of the rows (median); the
full photo carries the prior (LoD2) mesh edges in cyan to check the projection. r2 (after the first look: the rows are not one glass wall): cluster A = case rows in 4 m xy cells holding >= DENSE case rows, B = the rest;
for each, the view with the most counted rows of it, shown as a crop without and with the rows marked (r3: dots = rows counted for the view, dashed = hull of where all its rows project, hidden or not); plus a top view (A red, B orange, view arrows). GT is used only to pick and to draw the rows. scientific_verdict: null"""
import sys
from cv2_frames import *
from shapely.geometry import MultiPoint
SCENES = {'B0_b10__LoD2': dict(site='B0_b10', prior='LoD2')}; DENSE = 200; OCC = 3.0; NEAR_M = 70.0   # case rows per 4 m cell for cluster A (the dense part); B = the scattered rest
OUTD = FIGD/'step6_find'; IMGD = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'

def main(stem):
    t0 = time.monotonic(); sc = SCENES[stem]; site = sc['site']; MAPS = IMGD/site/'maps'
    import importlib.util
    spec = importlib.util.spec_from_file_location('nl', '/repo/scripts/phd/main_gtjudge_v1/normal_line.py'); nl = importlib.util.module_from_spec(spec); spec.loader.exec_module(nl)
    row = loadz(GT/'scenes'/stem/'rows.npz', ['xyz', 'normal', 'row_tau_m', 'prior_distance_m', 'prior_presence', 'mvs_distance_m', 'mvs_presence', 'wall'])
    X = row['xyz'].astype(float); Nr = row['normal'].astype(float); tau = row['row_tau_m']; wall = row['wall'].astype(bool)
    pr = row['prior_presence'].astype(bool) & (row['prior_distance_m'] <= TAU); mw = ~row['mvs_presence'].astype(bool) | (row['mvs_distance_m'] > .5)
    case = wall & pr & mw; ci = np.flatnonzero(case)
    gd = GT/'scenes'/stem/'distances'; fams = dict(ours='FINALTRAIN_30000', twodgs='2DGS_30000', image_depth_mesh='mvs', prior_surface='prior')
    rs = {k: loadz(gd/f'{f}.npz', ['row_s'])['row_s'] for k, f in fams.items()}
    comp = {k: round(float(nl.values(v[case], tau[case])['within_pct']), 1) for k, v in rs.items()}
    ij = np.floor(X[ci, :2]/4).astype(int); keys, inv, cnt = np.unique(ij, axis=0, return_inverse=True, return_counts=True); dense = cnt[inv.ravel()] >= DENSE
    cl = {'A': ci[dense], 'B': ci[~dense]}; cmask = {k: np.isin(np.arange(len(X)), v) for k, v in cl.items()}
    clrec = {k: dict(rows=int(len(v)), cells=[((keys[i]+.5)*4).tolist() for i in np.flatnonzero(cnt >= DENSE)] if k == 'A' else None, height_m=np.percentile(X[v, 2], [5, 50, 95]).round(2).tolist() if len(v) else None,
                     image_depth_absent_pct=round(float(100*np.mean(~row['mvs_presence'].astype(bool)[v])), 1) if len(v) else None,
                     completeness_30000_pct={f: round(float(nl.values(a[cmask[k]], tau[cmask[k]])['within_pct']), 1) for f, a in rs.items()} if len(v) else None) for k, v in cl.items()}
    pm = loadz(S1/'defs'/site/f"prior_{sc['prior']}.npz", ['V', 'F']); scene = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh()
    tm.vertex.positions = o3d.core.Tensor(np.ascontiguousarray(pm['V'], 'f4')); tm.triangle.indices = o3d.core.Tensor(np.ascontiguousarray(pm['F'], 'i4')); scene.add_triangles(tm)
    views = [v for v in json.loads((GT/'views'/f'{site}.json').read_text())['views'] if not v['virtual']]
    P = X[ci]; N = Nr[ci]; res = []
    for v in views:
        K = np.asarray(v['K'], float); E = np.asarray(v['W2C'], float); C = -E[:3, :3].T@E[:3, 3]
        Xc = P@E[:3, :3].T+E[:3, 3]; z = Xc[:, 2]; u = K[0, 0]*Xc[:, 0]/np.maximum(z, 1e-6)+K[0, 2]; w = K[1, 1]*Xc[:, 1]/np.maximum(z, 1e-6)+K[1, 2]
        d = C-P; dn = np.linalg.norm(d, axis=1); cosang = np.abs(np.einsum('ij,ij->i', N, d))/dn   # wall normals: sign not oriented, use |cos|
        ok = (z > 0) & (u >= 0) & (u < 1024) & (w >= 0) & (w < 741) & (cosang >= np.cos(np.radians(75)))
        if ok.sum() < 20: continue
        q = np.flatnonzero(ok); ray = np.c_[np.broadcast_to(C, (len(q), 3)), -d[q]/dn[q, None]].astype('f4')
        th = scene.cast_rays(o3d.core.Tensor(ray))['t_hit'].numpy(); vis = ~(th < dn[q]-.5); ok[q[~vis]] = False
        # r3: the prior mesh holds only the scene's buildings; a nearer building outside the box can still hide the rows -> the view's MVS depth map
        # (fork_inputs maps/mvs): hidden when the median valid depth in a 7 x 7 window is more than OCC m nearer than the row
        dm = np.load(MAPS/'mvs'/f"{v['name']}.npy").astype(float); q = np.flatnonzero(ok); ui = np.clip(u[q].astype(int), 3, dm.shape[1]-4); wi = np.clip(w[q].astype(int), 3, dm.shape[0]-4)
        win = np.stack([dm[wi+dy, ui+dx] for dy in range(-3, 4) for dx in range(-3, 4)], 1); win = np.where(np.isfinite(win) & (win > 0), win, np.nan)
        known = np.isfinite(win).any(1); med = np.nanmedian(np.where(known[:, None], win, np.inf), 1); hid = known & (med < z[q]-OCC); ok[q[hid]] = False
        if ok.sum() < 20: continue
        az = float(np.degrees(np.arctan2(*(C[:2]-P[:, :2].mean(0))[::-1])) % 360)
        isA = np.isin(ci, cl['A'])
        res.append(dict(name=v['name'], n=int(ok.sum()), nA=int((ok & isA).sum()), nB=int((ok & ~isA).sum()), dist_m=round(float(np.median(dn[ok])), 1), azimuth_deg=round(az, 1), camera_xyz=C.tolist(), uv=np.c_[u[ok], w[ok]].tolist(),
                        uvA=np.c_[u[ok & isA], w[ok & isA]].tolist(), uvB=np.c_[u[ok & ~isA], w[ok & ~isA]].tolist(), mean_cos=round(float(cosang[ok].mean()), 2)))
    res.sort(key=lambda r: -r['n']); pick = []
    for r in res:
        if all(min(abs(r['azimuth_deg']-p['azimuth_deg']), 360-abs(r['azimuth_deg']-p['azimuth_deg'])) >= 30 for p in pick): pick.append(r)
        if len(pick) == 3: break
    # figure (r2: dense cluster A and scattered B shown apart, each as a crop of its best photo without and with marks)
    ORG = '#E8A33D'; near = [r for r in res if r['dist_m'] <= NEAR_M] or res   # r3: far cameras (> NEAR_M) look across other buildings outside the box
    bestA = max(near, key=lambda r: r['nA']) if near else None; bestB = max(near, key=lambda r: r['nB']) if near else None
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor='white')
    ax = fig.add_axes([.01, .06, .22, .86]); ax.scatter(X[::7, 0], X[::7, 1], s=.3, c='#C9C7BE', lw=0, rasterized=True)
    for k, col in (('B', ORG), ('A', RED)):
        Q = X[cl[k]]; ax.scatter(Q[:, 0], Q[:, 1], s=2 if k == 'A' else 1.5, c=col, lw=0, rasterized=True)
        if len(Q): ax.text(*(np.median(Q[:, :2], 0)+np.array([-6, 0])), k, fontsize=15, color=col, fontweight='bold', ha='center', va='center')
    for lab, p in (('A', bestA), ('B', bestB)):
        if p is None: continue
        C = np.asarray(p['camera_xyz']); m = np.median(X[cl[lab], :2], 0); dv = C[:2]-m; dv = dv/np.linalg.norm(dv)
        ax.annotate('', xy=m+5*dv, xytext=m+15*dv, arrowprops=dict(arrowstyle='-|>', color=NAVY, lw=1.8)); ax.text(*(m+17.5*dv), f'{lab}', fontsize=11, color='white', ha='center', va='center', fontweight='bold', bbox=dict(boxstyle='round,pad=.25', fc=NAVY, ec='white'))
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([]); ax.set_title('위에서 본 B0 · 빨강 A·주황 B = 사진 깊이 틀림·LoD2 맞음 벽', fontsize=10, color=NAVY, loc='left')
    y0 = ax.get_ylim()[0]; x1 = ax.get_xlim()[1]; ax.plot([x1-12, x1-2], [y0+3]*2, color='k', lw=2); ax.text(x1-7, y0+4.2, '10 m', ha='center', fontsize=9)
    def crop(p, key, row, col, label):
        im = np.asarray(Image.open(IMGD/site/'images'/f"{p['name']}.jpg").convert('RGB')); uv = np.asarray(p[key]); H, W = im.shape[:2]
        vw = [x for x in views if x['name'] == p['name']][0]; K = np.asarray(vw['K'], float); E = np.asarray(vw['W2C'], float); Q = X[cl[key[-1]]]@E[:3, :3].T+E[:3, 3]; Q = Q[Q[:, 2] > 1]
        allv = np.c_[K[0, 0]*Q[:, 0]/Q[:, 2]+K[0, 2], K[1, 1]*Q[:, 1]/Q[:, 2]+K[1, 2]]; hull = np.asarray(MultiPoint(allv).convex_hull.exterior.coords) if len(allv) >= 3 else None   # r3: where all its rows project, seen or not
        both = np.r_[uv, allv] if len(allv) else uv; lo, hi = np.percentile(both, 1, axis=0), np.percentile(both, 99, axis=0); c = (lo+hi)/2; half = np.maximum((hi-lo)/2+70, [190, 140])
        u0, u1 = int(max(c[0]-half[0], 0)), int(min(c[0]+half[0], W)); w0, w1 = int(max(c[1]-half[1], 0)), int(min(c[1]+half[1], H))
        a = fig.add_axes([.245, .52-row*.47, .245, .40]); a.imshow(im); a.set_xticks([]); a.set_yticks([]); a.set_xlim(0, W); a.set_ylim(H, 0)
        vw = [x for x in views if x['name'] == p['name']][0]; K = np.asarray(vw['K'], float); E = np.asarray(vw['W2C'], float); PV = np.asarray(pm['V'], float)@E[:3, :3].T+E[:3, 3]
        ed = np.asarray(pm['F'])[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2); zz = PV[ed, 2]; okk = (zz > 1).all(1); uvv = np.stack([K[0, 0]*PV[ed, 0]/np.maximum(zz, 1e-6)+K[0, 2], K[1, 1]*PV[ed, 1]/np.maximum(zz, 1e-6)+K[1, 2]], -1)[okk]
        a.add_collection(LineCollection(uvv, colors='#00E5FF', linewidths=.25, alpha=.35))   # prior (LoD2) mesh edges: projection check
        a.plot([u0, u1, u1, u0, u0], [w0, w0, w1, w1, w0], color='white', lw=2.4); a.plot([u0, u1, u1, u0, u0], [w0, w0, w1, w1, w0], color=col, lw=1.3)
        a.set_title(f"{label} · 사진 전체 · {p['name']}", fontsize=11, color=NAVY, loc='left')
        for j, marks in enumerate((False, True)):
            a = fig.add_axes([.50+j*.25, .52-row*.47, .245, .40]); a.imshow(im[w0:w1, u0:u1], extent=(u0, u1, w1, w0)); a.set_xticks([]); a.set_yticks([])
            if marks:
                if hull is not None: a.plot(hull[:, 0], hull[:, 1], color='white', lw=2.2, ls=(0, (4, 3))); a.plot(hull[:, 0], hull[:, 1], color=col, lw=1.2, ls=(0, (4, 3)))
                a.scatter(uv[:, 0], uv[:, 1], s=4, c=col, lw=0, alpha=.8)
            a.set_xlim(u0, u1); a.set_ylim(w1, w0); a.set_title(f"{label} · 확대 · " + ('점 = 이 사진에 보이는 행, 점선 = 모든 행이 놓이는 자리' if marks else '표시 없음'), fontsize=11, color=NAVY, loc='left')
        return [u0, w0, u1, w1]
    crops = {}
    if bestA is not None and bestA['nA']: crops['A'] = crop(bestA, 'uvA', 0, RED, 'A 몰린 곳')
    if bestB is not None and bestB['nB']: crops['B'] = crop(bestB, 'uvB', 1, ORG, 'B 흩어진 곳')
    OUTD.mkdir(parents=True, exist_ok=True); png = OUTD/f'{stem}_look.png'; fig.savefig(png, dpi=100, facecolor='white'); plt.close(fig)
    hull = MultiPoint(P[:, :2]).convex_hull
    rec = dict(at=now(), rule=__doc__, scientific_verdict=None, scene=stem, case_rows=int(case.sum()), wall_rows=int(wall.sum()), case_completeness_30000_pct=comp,
               case_height_m=np.percentile(P[:, 2], [5, 50, 95]).round(2).tolist(), case_xy_bounds=list(np.round(hull.bounds, 1)), case_area_hull_m2=round(hull.area, 1),
               views_considered=len(views), views_with_case=len(res), clusters=clrec, dense_cell_rows=DENSE, best_view_A=bestA and {k: v for k, v in bestA.items() if not k.startswith('uv')}, best_view_B=bestB and {k: v for k, v in bestB.items() if not k.startswith('uv')}, crops_uv=crops,
               top10=[{k: v for k, v in r.items() if not k.startswith('uv')} for r in res[:10]],
               png=str(png), png_sha256=sha(png), seconds=round(time.monotonic()-t0, 1))
    dump(OUTD/f'{stem}_look.json', rec); print('LOOK', json.dumps({k: rec[k] for k in ('case_rows', 'case_completeness_30000_pct', 'clusters', 'best_view_A', 'best_view_B')}, ensure_ascii=False), flush=True)
    for r in sorted(near, key=lambda r: -r['nA'])[:8]: print('NEARVIEW', r['name'], r['n'], r['nA'], r['nB'], r['dist_m'], r['azimuth_deg'], flush=True)
    for r in sorted(res, key=lambda r: -r['nA'])[:12]: print('VIEW', r['name'], r['n'], r['nA'], r['nB'], r['dist_m'], r['azimuth_deg'], flush=True)

if __name__ == '__main__': main(sys.argv[1] if len(sys.argv) > 1 else 'B0_b10__LoD2')
