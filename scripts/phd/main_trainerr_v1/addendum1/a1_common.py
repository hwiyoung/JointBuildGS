"""PHD-MAIN-TRAINERR-v1 addendum 1 helpers: places, visibility_a1 (three-mesh rule), full-resolution cameras/photos and the addendum6 palette.
Inherited code copied verbatim where noted (GTJUDGE preservation.cameras/full_image, addendum9 undistort_crop, addendum6 palette)."""
import importlib.util, io, os, sys, zipfile
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from common import *
import open3d as o3d
A1O = O/'addendum1'; A1D = D/'addendum1'
def acfg():
    p = R/'configs/phd/main_trainerr_v1/addendum1.json'; lock = json.loads((p.with_name('addendum1.lock.json')).read_text())
    assert sha(p) == lock['config_sha256'], 'addendum1 config changed after lock'
    return json.loads(p.read_text())
def atable(name, rows):
    return table(name, rows, folder=A1D/'tables')
def aprogress(s):
    with (A1D/'progress.md').open('a') as f: f.write(f'- {now()}: {s}\n')
def aissue(s):
    with (A1D/'issues.md').open('a') as f: f.write(f'- {now()}: {s}\n')

# ---------------- places (addendum1.json places) ----------------
def wall_coords(xyz, which='south'):
    c = acfg()['places']; sw = c['south_wall']; p0 = np.array(sw['p0']); e = np.array(sw['e']); n = np.array(sw['n_out'])
    if which == 'south':
        a = (xyz[:, :2]-p0)@e; d = (xyz[:, :2]-p0)@n; lo, hi = sw['along_m']; return a, d, (a >= lo) & (a <= hi) & (xyz[:, 2] >= sw['z_m'][0]) & (xyz[:, 2] <= sw['z_m'][1]) & (d >= sw['offset_m'][0]) & (d <= sw['offset_m'][1])
    lw = c['long_wall']; corner = p0+20*e; a = (xyz[:, :2]-corner)@(-n); d = (xyz[:, :2]-corner)@e-long_wall_shift(); lo, hi = lw['along_m']
    return a, d, (a >= lo) & (a <= hi) & (xyz[:, 2] >= lw['z_m'][0]) & (xyz[:, 2] <= lw['z_m'][1]) & (d >= lw['offset_m'][0]) & (d <= lw['offset_m'][1])
_LW = None
def long_wall_shift():
    """order 0.2: when the defined face differs from the GT wall, fit the nearest wall = median offset of the GT wall rows in the long-wall zone (cached)."""
    global _LW
    if _LW is None:
        f = A1O/'long_wall_fit.json'
        if f.exists(): _LW = json.loads(f.read_text())['shift_m']
        else:
            c = acfg(); sw = c['places']['south_wall']; lw = c['long_wall'] if 'long_wall' in c else c['places']['long_wall']; p0 = np.array(sw['p0']); e = np.array(sw['e']); n = np.array(sw['n_out']); corner = p0+20*e
            r = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['xyz', 'wall']); x = r['xyz']; a = (x[:, :2]-corner)@(-n); d = (x[:, :2]-corner)@e
            m = (a >= lw['along_m'][0]) & (a <= lw['along_m'][1]) & (x[:, 2] >= lw['z_m'][0]) & (x[:, 2] <= lw['z_m'][1]) & (d >= lw['offset_m'][0]) & (d <= lw['offset_m'][1]) & r['wall'].astype(bool)
            _LW = float(np.median(d[m])); dump(f, dict(at=now(), shift_m=_LW, gt_wall_rows=int(m.sum()), rule='median offset of GT wall rows in the defined long-wall zone; face moved by this amount', scientific_verdict=None))
    return _LW
def wall_normal(which='south'):
    sw = acfg()['places']['south_wall']; n = np.array(sw['n_out']+[0.]); e = np.array(sw['e']+[0.])
    return n if which == 'south' else e
def place_mask(xyz, place):
    c = acfg()['places']
    if place in ('south_wall', 'south_wall_missing', 'south_wall_valid'): return wall_coords(xyz, 'south')[2]
    if place == 'long_wall': return wall_coords(xyz, 'long')[2]
    if place == 'annex_roof_edge':
        r = c['annex_roof_edge']; return (xyz[:, 0] >= r['x'][0]) & (xyz[:, 0] <= r['x'][1]) & (xyz[:, 1] >= r['y'][0]) & (xyz[:, 1] <= r['y'][1]) & (xyz[:, 2] >= r['z_m'][0]) & (xyz[:, 2] <= r['z_m'][1])
    if place == 'back_wall_bottom':
        b = c['back_wall_bottom']; return np.min([np.linalg.norm(xyz-np.array(q), axis=1) for q in b['centres']], 0) <= b['radius_m']
    raise ValueError(place)
def place_corners(place):
    c = acfg()['places']; sw = c['south_wall']; p0 = np.array(sw['p0']); e = np.array(sw['e']); n = np.array(sw['n_out'])
    if place.startswith('south_wall'):
        return np.array([[*(p0+a*e), z] for a in sw['along_m'] for z in sw['z_m']])[[0, 1, 3, 2]]
    if place == 'long_wall':
        corner = p0+20*e; return np.array([[*(corner-a*n), z] for a in c['long_wall']['along_m'] for z in c['long_wall']['z_m']])[[0, 1, 3, 2]]
    if place == 'annex_roof_edge':
        r = c['annex_roof_edge']; z = r['centre'][2]; return np.array([[r['x'][0], r['y'][0], z], [r['x'][1], r['y'][0], z], [r['x'][1], r['y'][1], z], [r['x'][0], r['y'][1], z]])
    b = c['back_wall_bottom']; A, B = np.array(b['centres']); u = B-A; u[2] = 0; u /= np.linalg.norm(u)
    return np.array([A-2*u, A+2*u, B+2*u, B-2*u])

# ---------------- meshes ----------------
def mesh_path(stem, method):
    """method mesh from the stored GTJUDGE distance record (container paths /out -> RESCORE, /gtjudge -> GTJUDGE)."""
    j = json.loads((GT/'scenes'/stem/'distances'/f'{method}.json').read_text()); p = j['mesh']
    return Path(p.replace('/out/', str(RS)+'/').replace('/gtjudge/', str(GT)+'/'))
def trained_mesh(stem, arm): return mesh_path(stem, 'FINALTRAIN_30000' if arm == 'own' else 'A1')
def target_mesh(stem, arm): return mesh_path(stem, 'judgment_mesh' if arm == 'own' else 'gt_judgment_mesh')
def scene_from(V, F):
    sc = o3d.t.geometry.RaycastingScene(nthreads=16); sc.add_triangles(o3d.core.Tensor(np.asarray(V, np.float32)), o3d.core.Tensor(np.asarray(F, np.uint32))); return sc
def scene_ply(path):
    m = o3d.io.read_triangle_mesh(str(path)); return scene_from(np.asarray(m.vertices), np.asarray(m.triangles))
def blockers(stem, arm):
    site, prior = stem.split('__'); pz = loadz(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs'/site/f'prior_{prior}.npz', ['V', 'F'])
    return {'mvs': scene_ply(AX/'mvs'/site/'mesh_mvs_a.ply'), 'prior': scene_from(pz['V'], pz['F']), 'trained': scene_ply(trained_mesh(stem, arm))}

def train_views(site):
    return [v for v in json.loads((GT/'views'/f'{site}.json').read_text())['views'] if not v['virtual']]

def vis_a1(stem, arm, X, Nn, tau, result, maps=True, scenes=None, keep_blocked=False, progress='', only_views=None):
    """visibility_a1 over all training views. Returns per seen (point, view) pair arrays + blocking counts by mesh."""
    site = stem.split('__')[0]; views = train_views(site); scenes = scenes or blockers(stem, arm); ap = arm_paths(stem, arm)
    index = json.loads((ap['target_dir']/'maps/index.json').read_text())['views'] if maps else None
    cos30 = np.cos(np.radians(30.)); out = {k: [] for k in ['point', 'view', 'u', 'v', 'px', 'py', 'z', 'facing', 'angle_deg', 'owner', 'weight', 'tdepth', 'mesh_z']}
    blocked = {k: 0 for k in scenes}; inimg = np.zeros(len(X), np.int32)
    for j, vw in enumerate(views):
        if only_views is not None and vw['name'] not in only_views: continue
        K = np.asarray(vw['K'], float); E = np.asarray(vw['W2C'], float); W, H = vw['width'], vw['height']; C = -E[:3, :3].T@E[:3, 3]
        Pc = X@E[:3, :3].T+E[:3, 3]; z = Pc[:, 2]
        with np.errstate(divide='ignore', invalid='ignore'): u = K[0, 0]*Pc[:, 0]/z+K[0, 2]; v = K[1, 1]*Pc[:, 1]/z+K[1, 2]
        px = np.floor(np.nan_to_num(u, nan=-1e9)+.5).astype(np.int64); py = np.floor(np.nan_to_num(v, nan=-1e9)+.5).astype(np.int64)
        ii = np.flatnonzero((z > 0) & (px >= 0) & (py >= 0) & (px < W) & (py < H)); inimg[ii] += 1
        if not len(ii): continue
        d = X[ii]-C; dist = np.linalg.norm(d, axis=1); dirn = d/dist[:, None]; rays = o3d.core.Tensor(np.c_[np.broadcast_to(C, (len(ii), 3)), dirn].astype(np.float32))
        ok = np.ones(len(ii), bool); mz = None
        for name, sc in scenes.items():
            th = sc.cast_rays(rays)['t_hit'].numpy().astype(np.float64); blk = np.isfinite(th) & (th < dist-np.maximum(tau[ii], np.where(result[ii], .1, 0.)))
            blocked[name] += int((blk & ok).sum()); ok &= ~blk
            if name == 'trained': mz = np.where(np.isfinite(th), th*(dirn@E[2, :3]), np.nan)
        k = ii[ok]
        if not len(k): continue
        if maps:
            mi = index[vw['name']]
            with np.load(ap['target_dir']/'maps'/mi['file']) as mp: own, wt, td = (mp[q][py[k], px[k]] for q in ['owner', 'weight', 'depth'])
        else: own = np.full(len(k), -1); wt = np.full(len(k), np.nan); td = np.full(len(k), np.nan)
        cosang = np.abs(np.einsum('ij,ij->i', -dirn[ok], Nn[k]))
        for key, val in [('point', k), ('view', np.full(len(k), j)), ('u', u[k]), ('v', v[k]), ('px', px[k]), ('py', py[k]), ('z', z[k]), ('facing', cosang >= cos30),
                         ('angle_deg', np.degrees(np.arccos(np.clip(cosang, 0, 1)))), ('owner', own), ('weight', wt), ('tdepth', td), ('mesh_z', mz[ok])]: out[key].append(val)
        if progress and j % 60 == 0: print('VIS_A1', progress, j, len(views), flush=True)
    dt_ = dict(point='i4', view='i2', u='f4', v='f4', px='i2', py='i2', z='f4', facing='u1', angle_deg='f4', owner='i4', weight='f4', tdepth='f4', mesh_z='f4')
    arr = {k: (np.concatenate(v) if v else np.zeros(0)).astype(dt_[k]) for k, v in out.items()}
    return arr, dict(blocked_pairs=blocked, in_image_pairs=int(inimg.sum()), seen_pairs=len(arr['point'])), inimg

# ---------------- photos (inherited) ----------------
def cameras(site):
    """GTJUDGE preservation.cameras (unchanged logic): FINALTRAIN inherited_judgeapply Cameras with its own common module."""
    own = sys.modules.pop('common'); paths = sys.path[:]
    folder = R/'scripts/phd/main_finaltrain_v1/inherited_judgeapply'; sys.path.insert(0, str(folder)); os.environ['FINALTRAIN_SITE'] = site
    try:
        spec = importlib.util.spec_from_file_location('gt_texture_cameras', folder/'cameras.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); cam = m.Cameras(site)
    finally:
        sys.modules['common'] = own; sys.path[:] = paths
    return cam
def full_image(cam, j):
    from PIL import Image
    archive = PH.parent/'p0-audit/data/raw/uav/Images.zip'
    with zipfile.ZipFile(archive) as z: data = z.read(cam.members[j]); info = z.getinfo(cam.members[j])
    im = Image.open(io.BytesIO(data)).convert('RGB'); return im, dict(archive=str(archive), member=cam.members[j], crc32=info.CRC, size=info.file_size)
def undistort_crop(cam, j, crop, size):
    """GTJUDGE add9_photos.undistort_crop (verbatim rule)."""
    import cv2
    from PIL import Image
    im, source = full_image(cam, j); original = np.asarray(im); W, H = size
    x, y = np.meshgrid(crop[0]+(np.arange(W)+.5)*(crop[2]-crop[0])/W, crop[1]+(np.arange(H)+.5)*(crop[3]-crop[1])/H)
    fx, fy, cx, cy, k1, k2, p1, p2, k3, k4, k5, k6 = cam.p; x = (x-cx)/fx; y = (y-cy)/fy; r = x*x+y*y; radial = (1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
    u = fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx; v = fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy
    valid = (u >= 0) & (u < cam.w-1) & (v >= 0) & (v < cam.h-1)
    out = cv2.remap(original, u.astype('f4'), v.astype('f4'), cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    source['undistorted_valid_pixel_fraction'] = float(valid.mean()); return Image.fromarray(out), source
def bounds_crop(uv, w, h, padding=1.06):
    """GTJUDGE add9_photos.bounds_crop (verbatim)."""
    lo, hi = uv.min(0), uv.max(0); mid = (lo+hi)/2; cw = max(hi[0]-lo[0], (hi[1]-lo[1])*1.25)*padding; ch = cw/1.25
    if cw <= w and ch <= h: mid = np.clip(mid, [cw/2, ch/2], [w-cw/2, h-ch/2])
    return np.r_[mid-[cw/2, ch/2], mid+[cw/2, ch/2]]
def native(P, cam, j):
    Q = np.asarray(P)@cam.R[j].T+cam.t[j]; uv = Q[:, :2]/Q[:, 2, None]*cam.p[:2]+cam.p[2:4]; return uv, Q[:, 2]
def palette(ids, signed, tau):
    """GTJUDGE add6_render.palette (verbatim): white within tau, red above, blue below, saturation 1 m, no reference #8C95A3."""
    good = ids >= 0; far = good & np.isfinite(signed) & (abs(signed) > tau); out = np.full((*ids.shape, 3), 255, 'u1'); t = np.minimum(abs(signed[far]), 1)[:, None]
    out[far] = np.rint(255*(1-t)+np.where((signed[far] > 0)[:, None], np.array([216, 55, 48]), np.array([42, 120, 214]))*t).astype('u1'); out[good & ~np.isfinite(signed)] = [140, 149, 163]; return out
def cylinder_module():
    spec = importlib.util.spec_from_file_location('gtj_cylinder', R/'scripts/phd/main_gtjudge_v1/cylinder.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
