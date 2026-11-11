"""Prototype v2 of the revised video layout (CPU): E mesh and F judgment map + Gaussians from the same oblique camera,
rotation sample at 30,000, and G sections chosen with training results. Colours: one meaning per colour."""
import sys
from common import *
from tl_defs import TAU
from derive_states import scope_mask
import open3d as o3d
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import EllipseCollection, LineCollection
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
P_ = '/fonts/NotoSansCJK-Regular.ttc'; fm.fontManager.addfont(P_); plt.rcParams['font.family'] = fm.FontProperties(fname=P_).get_name(); plt.rcParams['axes.unicode_minus'] = False
A = O/'analysis'; OUT = O/'proto_v2'; OUT.mkdir(exist_ok=True)
JC = {0: '#7FA7D9', 2: '#D85A30', 1: '#1D9E75', 4: '#E8B931'}; JDARK = {0: '#185FA5', 2: '#993C1D', 1: '#0F6E56', 4: '#854F0B'}; PALEJ = {0: '#B5D4F4', 2: '#F5C4B3', 1: '#9FE1CB', 4: '#FAC775'}; JN = {0: '일치', 2: '보정', 1: '보존', 4: '결측'}
PINK = '#C2378A'; GREYG = '#888780'; NAVY = '#16263d'; FIT = np.array(to_rgb('#D3D1C7')); P0 = np.array(to_rgb('#AFA9EC')); P1 = np.array(to_rgb('#3C3489'))
LT = np.array([-.35, -.45, .82]); LT /= np.linalg.norm(LT)

def basis(c, az, el=35):
    up = np.array(c['coordinates']['up']); up /= np.linalg.norm(up); east = np.array([1., 0, 0]); east -= (east@up)*up; east /= np.linalg.norm(east); north = np.cross(up, east)
    a, e = np.radians(az), np.radians(el); out = np.cos(e)*(np.cos(a)*east+np.sin(a)*north)+np.sin(e)*up; f = -out; r = np.cross(f, up); r /= np.linalg.norm(r); return np.stack([r, np.cross(r, f), f])

class Scene:
    def __init__(self):
        self.c = cfg(); sc = self.c['scope']; g = sc['buffered_footprint']; ring = np.asarray(g['coordinates'][0] if g['type'] == 'Polygon' else g['coordinates'][0][0], float)[:, :2]
        corners = np.array([[x, y, z] for x in (ring[:, 0].min(), ring[:, 0].max()) for y in (ring[:, 1].min(), ring[:, 1].max()) for z in (sc['z_min'], sc['z_max'])]); self.ctr = corners.mean(0)
        hw = [np.abs((corners-self.ctr)@basis(self.c, az)[:2].T).max(0) for az in range(0, 360, 45)]; h = np.max(hw, 0)*1.04; self.half = (max(h[0], h[1]*1.5), max(h[0], h[1]*1.5)/1.5)
        procb = np.array(json.loads((PF/'figures/proc_30000_1_a.json').read_text())['camera']['basis']); self.basis_check = float(np.abs(procb-basis(self.c, 180)).max())
        t = loadz(FT/'targets'/f'{STEM}.npz'); valid = np.flatnonzero((t['region'] >= 0) & np.isfinite(t['target']).all(1) & np.isfinite(t['normal']).all(1) & np.isfinite(t['sigma']) & (t['sigma'] > 0))
        ins = scope_mask(t['target'][valid].astype(float), self.c); self.pid = valid[ins]; self.pt = t['target'][self.pid].astype(float); self.pn = t['normal'][self.pid].astype(float); self.pj = t['judge_region'][self.pid]
        self.pr = np.sqrt(t['area'][self.pid]/np.pi); self.psig = t['sigma'][self.pid].astype(float); self.pgroup = loadz(PF/'work/patch_groups.npz', ['group'])['group'][self.pid]
        self.m30 = self.mesh('30000'); self.drape()
        saves = [json.loads(l) for l in (RUNM/'trainlog/saves.jsonl').read_text().splitlines()]; self.seq = {s['name']: s['seq'] for s in saves}; self.order = [s['name'] for s in saves]
        self.dl = loadz(DER/'events/delete.npz'); self.W = set(loadz(DER/'gaussians/0.npz')['init_id'][loadz(DER/'gaussians/0.npz')['group33'] == 1].tolist())
    def mesh(self, name):
        z = loadz(A/f'mesh_{name}.npz', ['vertices', 'faces', 'vertex_error_m']); sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh()
        tm.vertex.positions = o3d.core.Tensor(z['vertices'].astype('f4')); tm.triangle.indices = o3d.core.Tensor(z['faces'].astype('i4')); sc.add_triangles(tm); return dict(scene=sc, err=np.abs(z['vertex_error_m'][z['faces']].mean(1)), V=z['vertices'], F=z['faces'], verr=z['vertex_error_m'])
    def drape(self):
        o = np.c_[self.pt[:, :2], np.full(len(self.pt), self.c['scope']['z_max']+5)]; r = self.m30['scene'].cast_rays(o3d.core.Tensor(np.c_[o, np.tile([0, 0, -1.], (len(o), 1))].astype('f4')))
        t = r['t_hit'].numpy(); self.pz = np.where(np.isfinite(t), o[:, 2]-t, self.pt[:, 2])
    def raster(self, m, B, W=900):
        H = int(W*self.half[1]/self.half[0]); xs = np.linspace(-self.half[0], self.half[0], W); ys = np.linspace(self.half[1], -self.half[1], H); X, Y = np.meshgrid(xs, ys)
        org = self.ctr+X[..., None]*B[0]+Y[..., None]*B[1]-400*B[2]; rays = np.concatenate([org, np.broadcast_to(B[2], org.shape)], -1).reshape(-1, 6).astype('f4')
        r = m['scene'].cast_rays(o3d.core.Tensor(rays)); t = r['t_hit'].numpy(); hit = np.isfinite(t); pid = r['primitive_ids'].numpy(); nrm = r['primitive_normals'].numpy()
        e = np.where(hit, m['err'][pid.clip(0, len(m['err'])-1)], 0); a = np.clip((e-TAU/100)/(1-TAU/100), 0, 1)[:, None]
        col = np.where((e <= TAU/100)[:, None], FIT, P0*(1-a)+P1*a); sh = .55+.45*np.abs(nrm@LT); img = np.where(hit[:, None], col*sh[:, None], 1.).reshape(H, W, 3)
        return img, np.where(hit, t-400, np.inf).reshape(H, W)
    def proj(self, P, B): q = (P-self.ctr)@B.T; return q[:, 0], q[:, 1], q[:, 2]
    def visible(self, P, B, depth, tol=.5):
        x, y, d = self.proj(P, B); H, W = depth.shape; col = np.clip(((x+self.half[0])/(2*self.half[0])*(W-1)).round().astype(int), 0, W-1); row = np.clip(((self.half[1]-y)/(2*self.half[1])*(H-1)).round().astype(int), 0, H-1)
        return d <= depth[row, col]+tol, x, y

def draw_E(ax, S, img, B, line=None, outline=True, depth=None):
    ax.imshow(img, extent=(-S.half[0], S.half[0], -S.half[1], S.half[1])); ax.set_xlim(-S.half[0], S.half[0]); ax.set_ylim(-S.half[1], S.half[1]); ax.set_aspect('equal'); ax.axis('off')
    if outline: wrong_outline(ax, S, B, depth)
    if line is not None: x, y, _ = S.proj(line, B); ax.plot(x, y, color=NAVY, lw=2)

def wrong_outline(ax, S, B, depth):
    m = S.pgroup == 1; P = np.c_[S.pt[m, :2], S.pz[m]]; vis, x, y = S.visible(P, B, depth, 1.); r = S.pr[m]
    H, W = 300, int(300*S.half[0]/S.half[1]); xs = np.linspace(-S.half[0], S.half[0], W); ys = np.linspace(-S.half[1], S.half[1], H); mask = np.zeros((H, W), bool)
    for xi, yi, ri in zip(x[vis], y[vis], np.maximum(r[vis]*3.0, .8)):
        c0, c1 = np.searchsorted(xs, [xi-ri, xi+ri]); r0, r1 = np.searchsorted(ys, [yi-ri, yi+ri])
        if c1 > c0 and r1 > r0: X, Y = np.meshgrid(xs[c0:c1], ys[r0:r1]); mask[r0:r1, c0:c1] |= (X-xi)**2+(Y-yi)**2 <= ri*ri
    from scipy.ndimage import binary_closing, binary_opening, label
    mask = binary_opening(binary_closing(mask, iterations=7), iterations=3); lab, nlab = label(mask)
    if nlab: sizes = np.bincount(lab.ravel())[1:]; mask = np.isin(lab, 1+np.flatnonzero(sizes >= .02*sizes.max()))
    ax.contour(xs, ys, mask.astype(float), levels=[.5], colors=PINK, linewidths=2.2)

def draw_F(ax, S, d, B, depth, prev=None, line=None):
    vis, x, y = S.visible(np.c_[S.pt[:, :2], S.pz], B, depth, .6); _, _, dd = S.proj(np.c_[S.pt[:, :2], S.pz], B)
    n = S.pn/np.linalg.norm(S.pn, axis=1)[:, None]; t1 = np.cross(n, [0, 0, 1.]); bad = np.linalg.norm(t1, axis=1) < 1e-6; t1[bad] = [1, 0, 0]; t1 /= np.linalg.norm(t1, axis=1)[:, None]; t2 = np.cross(n, t1)
    M = np.stack([np.stack([t1@B[0], t2@B[0]], 1), np.stack([t1@B[1], t2@B[1]], 1)], 1)*S.pr[:, None, None]; U, s, _ = np.linalg.svd(M); ang = np.degrees(np.arctan2(U[:, 1, 0], U[:, 0, 0]))
    o = np.flatnonzero(vis)[np.argsort(-dd[vis])]
    ax.add_collection(EllipseCollection(2*s[o, 0], 2*s[o, 1], ang[o], units='xy', offsets=np.c_[x[o], y[o]], offset_transform=ax.transData, facecolors=[PALEJ[int(j)] for j in S.pj[o]], edgecolors='none'))
    wrong_outline(ax, S, B, depth)
    P = d['xyz'].astype(float); gv, gx, gy = S.visible(P, B, depth, .5); wrong = d['group33'] == 1; tag = d['target_tag']; up = gv | wrong
    for msk, kw in [((tag == 0) & ~wrong & up, dict(s=1, c=GREYG, lw=0, alpha=.6)), ((tag == 2) & ~wrong & up, dict(s=5, facecolors='none', edgecolors='#2C2C2A', linewidths=.35, alpha=.7))]: ax.scatter(gx[msk], gy[msk], **kw)
    for j, col in JC.items():
        msk = (tag == 1) & (d['judgment'] == j) & ~wrong & up; ax.scatter(gx[msk], gy[msk], s=1.2, c=JDARK[j], lw=0, alpha=.8)
    ax.scatter(gx[wrong], gy[wrong], s=4, c=PINK, lw=0)
    if prev is not None:
        e = S.dl; m = (e['seq'] > S.seq[prev]) & (e['seq'] <= S.seq[d['_name']]); ex, ey, _ = S.proj(e['xyz'][m].astype(float), B); w = np.isin(e['init_id'][m], np.fromiter(S.W, 'i8'))
        ax.scatter(ex[~w], ey[~w], marker='x', s=6, c='#5F5E5A', linewidths=.5); ax.scatter(ex[w], ey[w], marker='x', s=14, c=PINK, linewidths=.8)
    if line is not None: lx, ly, _ = S.proj(line, B); ax.plot(lx, ly, color=NAVY, lw=2)
    ax.set_xlim(-S.half[0], S.half[0]); ax.set_ylim(-S.half[1], S.half[1]); ax.set_aspect('equal'); ax.axis('off')

def section_line(S, kind, at):
    b = json.loads((A/'band.json').read_text()); c2, a1, a2 = map(np.array, (b['c2'], b['a1'], b['a2']))
    ax_, nrm = (a2, a1) if kind == 'cross' else (a1, a2); s = np.linspace(-60, 60, 1201); P = c2+(at+.5)*nrm+s[:, None]*ax_
    m = scope_mask(np.c_[P, np.full(len(P), -30.)], dict(S.c, scope=dict(S.c['scope'], z_min=-99, z_max=99))); P = P[m]
    o = np.c_[P, np.full(len(P), S.c['scope']['z_max']+5)]; r = S.m30['scene'].cast_rays(o3d.core.Tensor(np.c_[o, np.tile([0, 0, -1.], (len(o), 1))].astype('f4'))); t = r['t_hit'].numpy()
    L = np.c_[P, np.where(np.isfinite(t), o[:, 2]-t, np.nan)][np.isfinite(t)]; L = L[L[:, 2] > S.c['scope']['ground_z']+10]; return L, (c2, a1, a2, ax_, nrm)

def cut(V, F, c2, nrm, at, axv):
    vv = (V[:, :2]-c2)@nrm-(at+.5); sg = np.sign(vv[F]); T = F[(sg.min(1) < 0) & (sg.max(1) > 0)]; E = []
    for a, b in [(0, 1), (1, 2), (2, 0)]:
        va, vb = vv[T[:, a]], vv[T[:, b]]; m = (va*vb) < 0; w = np.where(m, va/np.where(m, va-vb, 1), np.nan); E.append(V[T[:, a]]+w[:, None]*(V[T[:, b]]-V[T[:, a]]))
    E = np.stack(E, 1); ok = np.isfinite(E[:, :, 0]); keep = ok.sum(1) == 2; E = E[keep]; ok = ok[keep]
    if not len(E): return np.zeros((0, 2, 2))
    P = np.stack([E[i][ok[i]] for i in range(len(E))]); return np.stack([(P[:, :, :2]-c2)@axv, P[:, :, 2]], 2)

def main(step='all'):
    S = Scene(); print('basis check vs PROCFIG az180', S.basis_check, flush=True); B180 = basis(S.c, 180); ground = S.c['scope']['ground_z']
    lines = {'cross': section_line(S, 'cross', 28.), 'long': section_line(S, 'long', -8.)}
    states = [('0', None), ('2000', '1900'), ('7000', '6500'), ('30000', '27500')]
    fig, axs = plt.subplots(len(states), 2, figsize=(16, 4.6*len(states)), facecolor='white'); _, d30 = S.raster(S.m30, B180)
    for i, (n, prev) in enumerate(states):
        img, dep = S.raster(S.mesh(n), B180); d = dict(loadz(DER/'gaussians'/f'{n}.npz')); d['_name'] = n
        draw_E(axs[i, 0], S, img, B180, lines['cross'][0], depth=d30); draw_F(axs[i, 1], S, d, B180, d30, prev, lines['cross'][0])
        axs[i, 0].set_title(f'{int(n):,}회 · E 메시 표면', loc='left', fontsize=13); axs[i, 1].set_title(f'{int(n):,}회 · F 판정 지도 + 가우시안', loc='left', fontsize=13)
    legend(fig); fig.tight_layout(rect=(0, .03, 1, 1)); fig.savefig(OUT/'EF_oblique_4states.png', dpi=110); plt.close(fig); print('EF done', flush=True)
    d = dict(loadz(DER/'gaussians/30000.npz')); d['_name'] = '30000'; fig, axs = plt.subplots(2, 4, figsize=(20, 7.5), facecolor='white')
    for k, az in enumerate([180, 270, 0, 90]):
        B = basis(S.c, az); img, dep = S.raster(S.m30, B, 700); draw_E(axs[0, k], S, img, B, lines['cross'][0], depth=dep); draw_F(axs[1, k], S, d, B, dep, None, lines['cross'][0]); axs[0, k].set_title(f'방위 {az}°', fontsize=13)
    fig.tight_layout(); fig.savefig(OUT/'EF_rotation_30000.png', dpi=100); plt.close(fig); print('rotation done', flush=True)
    rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz']); prior = loadz(S1/'defs'/SITE/'prior_ALS.npz', ['V', 'F'])
    for kind, at in [('cross', 28.), ('long', -8.)]:
        _, (c2, a1, a2, axv, nrm) = lines[kind]; fig, axs = plt.subplots(1, 3, figsize=(20, 5.2), facecolor='white', sharey=True)
        R = rows['xyz'].astype(float); rv = (R[:, :2]-c2)@nrm; rm = (rv >= at) & (rv < at+1) & scope_mask(R, S.c); pseg = cut(prior['V'].astype(float), prior['F'], c2, nrm, at, axv)
        pv = (S.pt[:, :2]-c2)@nrm; pm = (pv >= at) & (pv < at+1)
        for k, n in enumerate(['0', '2000', '30000']):
            ax = axs[k]; m = S.mesh(n); seg = cut(m['V'].astype(float), m['F'], c2, nrm, at, axv); d = loadz(DER/'gaussians'/f'{n}.npz'); gp = d['xyz'].astype(float); gm = (((gp[:, :2]-c2)@nrm) >= at) & (((gp[:, :2]-c2)@nrm) < at+1); gs = (gp[:, :2]-c2)@axv
            for j in JC:
                q = pm & (S.pj == j); ax.errorbar(((S.pt[q, :2]-c2)@axv), S.pt[q, 2]-ground, yerr=1.96*S.psig[q], fmt='none', ecolor=PALEJ[j], elinewidth=3, alpha=.9)
            ax.add_collection(LineCollection(np.stack([pseg[:, :, 0], pseg[:, :, 1]-ground], 2), colors=PINK, linewidths=1.2, linestyles=(0, (5, 3))))
            ax.scatter((R[rm, :2]-c2)@axv, R[rm, 2]-ground, s=1.5, c='black', lw=0)
            ax.add_collection(LineCollection(np.stack([seg[:, :, 0], seg[:, :, 1]-ground], 2), colors=NAVY, linewidths=1.2))
            wr = d['group33'] == 1; tag = d['target_tag']
            ax.scatter(gs[gm & (tag == 0) & ~wr], gp[gm & (tag == 0) & ~wr, 2]-ground, s=3, c=GREYG, lw=0)
            ax.scatter(gs[gm & (tag == 2) & ~wr], gp[gm & (tag == 2) & ~wr, 2]-ground, s=9, facecolors='none', edgecolors='#2C2C2A', linewidths=.5)
            for j, col in JC.items():
                q = gm & (tag == 1) & (d['judgment'] == j) & ~wr; ax.scatter(gs[q], gp[q, 2]-ground, s=4, c=col, lw=0)
            ax.scatter(gs[gm & wr], gp[gm & wr, 2]-ground, s=22, c=PINK, edgecolors='white', linewidths=.6, zorder=6); ax.set_ylim(12, 25.5); ax.set_title(f'{int(n):,}회', fontsize=13); ax.set_xlabel(('건물 가로 방향' if kind == 'cross' else '지붕 긴 방향')+' (m)')
            lim = np.r_[(R[rm, :2]-c2)@axv]; ax.set_xlim(lim.min()-1, lim.max()+1)
        axs[0].set_ylabel('지면 위 높이 (m)'); legend(fig); fig.tight_layout(rect=(0, .08, 1, 1)); fig.savefig(OUT/f'G_{kind}.png', dpi=110); plt.close(fig); print('G', kind, rm.sum(), flush=True)
    dump(OUT/'proto_v2.json', dict(at=now(), camera='az 180 el 35 orthographic (same basis as PROCFIG rank-1, max diff %.2e)' % S.basis_check, half_extent_m=list(S.half),
         occlusion='Gaussians and judgment patches drawn only where not behind the 30,000 mesh from the same camera (+0.5 m); wrong-lineage always drawn',
         judgment_regions='valid target patches in scope, discs of patch area draped on the 30,000 mesh height', sections=dict(cross=28., long=-8.), scientific_verdict=None))

def legend(fig):
    h = [Patch(color=PALEJ[j], label=f'바탕 {JN[j]}') for j in [0, 2, 1, 4]]+[Line2D([], [], marker='o', ls='', color=JDARK[j], label=f'묶임({JN[j]})') for j in [0, 2, 1, 4]]
    h += [Line2D([], [], marker='o', ls='', markerfacecolor='none', markeredgecolor='#2C2C2A', label='풀림'), Line2D([], [], marker='o', ls='', color=GREYG, label='처음부터 자유'),
          Line2D([], [], marker='o', ls='', color=PINK, label='옛 지붕 출신 · 분홍 선 = 옛 지붕/틀린 판정 자리'), Line2D([], [], marker='x', ls='', color='#5F5E5A', label='직전 뒤 지워짐'),
          Patch(color=FIT, label='면 맞음'), Patch(color=P1, label='면 어긋남(진할수록 멂)'), Line2D([], [], color=NAVY, label='단면 위치 · 면'), Line2D([], [], marker='o', ls='', color='black', ms=3, label='참값')]
    fig.legend(handles=h, loc='lower center', ncol=8, frameon=False, fontsize=10)

if __name__ == '__main__': main(*sys.argv[1:])
