"""광도 일관성 검사 준비 (구역마다). JUDGEAPPLY-v1 photo_prepare.py 의 규칙(벽 원통 5 m, 사전 정보 면 = h_P + r, 높이 하나, 자른 조각만)을
캠퍼스 입력(WIDEN0 MVS 점, raw ALS 점, 구역 메시, WIDEN0 학습 카메라)에 쓴다. 상속 함수는 바이트 같은 복사. 참값 읽지 않음.
대상: 구성 패치 하나라도 n>=4 인 사진 점. r 은 본값(calib base) 탐색 지역 값."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import resource
sys.path.insert(0, str(HERE/'inherited'))
from photo_cameras import Cameras, choose_mvs_views
UV = np.stack(np.meshgrid(np.arange(25)*.02-.24, np.arange(25)*.02-.24, indexing='xy'), -1).reshape(625, 2)
defs = json.loads((R/'configs/phd/main_widen0_v2/widen0_v2.json').read_text())['definitions']
scope = dict(np=np, cKDTree=cKDTree, UV=UV, DEFINITIONS=defs, DEFS=defs)
functions('u_core.py', ['find_face'], scope)
tangent, fit_mvs, in_triangles = functions('photo_planes.py', ['tangent', 'fit_mvs', 'in_triangles'], scope)
functions('photo_planes.py', ['plane'], scope)
HALF = {'H': 10.}
def column(X, tree, c, n):  # JUDGEAPPLY regional_column: 지붕 10 m, 벽 5 m
    H = HALF['H']; probes = c + np.arange(-H+.25, H, .5)[:, None]*n
    ids = np.unique(np.concatenate([np.asarray(a, int) for a in tree.query_ball_point(probes, np.hypot(.5, .25)+1e-6)]))
    v = X[ids]-c; t = v@n; rho2 = np.maximum(0, np.sum(v*v, 1)-t*t)
    keep = (rho2 <= .25) & (abs(t) <= H); ids = ids[keep]; t = t[keep]
    o, _, _ = scope['find_face'](t, H, defs)
    if o is None: return np.empty((0, 3))
    return X[ids[abs(t-o) <= 1.]]
scope['column'] = column
fitted_normals, prior_height, als_mask, mvs_mask = functions('photo_prepare_reply2.py', ['fitted_normals', 'prior_height', 'als_mask', 'mvs_mask'], scope)
SCENE = {}
scope['mesh_scene'] = lambda tile, prior: SCENE['scene']
select_photos, = functions('main_photocheck_v1__cameras.py', ['select_photos'], scope)
def make_scene(V, F):
    import open3d as o3d
    s = o3d.t.geometry.RaycastingScene(nthreads=4); s.add_triangles(o3d.core.Tensor(V.astype('f4')), o3d.core.Tensor(F.astype('u4'))); return s
def main(tile):
    cfg(); dest = O/'photo_prepared'/f'{tile}.npz'
    if dest.exists(): return
    start = time.monotonic(); parts = []; rows = []; X = tree = A = atree = None; cam = Cameras()
    for prior in ['LoD2', 'ALS']:
        gp = O/'photo_groups'/f'{tile}__{prior}.npz'
        if not gp.exists(): continue
        g = loadz(gp); d = loadz(O/'geometry_raw'/f'{tile}__{prior}.npz', ['n', 'd_m', 'kind', 'building', 'shift_m', 'centre'])
        cb = loadz(O/'geometry/base'/f'{tile}__{prior}.npz', ['r_m', 'geometry'])
        own = g['patch_point']; P = len(g['point_id'])
        target = np.bincount(own, weights=(d['n'] >= 4).astype(float), minlength=P) > 0
        all_within = np.bincount(own, weights=(cb['geometry'] != 0).astype(float), minlength=P) == 0
        dbar = np.full(P, np.nan); r_m = np.full(P, np.nan); shift = np.zeros((P, 3))
        o = np.argsort(own, kind='stable'); cuts = np.flatnonzero(np.diff(own[o])) + 1
        for grp in np.split(o, cuts):
            j = own[grp[0]]; v = d['d_m'][grp]; v = v[(d['n'][grp] >= 4) & np.isfinite(v)]
            if len(v): dbar[j] = np.median(v)
            r_m[j] = cb['r_m'][grp[0]]; shift[j] = d['shift_m'][grp[0]]
        active = np.flatnonzero(target); N = len(active)
        if not N: continue
        if X is None:
            X = np.load(WI/'points'/tile/'mvs_a_xyz.npy').astype(float); tree = cKDTree(X, leafsize=32, balanced_tree=False, compact_nodes=False)
        h = g['centre'][active]; normal = g['normal'][active].copy(); hp = np.zeros(N); rule = np.ones(N, bool); priorn = np.full(N, -1, int); support = None
        if prior == 'ALS':
            if A is None:
                raw = np.fromfile(W/'inputs/points'/tile/'als.bin', dtype=[('x', '<f8'), ('y', '<f8'), ('z', '<f8'), ('cls', 'u1'), ('multi', 'u1')])
                A = np.c_[raw['x'], raw['y'], raw['z']][np.isin(raw['cls'], [2, 6])]; atree = cKDTree(A, leafsize=32, balanced_tree=False, compact_nodes=False)
            hr = h - shift[active]; normal, rule = fitted_normals(A, atree, hr)
            for i in range(N): hp[i], priorn[i] = prior_height(A, atree, hr[i], normal[i])
            bl = set(g['building'][active]); cs = {b: [] for b in bl}
            for q in (O/'geometry_raw').glob('*__ALS.npz'):
                z = loadz(q, ['building', 'centre'])
                for b in bl:
                    m = z['building'] == b
                    if m.any(): cs[b].append(z['centre'][m])
            support = {b: cKDTree(np.concatenate(v)) for b, v in cs.items() if v}
        else:
            mesh = loadz(WI/'prior_tiles'/tile/'lod2_mesh.npz', ['V', 'F', 'tri_surface'])
            tris = {int(s): mesh['V'][mesh['F'][mesh['tri_surface'] == s]] for s in np.unique(g['surf'][active])}
        centres = np.full((N, 2, 3), np.nan); normals = centres.copy(); e1 = centres.copy(); e2 = centres.copy(); avail = np.zeros((N, 2), bool); masks = np.zeros((N, 2, 625), bool)
        count = np.zeros(N, int); res = np.full(N, np.nan); angle = res.copy(); fitreason = np.full(N, 'prior_plane_unavailable', dtype='<U40'); t0 = time.monotonic()
        for i, gi in enumerate(active):
            c = h[i]; n = normal[i]
            if not np.isfinite(n).all() or not np.isfinite(hp[i]) or not np.isfinite(r_m[gi]): continue
            centres[i, 0] = c + (hp[i] + r_m[gi])*n; normals[i, 0] = n; avail[i, 0] = True
            e1[i, 0], e2[i, 0] = (g['tangent1'][gi], g['tangent2'][gi]) if prior == 'LoD2' else tangent(n)
            HALF['H'] = 5. if g['kind'][gi] == 2 else 10.
            fitted, meta = fit_mvs(X, tree, c, n, hp[i], dbar[gi]); count[i] = meta['point_count']; fitreason[i] = meta['reason']
            if fitted is not None:
                centres[i, 1], normals[i, 1] = fitted; avail[i, 1] = True; e1[i, 1], e2[i, 1] = tangent(fitted[1]); res[i] = meta['residual_nmad_m']; angle[i] = meta['normal_angle_deg']
            for j in range(2):
                if not avail[i, j]: continue
                cc, nn, a, b = centres[i, j], normals[i, j], e1[i, j], e2[i, j]
                if j == 1: masks[i, j] = mvs_mask(X, tree, cc, nn, a, b, np.array([0.]))[0]
                elif prior == 'ALS': masks[i, j] = als_mask(support[str(g['building'][gi])], cc, nn, a, b, np.array([0.]))[0]
                else: masks[i, j] = in_triangles(cc + UV[:, 0, None]*a + UV[:, 1, None]*b, tris[int(g['surf'][gi])], cc, a, b)
            if i % 5000 == 0: print('PHOTO_PREPARE', tile, prior, i, N, round(time.monotonic()-t0), flush=True)
        geo_s = time.monotonic()-t0; t1 = time.monotonic()
        selected = np.full((N, 2, 10), -1, np.int32)
        if prior == 'LoD2':
            SCENE['scene'] = make_scene(mesh['V'], mesh['F'])
            gg = dict(centre=centres[:, 0], normal=normals[:, 0], tangent1=e1[:, 0], tangent2=e2[:, 0], geometry_valid=avail[:, 0]); selected[:, 0] = select_photos(gg, cam, tile, prior)['selected_images']
        else:
            am = loadz(WI/'prior_tiles'/tile/'als_mesh.npz', ['V', 'F']); sh = shift[active]; keys = np.unique(sh, axis=0)
            for s in keys:
                m = np.flatnonzero((sh == s).all(1)); SCENE['scene'] = make_scene(am['V'] + s, am['F'])
                gg = dict(centre=centres[m, 0], normal=normals[m, 0], tangent1=e1[m, 0], tangent2=e2[m, 0], geometry_valid=avail[m, 0]); selected[m, 0] = select_photos(gg, cam, tile, prior)['selected_images']
        selected[:, 1] = choose_mvs_views(centres[:, 1], normals[:, 1], e1[:, 1], e2[:, 1], cam, avail[:, 1]); vis_s = time.monotonic()-t1
        parts.append(dict(point_id=g['point_uid'][active], source_index=active, prior=np.full(N, prior), kind=g['kind'][active], area=g['area'][active], all_within=all_within[active], dbar=dbar[active], r_m=r_m[active],
                          centres=centres, normals=normals, tangent1=e1, tangent2=e2, available=avail, selected_images=selected, masks=masks, prior_height_m=hp, prior_n=priorn, prior_normal_rule_met=rule,
                          mvs_fit_count=count, mvs_fit_nmad_m=res, mvs_normal_angle_deg=angle, mvs_fit_reason=fitreason, photo_centre=h, photo_normal=normal))
        rows.append(dict(prior=prior, all_points=P, scored_points=N, geometry_seconds=geo_s, visibility_seconds=vis_s))
    if not parts:
        dump(dest.with_suffix('.json'), dict(at=now(), tile=tile, rows=[], note='no target point', scientific_verdict=None)); return
    result = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}; N = len(result['point_id']); av = result['available'].ravel(); planes = np.flatnonzero(av)
    result.update(row_plane=planes.astype('i4'), row_height=np.zeros(len(planes)), mask_bits=np.packbits(result.pop('masks').reshape(2*N, 625)[planes], axis=1), plane_row_ptr=np.r_[0, np.cumsum(av)].astype(np.int64))
    fr = np.full(2*N, np.nan); fr[planes] = np.unpackbits(result['mask_bits'], axis=1, count=625).mean(1); result['mask_fraction_at_zero'] = fr.reshape(N, 2)
    savez(dest, **result)
    dump(dest.with_suffix('.json'), dict(at=now(), tile=tile, rows=rows, total_seconds=time.monotonic()-start, peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2, GT_read=False, scientific_verdict=None))
    print('PHOTO_PREPARE_COMPLETE', tile, json.dumps(rows), flush=True)
if __name__ == '__main__':
    for t in sys.argv[1:]: main(t)
