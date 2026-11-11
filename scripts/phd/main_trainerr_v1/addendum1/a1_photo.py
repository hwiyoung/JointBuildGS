"""Addendum 1 work 가 (order 3): real-photo figures of the four B0 places, own arm. CPU container.
Writes docs addendum1/figures/photo_<place>_<마주|비스듬>_<원본|점|결과|목표>.png + json, legend, tables/place_check, tables/photo_selection."""
from a1_common import *
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree
STEM, SITE, ARM = 'B0_b10__LoD2', 'B0_b10', 'own'
PLACES = ['south_wall_missing', 'south_wall_valid', 'annex_roof_edge', 'back_wall_bottom']
CASECOL = None
SIZE = (1600, 1280)
FIG = A1D/'figures'

def hexrgb(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))

def surface_image(path, cam, j, crop, ref, rtree, cy, wall_tau, roof_tau):
    """GTJUDGE addendum6 render rule on the crop pixels: first hit, oriented triangle normal, cylinder distance, palette."""
    sc = scene_ply(path); W, H = SIZE; fx, fy, cx, cy_ = cam.p[:4]; Rm, t = cam.R[j], cam.t[j]; C = -Rm.T@t
    ids = np.full((H, W), -1, 'i8'); signed = np.full((H, W), np.nan, 'f4'); tau = np.full((H, W), np.nan, 'f4')
    xs = crop[0]+(np.arange(W)+.5)*(crop[2]-crop[0])/W
    for y0 in range(0, H, 160):
        ys = crop[1]+(np.arange(y0, min(H, y0+160))+.5)*(crop[3]-crop[1])/H; X, Y = np.meshgrid(xs, ys)
        dc = np.stack([(X-cx)/fx, (Y-cy_)/fy, np.ones_like(X)], -1).reshape(-1, 3); dw = dc@Rm; dw /= np.linalg.norm(dw, axis=1)[:, None]
        rr = np.c_[np.broadcast_to(C, dw.shape), dw].astype('f4'); hit = sc.cast_rays(o3d.core.Tensor(rr)); dep = hit['t_hit'].numpy(); good = np.isfinite(dep)
        fi = hit['primitive_ids'].numpy().astype('i8'); fi[~good] = -1; h = min(H, y0+160)-y0; ids[y0:y0+h] = fi.reshape(h, W)
        if good.any():
            pt = rr[good, :3].astype(float)+dep[good, None]*rr[good, 3:]; n = hit['primitive_normals'].numpy()[good].astype(float); n /= np.linalg.norm(n, axis=1)[:, None]
            near = rtree.query(pt, workers=8)[1]; rn = ref['normal'][near]; n *= np.where((n*rn).sum(1) < 0, -1, 1)[:, None]; wl = ref['wall'][near].astype(bool)
            sv, _ = cy.query(pt, n, np.where(wl, 5., 10.), float(ref['radius'])); signed[y0:y0+h].reshape(-1)[good] = -sv; tau[y0:y0+h].reshape(-1)[good] = np.where(wl, wall_tau, roof_tau)
    del sc; return Image.fromarray(palette(ids, signed, tau)), int((ids >= 0).sum())

def cross(draw, p, s=14):
    x, y = p
    for col, w in [((0, 0, 0), 5), ((255, 255, 0), 2)]: draw.line([(x-s, y), (x+s, y)], fill=col, width=w); draw.line([(x, y-s), (x, y+s)], fill=col, width=w)

def main():
    c = acfg(); t0 = Timer('a1_photo'); FIG.mkdir(parents=True, exist_ok=True); CC = json.loads((R/'configs/phd/main_gtjudge_v1/addendum6.json').read_text())['case_colors']
    rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz', 'normal', 'wall', 'row_tau_m']); case = loadz(GT/'scenes'/STEM/'stage1_cells.npz', ['case_id'])['case_id']
    Nr = rows['normal']/np.linalg.norm(rows['normal'], axis=1)[:, None]
    # place check (order 0.2): GT wall points of each wall zone must sit at d ~ 0
    chk = []
    for which in ['south', 'long']:
        a, d, m = wall_coords(rows['xyz'], which); w = m & rows['wall'].astype(bool)
        nrm = wall_normal(which); cosn = np.abs(Nr[w]@nrm)
        chk.append(dict(wall=which, gt_rows_in_zone=int(m.sum()), wall_rows=int(w.sum()), d_median_m=float(np.median(d[w])) if w.any() else None,
                        d_p10=float(np.quantile(d[w], .1)) if w.any() else None, d_p90=float(np.quantile(d[w], .9)) if w.any() else None,
                        normal_agreement_median=float(np.median(cosn)) if w.any() else None, case0=int((m & (case == 0)).sum()), case4=int((m & (case == 4)).sum())))
    atable('place_check', chk)
    roof_tau, wall_tau = tau_of(SITE, 'LoD2')
    masks = {p: place_mask(rows['xyz'], p) for p in PLACES}; masks['south_wall_missing'] &= case == 4; masks['south_wall_valid'] &= case == 0
    scenes = blockers(STEM, ARM); sel_rows = []; choice = {}
    for p in PLACES:
        idx = np.flatnonzero(masks[p]); pr, info, _ = vis_a1(STEM, ARM, rows['xyz'][idx], Nr[idx], rows['row_tau_m'][idx], np.zeros(len(idx), bool), maps=False, scenes=scenes)
        names = [v['name'] for v in train_views(SITE)]; best = {}
        for grp, gm in [('마주', pr['facing'] == 1), ('비스듬', pr['facing'] == 0)]:
            cnt = np.bincount(pr['view'][gm], minlength=len(names))
            if cnt.max() > 0:
                order = sorted(range(len(names)), key=lambda k: (-cnt[k], names[k])); best[grp] = (names[order[0]], int(cnt[order[0]]))
            sel_rows.append(dict(place=p, group=grp, place_gt_rows=len(idx), image=best.get(grp, (None,))[0], seen_place_points=best.get(grp, (None, 0))[1], blocked_pairs_all_views=info['blocked_pairs']))
        choice[p] = (idx, best)
    atable('photo_selection', sel_rows)
    cam = cameras(SITE); ref = loadz(GT/'reference'/SITE/'dense.npz'); rtree = cKDTree(ref['xyz']); Cy = cylinder_module(); cy = Cy.Cylinder(ref['xyz'])
    lost1 = loadz(O/'sets/c1_own_lost.npz'); lost3 = loadz(O/'sets/c3_own_lost.npz'); records = []
    for p, (idx, best) in choice.items():
        for grp, (name, nseen) in best.items():
            j = cam.names.index(name); pr, info, _ = vis_a1(STEM, ARM, rows['xyz'][idx], Nr[idx], rows['row_tau_m'][idx], np.zeros(len(idx), bool), maps=False, scenes=scenes, only_views={name})
            uv, _ = native(rows['xyz'][idx][pr['point']], cam, j); crop = bounds_crop(uv, cam.w, cam.h); sx = SIZE[0]/(crop[2]-crop[0]); sy = SIZE[1]/(crop[3]-crop[1])
            to_px = lambda P: (native(P, cam, j)[0]-crop[:2])*[sx, sy]
            im, src = undistort_crop(cam, j, crop, SIZE); base = f'photo_{p}_{grp}'; meta = dict(place=p, group=grp, image=name, j=j, place_gt_rows=len(idx), seen_place_points=nseen, blocked_pairs_this_view=info['blocked_pairs'],
                camera=dict(model='undistorted pinhole crop of the FULL_OPENCV training camera', fx=float(cam.p[0]), fy=float(cam.p[1]), cx=float(cam.p[2]), cy=float(cam.p[3]), full_opencv=cam.p.tolist(),
                            width=cam.w, height=cam.h, R=cam.R[j].tolist(), t=cam.t[j].tolist(), crop_xyxy=crop.tolist(), output_size=list(SIZE), pixel_rule='output pixel (i+.5) maps to crop[0]+(i+.5)*(crop[2]-crop[0])/W'),
                source=src, corners_xyz=place_corners(p).tolist())
            corners = to_px(place_corners(p)); meta['corners_px'] = corners.tolist()
            def finish(img, kind, extra=None):
                d = ImageDraw.Draw(img)
                for q in corners: cross(d, q)
                path = FIG/f'{base}_{kind}.png'; img.save(path); dump(path.with_suffix('.json'), dict(meta, kind=kind, **(extra or {}), at=now(), text_in_figure=False, scientific_verdict=None))
            finish(im.copy(), '원본')
            # points: every GT row / lost point projecting into the crop, kept when seen in this view (visibility_a1)
            uvall = to_px(rows['xyz']); inn = np.flatnonzero((uvall >= 0).all(1) & (uvall[:, 0] < SIZE[0]) & (uvall[:, 1] < SIZE[1]) & (np.asarray(native(rows['xyz'], cam, j)[1]) > 0))
            prr, _, _ = vis_a1(STEM, ARM, rows['xyz'][inn], Nr[inn], rows['row_tau_m'][inn], np.zeros(len(inn), bool), maps=False, scenes=scenes, only_views={name}); g = inn[prr['point']]
            img = im.copy().convert('RGBA'); ov = Image.new('RGBA', img.size); dr = ImageDraw.Draw(ov); counts = {}
            for k in [0, 1, 2, 3, 4]:
                q = g[case[g] == k]; counts[f'case{k}'] = len(q); col = hexrgb(CC[str(k)])
                for x, y in to_px(rows['xyz'][q]): dr.ellipse((x-2.5, y-2.5, x+2.5, y+2.5), fill=(*col, 200))
            for P_, nm, col, res in [(lost1, 'c1_lost', (31, 95, 214), False), (lost3, 'c3_lost', (214, 39, 40), True)]:
                uvp = to_px(P_['xyz']); ii = np.flatnonzero((uvp >= 0).all(1) & (uvp[:, 0] < SIZE[0]) & (uvp[:, 1] < SIZE[1]))
                if len(ii):
                    nn = P_['normal'][ii]/np.linalg.norm(P_['normal'][ii], axis=1)[:, None]
                    pp, _, _ = vis_a1(STEM, ARM, P_['xyz'][ii], nn, P_['tau_m'][ii], np.full(len(ii), res), maps=False, scenes=scenes, only_views={name}); q = ii[pp['point']]
                else: q = ii
                counts[nm] = len(q)
                for x, y in uvp[q]: dr.ellipse((x-3.5, y-3.5, x+3.5, y+3.5), fill=(*col, 235))
            finish(Image.alpha_composite(img, ov).convert('RGB'), '점', dict(seen_points_drawn=counts, colors=dict(cases=CC, c1_lost='#1F5FD6', c3_lost='#D62728')))
            for kind, path in [('결과', trained_mesh(STEM, ARM)), ('목표', target_mesh(STEM, ARM))]:
                simg, nhit = surface_image(path, cam, j, crop, ref, rtree, cy, wall_tau, roof_tau)
                finish(simg, kind, dict(mesh=str(path), mesh_sha256=sha(path), hit_pixels=nhit, color_rule='GTJUDGE addendum6 palette: result minus reference along the oriented triangle normal (cylinder query), white within tau, red above (outside), blue below (inside), saturation 1 m, no reference #8C95A3'))
            records.append(dict(place=p, group=grp, image=name, seen_place_points=nseen, **{f'drawn_{k}': v for k, v in counts.items()}, crop=crop.tolist()))
            print('PHOTO', p, grp, name, nseen, flush=True)
    cy.close(); atable('photo_figures', records)
    # legend (separate image, the only figure with text)
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    fig, ax = plt.subplots(figsize=(7, 3.2)); ax.axis('off'); names = {'0': '두 자료 모두 유효', '1': '사전정보 오류', '2': '영상 깊이 오류', '3': '둘 다 틀림', '4': '영상 깊이 결측'}
    items = [(CC[k], f'참값 점: {v}') for k, v in names.items()]+[('#1F5FD6', '잃은 점(칸 ①, 본 방법)'), ('#D62728', '틀린 결과 점(칸 ③, 본 방법)')]
    for i, (col, lab) in enumerate(items): ax.scatter([0.02], [1-i*.13], c=col, s=60); ax.text(.06, 1-i*.13, lab, va='center', fontsize=9)
    for i, (col, lab) in enumerate([('#FFFFFF', '면: 참값까지 τ 안'), ('#D83730', '면: 참값보다 위·바깥(1 m 이상 진함)'), ('#2A78D6', '면: 참값보다 아래·안쪽'), ('#8C95A3', '면: 참값 없음'), ('#FFFF00', '십자: 자리 모서리')]):
        ax.scatter([0.55], [1-i*.13], c=col, s=60, edgecolors='k', marker='s'); ax.text(.59, 1-i*.13, lab, va='center', fontsize=9)
    ax.set_xlim(0, 1.2); ax.set_ylim(.0, 1.1); fig.savefig(FIG/'photo_legend.png', dpi=200, bbox_inches='tight'); plt.close(fig)
    aprogress(f'일 가 사진 그림 {len(records)}장면 × 4 ({t0.done():.0f} s)')
if __name__ == '__main__': main()
