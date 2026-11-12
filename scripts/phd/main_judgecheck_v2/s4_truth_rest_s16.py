"""[16칸 MVS 면을 읽는 판: 6909_53361 전용. 나머지는 s4_truth_rest.py 와 같음]
나머지 건물의 참값 점 (발주 2.3·2.5). 구역마다: WIDEN0 gt_xyz(구역 중심 소유) - 세 평가 범위 안 점(저장된 GTJUDGE 행이 맡음).
분류: 벽 = s04 vertical_points (0.5 m 복셀 PCA |nz|<0.5, 5점 이상, 구역 점 전체로), 땅 = 벽 아님 & z - DTM <= 0.5 m, 지붕 = 나머지.
짝짓기: RESCORE 기둥 규칙(prism.cpp, ±0.125 m, 지붕 10 m / 벽 5 m, 가장 가까운 |축 거리|), 벽 점 ↔ 벽 패치, 지붕·땅 점 ↔ 지붕 패치.
솎기: STAGE1 defs_s1 규칙(0.1 m 칸, 지붕·땅 수평, 벽은 LoD2 면마다 벽 평면 좌표; src.phd.metrics_v3.thin.keep_nearest).
법선: AXES71 a1_normals (반지름 0.5 m 이웃 PCA, 10개 미만이면 가까운 10개; 이웃은 구역 점 전체), 방향 지붕·땅 nz>=0, 벽은 가장 가까운 학습 카메라 쪽.
거리: GTJUDGE normal_line.measure (점 + 5 cm 접선 넷, ±n, 지붕·땅 10 m / 벽 5 m), 사전 정보 면(LoD2 바닥면 뺌 / ALS TIN + 지역 이동), MVS 면(s1_tsdf)."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import subprocess, open3d as o3d
sys.path.insert(0, '/repo'); sys.path.insert(0, str(HERE/'inherited'))
from src.phd.metrics_v3 import thin
from photo_cameras import Cameras
scope = dict(np=np, CHUNK=2000000)
vertical_points, = functions('s04_gt_v6.py', ['vertical_points'], scope)
measure, tangents, unit_normals = functions('gtjudge_normal_line.py', ['measure', 'tangents', 'unit_normals'], dict(np=np))
SURVEY = PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1'
BOXES = {'B0': ([28.1, 98.8], [80.6, 111.4]), 'B173nb': ([115.4, 191.0], [55.0, 109.1]), 'R1rep': ([1.0, 55.3], [-26.6, 22.8])}
A = np.deg2rad(70.); BASIS = np.array([[np.cos(A), np.sin(A)], [np.sin(A), -np.cos(A)]])
class Scene:
    def __init__(s, V, F):
        s.s = o3d.t.geometry.RaycastingScene(nthreads=int(os.environ.get('JC2_CPUS', '4'))); s.s.add_triangles(o3d.core.Tensor(np.asarray(V, 'f4')), o3d.core.Tensor(np.asarray(F, 'u4')))
    def cast(s, p, d):
        r = np.c_[p, d].astype('f4'); t = s.s.cast_rays(o3d.core.Tensor(r))['t_hit'].numpy(); return t
def prism(points, c, a, b, n, length, folder):
    basis = np.stack([a, b, n], axis=2); good = np.isfinite(basis).all((1, 2)) & np.isfinite(c).all(1)
    inv = np.full_like(basis, np.nan); good[good] &= np.abs(np.linalg.det(basis[good])) > 1e-10; inv[good] = np.linalg.inv(basis[good])
    ext = .125*(abs(a)+abs(b)) + length[:, None]*abs(n)
    rec = np.c_[c, inv.reshape(-1, 9), np.where(good, length, 0), c-ext, c+ext].astype('<f8'); folder.mkdir(parents=True, exist_ok=True)
    points.astype('<f8').tofile(folder/'points.bin'); np.nan_to_num(rec, nan=np.nan).tofile(folder/'columns.bin')
    exe = O/'bin/prism'
    if not exe.exists(): exe.parent.mkdir(exist_ok=True); subprocess.run(['g++', '-O3', '-std=c++17', str(HERE/'inherited/rescore_prism.cpp'), '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder/'points.bin'), str(folder/'columns.bin'), str(folder/'owner.bin'), str(folder/'hits.bin')], check=True, stdout=subprocess.DEVNULL)
    o = np.fromfile(folder/'owner.bin', '<i4'); h = np.fromfile(folder/'hits.bin', '<i4')
    for f in ['points.bin', 'columns.bin', 'owner.bin', 'hits.bin']: (folder/f).unlink()
    return o, h
def pca_normals(X, tree, Q):
    N = np.full((len(Q), 3), np.nan); cnt = np.zeros(len(Q), np.int32); res = np.full(len(Q), np.nan)
    for b0 in range(0, len(Q), 20000):
        q = Q[b0:b0+20000]; L = tree.query_ball_point(q, 0.5)
        for k, ids in enumerate(L):
            if len(ids) < 10: ids = tree.query(q[k], 10)[1]
            P = X[np.asarray(ids, int)]; m = P.mean(0); C = (P-m).T @ (P-m)/len(P); w, v = np.linalg.eigh(C)
            N[b0+k] = v[:, 0]; cnt[b0+k] = len(ids); res[b0+k] = np.sqrt(max(w[0], 0))
    return N, cnt, res
def main(tile):
    cfg(); dest = O/'truth/rest'/f'{tile}.npz'
    if dest.exists(): return
    T = Timer(); t = next(x for x in json.loads((W/'inputs/tiles.json').read_text()) if x['id'] == tile)
    e0, n0, e1, n1 = t['core_global']; lo = np.array([e0-690953, n0-5336071]); hi = np.array([e1-690953, n1-5336071])
    X = np.load(WI/'points'/tile/'gt_xyz.npy').astype(np.float64); core = ((X[:, :2] >= lo) & (X[:, :2] < hi)).all(1)
    uv = X[:, :2] @ BASIS.T; inbox = np.zeros(len(X), bool)
    for (u, v) in BOXES.values(): inbox |= (uv[:, 0] >= u[0]) & (uv[:, 0] <= u[1]) & (uv[:, 1] >= v[0]) & (uv[:, 1] <= v[1])
    vert = vertical_points(X); T.mark('vertical')
    Dg = dict(np.load(SURVEY/'derived.npz')); dtm = Dg['dtm'].astype(float)
    E = X[:, 0] + 690953.0; Nn = X[:, 1] + 5336071.0; ix = np.floor((E - 690700.0)/0.5).astype(int); iy = np.floor((Nn - 5335820.0)/0.5).astype(int)
    okg = (ix >= 0) & (iy >= 0) & (ix < dtm.shape[1]) & (iy < dtm.shape[0]); zd = np.full(len(X), np.nan); zd[okg] = dtm[iy[okg], ix[okg]] - 604.0
    hag = X[:, 2] - zd
    gkind = np.where(vert, 2, np.where(np.isfinite(hag) & (hag <= .5), 3, 1)).astype(np.int8)   # 1 지붕, 2 벽, 3 땅
    sel = np.flatnonzero(core & ~inbox); out = {}; cam = Cameras(); camc = cTree = cKDTree(cam.centres)
    tree_all = None
    for prior in ['LoD2', 'ALS']:
        # 이 구역과 이웃 구역의 패치 (기둥이 구역 경계를 넘을 수 있음)
        P = []
        for q in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
            z = loadz(q, ['patch_id', 'centre', 'normal', 'tangent1', 'tangent2', 'kind', 'prior_height_m', 'building', 'surf', 'region', 'shift_m'])
            m = ((z['centre'][:, :2] >= lo - 12) & (z['centre'][:, :2] <= hi + 12)).all(1)
            if m.any(): z = {k: v[m] for k, v in z.items()}; z['tile'] = np.full(int(m.sum()), q.stem.split('__')[0]); P.append(z)
        if not P: continue
        p = {k: np.concatenate([x[k] for x in P]) for k in P[0]}; n = p['normal'].astype(float); a = p['tangent1'].astype(float); b = p['tangent2'].astype(float)
        if prior == 'ALS':
            for i in np.flatnonzero(np.isfinite(n).all(1)):
                e = np.array([1., 0., 0.]) if abs(n[i, 0]) < .9 else np.array([0., 1., 0.]); e = e - n[i]*(e@n[i]); e /= np.linalg.norm(e); a[i] = e; b[i] = np.cross(n[i], e)
        c = p['centre'] + np.nan_to_num(p['prior_height_m'])[:, None]*n; length = np.where(p['kind'] == 1, 10., 5.)
        owner = np.full(len(sel), -1, np.int64); hits = np.zeros(len(sel), np.int32)
        for kind, gmask in [(1, gkind[sel] != 2), (2, gkind[sel] == 2)]:
            pm = np.flatnonzero(p['kind'] == kind); qi = np.flatnonzero(gmask)
            if not len(pm) or not len(qi): continue
            o, h = prism(X[sel[qi]], c[pm], a[pm], b[pm], n[pm], length[pm], O/'tmp'/f'prism_{tile}_{prior}_{kind}')
            owner[qi[o >= 0]] = pm[o[o >= 0]]; hits[qi] = h
        paired = np.flatnonzero(owner >= 0); po = owner[paired]; gi = sel[paired]
        pair_count = np.bincount(po, minlength=len(p['kind']))
        # 안쪽 반기둥(지붕 아래 10 m, 벽 뒤 5 m)에 든 참값 점(구역 중심의 모든 점, 종류 무관; 5.2 나·다의 '참값이 지나 본 사전 정보 면')
        corepts = np.flatnonzero(core); half = length/2
        o2, _ = prism(X[corepts], c - half[:, None]*n, a, b, n, half, O/'tmp'/f'prism_{tile}_{prior}_inner')
        inner_count = np.bincount(o2[o2 >= 0], minlength=len(p['kind']))
        # 솎기 0.1 m: 지붕·땅 수평 칸, 벽은 LoD2 면마다 벽 평면
        keep = np.zeros(len(paired), bool); wk = p['kind'][po] == 2
        if (~wk).any(): keep[~wk] = thin.keep_nearest(X[gi[~wk], :2], 0.1)
        if wk.any(): keep[wk] = thin.keep_nearest(thin.wall_coords(X[gi[wk]], n[po[wk]]), 0.1, group=p['surf'][po[wk]])
        gi, po = gi[keep], po[keep]
        if tree_all is None: tree_all = cKDTree(X, leafsize=32)
        Nm, cnt, resid = pca_normals(X, tree_all, X[gi])
        wall = gkind[gi] == 2; flip = Nm[:, 2] < 0
        if wall.any():
            q = camc.query(X[gi[wall]])[1]; flip[wall] = np.einsum('ij,ij->i', Nm[wall], cam.centres[q] - X[gi[wall]]) < 0
        Nm[flip] *= -1
        # 거리
        if prior == 'LoD2':
            m = loadz(WI/'prior_tiles'/tile/'lod2_mesh.npz', ['V', 'F', 'tri_type']); scene_p = Scene(m['V'], m['F'][m['tri_type'] != 2]); shift = np.zeros((len(gi), 3))
        else:
            m = loadz(WI/'prior_tiles'/tile/'als_mesh.npz', ['V', 'F']); scene_p = Scene(m['V'], m['F']); shift = p['shift_m'][po]
        sP, offP = measure(scene_p, X[gi] - shift, Nm, wall)
        whole = O/'truth/mvs_surface'/f'{tile}.npz'
        if whole.exists():
            mv = loadz(whole, ['V', 'F']); scene_m = Scene(mv['V'], mv['F']); sM, offM = measure(scene_m, X[gi], Nm, wall); del scene_m
        elif (O/'truth/mvs_surface'/f'{tile}_s16.complete.json').exists():  # 16칸 메시(s1_tsdf_s16.py): 점이 놓인 25 m 칸의 메시
            sM = np.full(len(gi), np.nan); offM = np.full(len(gi), -1, np.int8)
            qd = np.clip(((X[gi, 0] - lo[0])//25).astype(int), 0, 3) + 4*np.clip(((X[gi, 1] - lo[1])//25).astype(int), 0, 3)
            for qq in range(16):
                mm = np.flatnonzero(qd == qq)
                if not len(mm): continue
                mv = loadz(O/'truth/mvs_surface'/f'{tile}_s{qq}.npz', ['V', 'F']); scene_m = Scene(mv['V'], mv['F'])
                sM[mm], offM[mm] = measure(scene_m, X[gi[mm]], Nm[mm], wall[mm]); del scene_m
        else:  # 사분면 메시(s1_tsdf_q.py): 점이 놓인 사분면의 메시
            sM = np.full(len(gi), np.nan); offM = np.full(len(gi), -1, np.int8); qd = (X[gi, 0] >= lo[0] + 50).astype(int) + 2*(X[gi, 1] >= lo[1] + 50).astype(int)
            for qq in range(4):
                mm = np.flatnonzero(qd == qq)
                if not len(mm): continue
                mv = loadz(O/'truth/mvs_surface'/f'{tile}_q{qq}.npz', ['V', 'F']); scene_m = Scene(mv['V'], mv['F'])
                sM[mm], offM[mm] = measure(scene_m, X[gi[mm]], Nm[mm], wall[mm]); del scene_m
        del scene_p
        out[prior] = dict(xyz=X[gi], gt_index=gi, normal=Nm, normal_count=cnt, normal_resid=resid, gt_kind=gkind[gi], hag=hag[gi], patch_id=p['patch_id'][po], patch_tile=p['tile'][po], building=p['building'][po], region=p['region'][po],
                          s_P=sP, s_M=sM, offset_P=offP, offset_M=offM, hits=hits[paired][keep])
        un = sel[owner < 0]; ku = np.zeros(len(un), bool); nw = gkind[un] != 2   # 판정 없음 점도 0.1 m 칸으로 솎아 셈 (짝 면이 없는 벽 점은 0.1 m 3차원 칸)
        if nw.any(): ku[nw] = thin.keep_nearest(X[un[nw], :2], 0.1)
        if (~nw).any():
            q = np.floor(X[un[~nw]]/0.1).astype(np.int64); _, first = np.unique(q, axis=0, return_index=True); kw = np.zeros(int((~nw).sum()), bool); kw[first] = True; ku[~nw] = kw
        out[prior + '_unpaired'] = dict(count_by_kind=np.bincount(gkind[un[ku]], minlength=4), count_by_kind_before_thinning=np.bincount(gkind[un], minlength=4))
        out[prior + '_patch'] = dict(patch_id=p['patch_id'], pair_count=pair_count, inner_count=inner_count)
        T.mark(prior)
    save = {}
    for prior in ['LoD2', 'ALS']:
        if prior in out:
            for k, v in out[prior].items(): save[f'{prior}__{k}'] = v
            save[f'{prior}__unpaired_by_kind'] = out[prior + '_unpaired']['count_by_kind']; save[f'{prior}__unpaired_by_kind_before_thinning'] = out[prior + '_unpaired']['count_by_kind_before_thinning']
            for k, v in out[prior + '_patch'].items(): save[f'{prior}__patch_{k}'] = v
    savez(dest, **save)
    rec = dict(at=now(), tile=tile, gt_points=len(X), core=int(core.sum()), in_eval_boxes=int((core & inbox).sum()), used=len(sel), kind_counts={str(k): int((gkind[sel] == k).sum()) for k in [1, 2, 3]},
               rows={pr: int(len(out[pr]['xyz'])) for pr in ['LoD2', 'ALS'] if pr in out}, unpaired={pr: out[pr + '_unpaired']['count_by_kind'].tolist() for pr in ['LoD2', 'ALS'] if pr in out}, marks=T.marks, scientific_verdict=None)
    dump(dest.with_suffix('.json'), rec); print('TRUTH_REST', json.dumps(rec), flush=True)
if __name__ == '__main__':
    for t in sys.argv[1:]: main(t)
