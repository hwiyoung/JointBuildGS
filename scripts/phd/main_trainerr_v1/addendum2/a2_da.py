"""Addendum 2 work 다 (order 4): B0_b10__ALS annex roof, real images. 'Inside the image' only (no occlusion test).
  select   (CPU): annex_under points of the own arm, per training image inside counts by group, crop -> addendum2/da/selection.json
  render   (GPU): a2_da_render.py (separate: the GPU image has no open3d)
  figures  (CPU): 원본, 점_<arm>, 결과_<arm>, 목표_<arm>, 렌더_<arm> -> docs addendum2/figures/da_<group>_<panel>.png + json"""
from a2_common import *
STEM, SITE = 'B0_b10__ALS', 'B0_b10'; SIZE = (1600, 1280)

def under_points(arm):
    c = bcfg(); bx = c['places']['annex_under']; rm = TRAINED_METHOD[arm]
    Z = np.load(GT/'addendum12/distance_A1'/f'{STEM}.npz') if arm == 'gt' else np.load(GT/'addendum11/final_data'/f'{STEM}.npz')
    r = {k: Z[f'result__{rm}__{k}'] for k in ['xyz', 'normal', 'case_id', 'eligible_new', 's_m']}; Z.close(); x = r['xyz'].astype('f8'); s = r['s_m'].astype('f8')
    m = (x[:, 0] >= bx['x'][0]) & (x[:, 0] <= bx['x'][1]) & (x[:, 1] >= bx['y'][0]) & (x[:, 1] <= bx['y'][1]) & (r['case_id'] == 2) & r['eligible_new'].astype(bool) & np.isfinite(s) & (np.abs(s) > 1.0)
    n = r['normal'][m].astype('f8'); n /= np.linalg.norm(n, axis=1)[:, None]; return x[m], n, s[m]

def select():
    c = bcfg(); X, Nn, _ = under_points('own'); cam = cameras(SITE); names = [v['name'] for v in train_views(SITE)]; rows = []; cnt = {'수직에 가까움': {}, '비스듬': {}}
    cos30 = np.cos(np.radians(30.))
    for name in names:
        j = cam.names.index(name); uv, z = native(X, cam, j); ins = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < cam.w) & (uv[:, 1] >= 0) & (uv[:, 1] < cam.h)
        C = -cam.R[j].T@cam.t[j]; d = C-X; d /= np.linalg.norm(d, axis=1)[:, None]; fac = np.abs((d*Nn).sum(1)) >= cos30
        cnt['수직에 가까움'][name] = int((ins & fac).sum()); cnt['비스듬'][name] = int((ins & ~fac).sum()); rows.append(dict(image=name, inside=int(ins.sum()), inside_near_vertical=cnt['수직에 가까움'][name], inside_oblique=cnt['비스듬'][name]))
    lo = np.r_[X[:, :2].min(0)-5, X[:, 2].min()]; hi = np.r_[X[:, :2].max(0)+5, X[:, 2].max()+4]; box = np.array([[x_, y_, z_] for x_ in (lo[0], hi[0]) for y_ in (lo[1], hi[1]) for z_ in (lo[2], hi[2])])
    sel = {}
    for grp, cg in cnt.items():
        name = sorted(cg, key=lambda k: (-cg[k], k))[0]; j = cam.names.index(name); uvb, zb = native(box, cam, j); crop = bounds_crop(uvb, cam.w, cam.h)
        fx, fy, cx, cy = cam.p[:4]; sx = SIZE[0]/(crop[2]-crop[0]); sy = SIZE[1]/(crop[3]-crop[1]); Kc = [[fx*sx, 0, (cx-crop[0])*sx-.5], [0, fy*sy, (cy-crop[1])*sy-.5], [0, 0, 1]]
        E = np.eye(4); E[:3, :3] = cam.R[j]; E[:3, 3] = cam.t[j]
        sel[grp] = dict(image=name, j=j, inside_points=cg[name], crop_xyxy=crop.tolist(), box_corners=box.tolist(), box_behind_camera=int((zb <= 0).sum()), K_crop=Kc, W2C=E.tolist(), size=list(SIZE))
    dump(A2O/'da/selection.json', dict(at=now(), stem=STEM, points=len(X), rule=c['work_da'], selection=sel, occlusion_test=False, note='inside the image only; no occlusion test (order 4)', scientific_verdict=None))
    btable('da_view_counts', rows); btable('da_selection', [dict(group=g, **{k: v for k, v in s.items() if k in ('image', 'inside_points', 'crop_xyxy')}) for g, s in sel.items()]); print('DA_SELECT', {g: s['image'] for g, s in sel.items()}, flush=True)

def figures():
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1'); from a1_photo import surface_image, cross; from PIL import Image, ImageDraw
    sel = json.loads((A2O/'da/selection.json').read_text())['selection']; cam = cameras(SITE); FIG = A2D/'figures'; FIG.mkdir(parents=True, exist_ok=True)
    ref = loadz(GT/'reference'/SITE/'dense.npz'); rtree = cKDTree(ref['xyz']); Cy = cylinder_module(); cy = Cy.Cylinder(ref['xyz']); roof_tau, wall_tau = tau_of(SITE, 'ALS'); pts = {arm: under_points(arm) for arm in ARMS}; recs = []
    for grp, s in sel.items():
        j = s['j']; crop = np.array(s['crop_xyxy']); sx = SIZE[0]/(crop[2]-crop[0]); sy = SIZE[1]/(crop[3]-crop[1]); to_px = lambda P: (native(P, cam, j)[0]-crop[:2])*[sx, sy]
        meta = dict(stem=STEM, group=grp, image=s['image'], camera=dict(model='undistorted pinhole crop of the FULL_OPENCV training camera', full_opencv=cam.p.tolist(), width=cam.w, height=cam.h, R=cam.R[j].tolist(), t=cam.t[j].tolist(),
                    crop_xyxy=crop.tolist(), output_size=list(SIZE), K_crop=s['K_crop']), inside_rule='inside the image only, no occlusion test', box_corners=s['box_corners'])
        def save(img, panel, extra=None):
            p = FIG/f'da_{grp}_{panel}.png'; img.save(p); dump(p.with_suffix('.json'), dict(meta, panel=panel, **(extra or {}), text_in_figure=False, at=now(), scientific_verdict=None))
        im, src = undistort_crop(cam, j, crop, SIZE); save(im, '원본', dict(source=src))
        for arm in ARMS:
            X = pts[arm][0]; uv = to_px(X); _, zc = native(X, cam, j); k = (zc > 0) & (uv >= 0).all(1) & (uv[:, 0] < SIZE[0]) & (uv[:, 1] < SIZE[1])
            img = im.copy().convert('RGBA'); ov = Image.new('RGBA', img.size); dr = ImageDraw.Draw(ov)
            for x, y in uv[k]: dr.ellipse((x-2.5, y-2.5, x+2.5, y+2.5), fill=(214, 39, 40, 220))
            save(Image.alpha_composite(img, ov).convert('RGB'), f'점_{arm}', dict(points_all=len(X), points_inside_crop=int(k.sum()), colour='#D62728', points='annex_under of the arm'))
            for kind, path in [('결과', trained_mesh(STEM, arm)), ('목표', target_mesh(STEM, arm))]:
                simg, nhit = surface_image(path, cam, j, crop, ref, rtree, cy, wall_tau, roof_tau)
                save(simg, f'{kind}_{arm}', dict(mesh=str(path), mesh_sha256=sha(path), hit_pixels=nhit, color_rule='GTJUDGE addendum6 palette (white within tau, red above/outside, blue below/inside, saturation 1 m, no reference #8C95A3)'))
            rp = A2O/'da'/f'render_{arm}_{grp}.png'
            if rp.exists(): save(Image.open(rp).convert('RGB'), f'렌더_{arm}', dict(source=str(rp), model=str(model_dir(STEM, arm)), renderer='te_render (inherited), SH degree 0, black background'))
            recs.append(dict(group=grp, image=s['image'], arm=arm, points_all=len(X), points_inside_crop=int(k.sum())))
        print('DA_FIG', grp, s['image'], flush=True)
    cy.close(); btable('da_figures', recs); bprogress('일 다 그림')

if __name__ == '__main__':
    a = sys.argv[1:]
    {'select': select, 'figures': figures}[a[0]]()
