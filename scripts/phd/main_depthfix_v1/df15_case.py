"""Order 7 site figures (CPU): per place, one row per arm run in that scene, three panels — photo crop, same-view render of the result surface (base extraction mesh),
section. Section: vertical plane through the place line A→B, slab ±0.25 m; GT points (gray), per patch in the slab: prior face disc (blue), image-depth face disc (orange),
판 0 target disc (green) with its ±τ band (light green), result mesh vertices in the slab (red). View = among training views where both section ends project inside the frame, the one whose 판 0 target map has the most pixels of the
place patches (no GT, no result). Places from config 'places' (lines below); same place and view for every arm.
usage: df15_case.py <place> <run>[,<run>...] [tag]   writes /docs/figures/case_<place>_<tag>.png/.pdf/.json"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from PIL import Image
import open3d as o3d
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = font_manager.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'; TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'; HW = .25
ARM_KO = {'p0': '판 0', 'p1': '판 1', 'p2': '판 2', 'p3': '판 3', 'p4': '판 4', 'p5': '판 5', 'p6': '판 6', 'p7': '판 7', 'p8': '판 8'}
LABEL = {'R1_floor_band': 'R1 바닥 띠', 'R1_sawtooth_valley': 'R1 톱니 모양 금속 지붕의 골', 'R1_round_wall': 'R1 둥근 건물 벽', 'B173_rooftop_structure': 'B173 주변 옥상 구조물 둘레', 'B173_wing': 'B173 주변 날개'}

def line_of(place, stem, c, tb):
    pl = c['places'][place]
    if place == 'R1_floor_band':
        f = loadz(TE/'addendum4/places/floor_band.npz'); X = f[[k for k in f if 'xyz' in k][0]].astype('f8'); o = X.mean(0)
        _, _, Vt = np.linalg.svd(X[:, :2] - o[:2], full_matrices=False); h = np.r_[Vt[1], 0]; return o[:2] - 4*h[:2], o[:2] + 4*h[:2]
    if place == 'B173_wing':
        r = json.loads((R/'configs/phd/main_rescore_v1/representatives_v1.json').read_text()); r = r['rows'] if isinstance(r, dict) and 'rows' in r else r
        row = next(x for x in (r if isinstance(r, list) else r.values()) if str(x.get('row', x.get('id', ''))) == 'A'); return np.asarray(row['start'][:2], float), np.asarray(row['end'][:2], float)
    if place == 'R1_sawtooth_valley':
        jp = loadz(JP/'patch_LoD2.npz', ['building']); pi = loadz(O/'patchinfo/R1rep_b10__LoD2.npz', ['joined', 'row']); t = loadz(O/'families/base/targets/R1rep_b10__LoD2.npz', ['centre', 'kind', 'in_eval'])
        b = np.where(pi['joined'], jp['building'][np.maximum(pi['row'], 0)], ''); m = (b == pl['building']) & (t['kind'] == 1) & t['in_eval']; xy = t['centre'][m, :2]; c0 = xy.mean(0)
        _, _, Vt = np.linalg.svd(xy - c0, full_matrices=False); s = (xy - c0)@Vt[0]; return c0 + Vt[0]*(s.min() + 17), c0 + Vt[0]*(s.min() + 27)
    if place == 'R1_round_wall':
        ce = np.asarray(pl['centre_xy']); a = np.radians(pl['section_dir_deg']); u = np.r_[np.cos(a), np.sin(a)]; return ce - 4*u, ce + 4*u
    if place == 'B173_rooftop_structure': return np.asarray(pl['section'][0], float), np.asarray(pl['section'][1], float)

def render(mesh_path, K, M, H=741, W=1024):
    m = o3d.t.io.read_triangle_mesh(str(mesh_path)); sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(m)
    yy, xx = np.mgrid[0:H, 0:W]; d = np.stack([(xx - K[0, 2])/K[0, 0], (yy - K[1, 2])/K[1, 1], np.ones_like(xx, float)], -1).reshape(-1, 3)
    Rw = M[:3, :3].T; dw = d@Rw.T; dw /= np.linalg.norm(dw, axis=1)[:, None]; C = cam_centre(M)
    ans = sc.cast_rays(o3d.core.Tensor(np.c_[np.tile(C, (len(dw), 1)), dw].astype('f4'))); n = ans['primitive_normals'].numpy(); hit = np.isfinite(ans['t_hit'].numpy())
    shade = np.where(hit, np.abs((n*dw).sum(1)), np.nan).reshape(H, W); return shade

def main(place, runs, tag='all'):
    c = cfg(); runs = runs.split(','); stem = runs[0].split(':')[0]; site, prior = stem.split('__')
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['centre', 'normal', 'area', 'prior_height_m', 'mvs_mean_m', 'target', 'surface_exists', 'kind'])
    pi = loadz(O/'patchinfo'/f'{stem}.npz', ['tau']); A, B = line_of(place, stem, c, tb); h = np.r_[(B - A)/np.linalg.norm(B - A), 0]; e = np.cross([0, 0, 1.], h); L = np.linalg.norm(B - A)
    o = np.r_[(A + B)/2, 0]
    def to2(X): rel = X - o; return rel@h, X[:, 2], np.abs(rel@e)
    s_, z_, w_ = to2(tb['centre']); inpl = (w_ <= HW) & (np.abs(s_) <= L/2); pids = np.flatnonzero(inpl & tb['surface_exists'])
    idx = json.loads((O/'maps/base/base'/stem/'index.json').read_text())['views']; best = None; mask = np.zeros(len(tb['area']), bool); mask[pids] = True
    zl = np.nanmedian(tb['centre'][pids, 2]) if len(pids) else 0.; ends = np.c_[np.r_[A[None], B[None]], np.full(2, zl)]
    for name in idx:
        Kv = np.asarray(idx[name]['K']); Mv = np.asarray(idx[name]['W2C']); qv = ends@Mv[:3, :3].T + Mv[:3, 3]
        if (qv[:, 2] <= 1).any(): continue
        uvv = np.c_[Kv[0, 0]*qv[:, 0]/qv[:, 2] + Kv[0, 2], Kv[1, 1]*qv[:, 1]/qv[:, 2] + Kv[1, 2]]
        if not ((uvv[:, 0] >= 40) & (uvv[:, 0] <= 984) & (uvv[:, 1] >= 40) & (uvv[:, 1] <= 701)).all(): continue   # both section ends well inside the frame
        own = loadz(O/'maps/base/base'/stem/f'{name}.npz', ['owner'])['owner']; k = int(mask[own[own >= 0]].sum())
        if best is None or k > best[1]: best = (name, k)
    view = best[0]; K = np.asarray(idx[view]['K']); M = np.asarray(idx[view]['W2C'])
    G = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz']; gs, gz, gw = to2(G); gm = (gw <= HW) & (np.abs(gs) <= L/2)
    pts = np.c_[A, np.full(2, np.nanmedian(tb['centre'][pids, 2]) if len(pids) else 0)]; Pc = np.r_[pts, [[*B, pts[0, 2]]]] if False else np.c_[np.r_[A[None], B[None]], np.full(2, np.nanmedian(tb['centre'][pids, 2]) if len(pids) else 0)]
    q = Pc@M[:3, :3].T + M[:3, 3]; uv = np.c_[K[0, 0]*q[:, 0]/q[:, 2] + K[0, 2], K[1, 1]*q[:, 1]/q[:, 2] + K[1, 2]]
    lo_, hi_ = uv.min(0) - 90, uv.max(0) + 90; x0, x1 = int(np.clip(lo_[0], 0, 1023)), int(np.clip(hi_[0], 1, 1024)); y0, y1 = int(np.clip(lo_[1], 0, 740)), int(np.clip(hi_[1], 1, 741))
    img = np.asarray(Image.open(S0/'fork_inputs/s61'/site/f'scene_{prior}'/'images'/f'{view}.jpg').convert('RGB').resize((1024, 741)))
    nrow = len(runs); fig, ax = plt.subplots(nrow, 3, figsize=(15, 3.6*nrow), squeeze=False, constrained_layout=True); meta = []
    for i, rs in enumerate(runs):
        st, run = rs.split(':'); mesh = O/'gtj/meshes'/f'{st}__df_{run}_base'/'final.ply'; arm = run.rsplit('_s', 1)[0]; lab = f"{ARM_KO[arm]} (씨앗 {run.rsplit('_s', 1)[1]})"
        ax[i, 0].imshow(img[y0:y1, x0:x1]); ax[i, 0].plot(uv[:, 0] - x0, uv[:, 1] - y0, 'y-', lw=2); ax[i, 0].set_title(f'{lab} · 사진'); ax[i, 0].axis('off')
        if mesh.exists():
            sh = render(mesh, K, M); ax[i, 1].imshow(sh[y0:y1, x0:x1], cmap='gray', vmin=0, vmax=1); ax[i, 1].plot(uv[:, 0] - x0, uv[:, 1] - y0, 'y-', lw=2)
            mm = o3d.io.read_triangle_mesh(str(mesh)); V = np.asarray(mm.vertices); vs, vz, vw = to2(V); vm = (vw <= HW) & (np.abs(vs) <= L/2)
        else: vm = None; ax[i, 1].text(.5, .5, '결과 면 없음', ha='center')
        ax[i, 1].set_title(f'{lab} · 같은 시점의 결과 면'); ax[i, 1].axis('off')
        a = ax[i, 2]; a.scatter(gs[gm], gz[gm], s=1, c='0.6', label='참값')
        for p in pids:
            n = tb['normal'][p]/np.linalg.norm(tb['normal'][p]); r = np.sqrt(tb['area'][p]/np.pi); t_ = np.cross(n, e); t_ = t_/max(np.linalg.norm(t_), 1e-9)
            for hh, col, lw_ in [(tb['prior_height_m'][p], '#1f5fd6', 1.2), (tb['mvs_mean_m'][p], '#ff7f0e', 1.2)]:
                if not np.isfinite(hh): continue
                cc = tb['centre'][p] + hh*n; seg = np.stack([cc - r*t_, cc + r*t_]); ss, zz, _ = to2(seg); a.plot(ss, zz, color=col, lw=lw_, alpha=.8)
            cc = tb['target'][p]; seg = np.stack([cc - r*t_, cc + r*t_]); ss, zz, _ = to2(seg); a.plot(ss, zz, color='#2ca02c', lw=1.6)
            off = pi['tau'][p]*n; for_band = np.stack([cc - r*t_ + off, cc + r*t_ + off, cc + r*t_ - off, cc - r*t_ - off]); bs, bz, _ = to2(for_band); a.fill(bs, bz, color='#2ca02c', alpha=.12, lw=0)
        if vm is not None: a.scatter(vs[vm], vz[vm], s=2, c='#d62728', label='결과 면')
        a.set_xlim(-L/2, L/2); a.set_aspect('equal', adjustable='datalim'); a.set_xlabel('단면 거리 (m)'); a.set_ylabel('높이 (m)'); a.set_title(f'{lab} · 단면')
        if i == 0:
            from matplotlib.lines import Line2D
            a.legend(handles=[Line2D([], [], color='0.6', marker='.', ls='', label='참값'), Line2D([], [], color='#1f5fd6', label='사전 정보 면'), Line2D([], [], color='#ff7f0e', label='영상 깊이 면'),
                              Line2D([], [], color='#2ca02c', label='판 0 목표 ± 허용'), Line2D([], [], color='#d62728', marker='.', ls='', label='결과 면')], fontsize=7, loc='best')
        meta.append(dict(run=rs, mesh=str(mesh), mesh_exists=mesh.exists()))
    fig.suptitle(f'{LABEL[place]} ({STEM_KO[stem]})'); p = D/'figures'/f'case_{place}_{stem}_{tag}'; fig.savefig(p.with_suffix('.png'), dpi=100); fig.savefig(p.with_suffix('.pdf')); plt.close(fig)
    dump(p.with_suffix('.json'), dict(place=place, label=LABEL[place], stem=stem, view=view, view_place_pixels=best[1], line_A=A.tolist(), line_B=B.tolist(), slab_half_m=HW, patches_in_section=int(len(pids)),
         rows=meta, rule=__doc__, scientific_verdict=None))
    print('CASE', place, stem, view, len(pids), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
