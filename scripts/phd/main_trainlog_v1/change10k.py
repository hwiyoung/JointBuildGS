"""Video critique follow-up (2026-11-11, CPU, no training): what changes after 10,000 iterations, and where.
Mesh: scoped faces of analysis/mesh_<n>.npz (frames.prep_mesh: per-vertex signed distance to the dense GT along the GT normal; GT used only for scoring).
Change k -> k2: a face of k2 farther than TAU from mesh k is 'new'; a face of k farther than TAU from mesh k2 is 'gone'. Area by class
(roof |nz| >= .7, wall |nz| <= .3, other) and by fit (|err| <= TAU). XY 1 m grid of the change in unfit area 10,000 -> 30,000 for zoom-spot candidates.
Gaussians: group33 == 1 (wrong-judgment lineage) at saved states: count, bound, opacity, signed height to the dense GT, offset to own target."""
import sys
from common import *
from tl_defs import TAU
import open3d as o3d
from scipy.spatial import cKDTree
from scipy.ndimage import label
OUTD = O/'analysis/change10k'; OUTD.mkdir(parents=True, exist_ok=True); T = TAU/100
ITS = ['7000', '10000', '15000', '20000', '30000']; PAIRS = [('7000', '10000'), ('10000', '15000'), ('15000', '30000'), ('10000', '30000')]
CLS = {0: 'roof', 1: 'wall', 2: 'other'}

def site_tree():
    t = loadz(FT/'targets'/f'{STEM}.npz', ['target']); pg = loadz(PF/'work/patch_groups.npz', ['group'])['group']
    return {g: cKDTree(t['target'][pg == g][:, :2].astype(float)) for g in (1, 2)}

def mesh(n, st):
    z = loadz(O/'analysis'/f'mesh_{n}.npz', ['vertices', 'faces', 'vertex_error_m']); V = z['vertices'].astype(float); F = z['faces']
    a, b, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]; cr = np.cross(b-a, c_-a); area = .5*np.linalg.norm(cr, axis=1); nz = np.abs(cr[:, 2])/np.maximum(2*area, 1e-12)
    cen = (a+b+c_)/3; err = z['vertex_error_m'][F].mean(1); cls = np.where(nz >= .7, 0, np.where(nz <= .3, 1, 2))
    site = np.zeros(len(F), 'i1')
    for g in (2, 1): d, _ = st[g].query(cen[:, :2], distance_upper_bound=.5); site[np.isfinite(d)] = g
    sc = o3d.t.geometry.RaycastingScene(); tm = o3d.t.geometry.TriangleMesh(); tm.vertex.positions = o3d.core.Tensor(V.astype('f4')); tm.triangle.indices = o3d.core.Tensor(F.astype('i4')); sc.add_triangles(tm)
    return dict(cen=cen, area=area, err=err, cls=cls, site=site, sc=sc)

def summary(m):
    fit = np.abs(m['err']) <= T; out = dict(area_m2=float(m['area'].sum()), fit_pct=float(100*m['area'][fit].sum()/m['area'].sum()),
               above_gt_area_m2=float(m['area'][m['err'] > T].sum()), below_gt_area_m2=float(m['area'][m['err'] < -T].sum()))
    for k, nm in CLS.items():
        s = m['cls'] == k; out[f'{nm}_area_m2'] = float(m['area'][s].sum()); out[f'{nm}_fit_pct'] = float(100*m['area'][s & fit].sum()/max(m['area'][s].sum(), 1e-9))
    for g, nm in [(1, 'wrong_site'), (2, 'correction_site')]:
        s = m['site'] == g; out[f'{nm}_area_m2'] = float(m['area'][s].sum()); out[f'{nm}_fit_pct'] = float(100*m['area'][s & fit].sum()/max(m['area'][s].sum(), 1e-9))
    return out

def change(m0, m1):
    dn = m0['sc'].compute_distance(o3d.core.Tensor(m1['cen'].astype('f4'))).numpy(); dg = m1['sc'].compute_distance(o3d.core.Tensor(m0['cen'].astype('f4'))).numpy()
    new, gone = dn > T, dg > T; out = dict()
    for lab, m, sel in [('new', m1, new), ('gone', m0, gone)]:
        fit = np.abs(m['err']) <= T; out[f'{lab}_area_m2'] = float(m['area'][sel].sum()); out[f'{lab}_fit_area_m2'] = float(m['area'][sel & fit].sum())
        out[f'{lab}_above_gt_area_m2'] = float(m['area'][sel & (m['err'] > T)].sum()); out[f'{lab}_below_gt_area_m2'] = float(m['area'][sel & (m['err'] < -T)].sum())
        for k, nm in CLS.items(): out[f'{lab}_{nm}_area_m2'] = float(m['area'][sel & (m['cls'] == k)].sum()); out[f'{lab}_{nm}_fit_area_m2'] = float(m['area'][sel & (m['cls'] == k) & fit].sum())
        for g, nm in [(1, 'wrong_site'), (2, 'correction_site')]: out[f'{lab}_{nm}_area_m2'] = float(m['area'][sel & (m['site'] == g)].sum())
    keep = ~new; w = m1['area'][keep]; o = np.argsort(dn[keep]); cw = np.cumsum(w[o]); out['kept_shift_median_cm'] = float(100*dn[keep][o][np.searchsorted(cw, cw[-1]/2)])
    out['kept_area_m2'] = float(w.sum()); return out, new, gone

def grid(m0, m1, gone, new):
    lo = np.minimum(m0['cen'][:, :2].min(0), m1['cen'][:, :2].min(0)); hi = np.maximum(m0['cen'][:, :2].max(0), m1['cen'][:, :2].max(0)); nb = np.ceil(hi-lo).astype(int)+1
    def h(m, sel): ij = np.floor(m['cen'][sel, :2]-lo).astype(int); g = np.zeros(nb); np.add.at(g, (ij[:, 0], ij[:, 1]), m['area'][sel]); return g
    u0, u1 = h(m0, np.abs(m0['err']) > T), h(m1, np.abs(m1['err']) > T); gu, nf = h(m0, gone & (np.abs(m0['err']) > T)), h(m1, new & (np.abs(m1['err']) <= T))
    savez(OUTD/'grid_10000_30000.npz', origin=lo, cell_m=1., unfit_10000=u0, unfit_30000=u1, gone_unfit=gu, new_fit=nf)
    d = u0-u1; lab, nl = label(d > .5); rows = []
    for k in range(1, nl+1):
        s = lab == k; ii, jj = np.nonzero(s); w = d[s]; rows.append(dict(cells=int(s.sum()), unfit_drop_m2=float(w.sum()), gone_unfit_m2=float(gu[s].sum()), new_fit_m2=float(nf[s].sum()),
                    x=float(lo[0]+.5+(ii*w).sum()/w.sum()), y=float(lo[1]+.5+(jj*w).sum()/w.sum()), x0=float(lo[0]+ii.min()), x1=float(lo[0]+ii.max()+1), y0=float(lo[1]+jj.min()), y1=float(lo[1]+jj.max()+1)))
    rows.sort(key=lambda r: -r['unfit_drop_m2']); return rows[:12]

def where_unfit(m, sel):
    """Where are the gone/new unfit faces: class split and height band."""
    a = m['area'][sel]; z = m['cen'][sel, 2]; return dict(area_m2=float(a.sum()), z_p10_p50_p90=[float(v) for v in np.percentile(z, [10, 50, 90])] if len(z) else None)

def gauss():
    g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz', 'normal']); gx = g['xyz'].astype(float); gn = g['normal'].astype(float); gn[gn[:, 2] < 0] *= -1; tr = cKDTree(gx); rows = []
    for n in ITS:
        d = loadz(DER/'gaussians'/f'{n}.npz'); w = d['group33'] == 1; P = d['xyz'][w].astype(float); dist, idx = tr.query(P, workers=8); sd = np.sign(((P-gx[idx])*gn[idx]).sum(1))*dist
        op = d['opacity'][w]; bound = d['target_tag'][w] == 1; off = np.abs(P[:, 2]-d['target_xyz'][w][:, 2])
        rows.append(dict(iteration=int(n), n=int(w.sum()), bound=int(bound.sum()), opacity_median=float(np.median(op)) if w.any() else None,
                         above_gt_gt_tau=int((sd > T).sum()), above_gt_gt_1m=int((sd > 1).sum()), fit_tau=int((np.abs(sd) <= T).sum()),
                         above_1m_and_opacity_gt_0p5=int(((sd > 1) & (op > .5)).sum()), signed_gt_m_p10_p50_p90=[float(v) for v in np.percentile(sd, [10, 50, 90])] if w.any() else None,
                         bound_target_offset_m_median=float(np.median(off[bound])) if bound.any() else None))
        print('GAUSS', rows[-1], flush=True)
    return rows

def main():
    st = site_tree(); M = {}; S = {}
    for n in ITS: M[n] = mesh(n, st); S[n] = summary(M[n]); print('MESH', n, S[n], flush=True)
    C = {}; spots = None; wh = {}
    for a, b in PAIRS:
        C[f'{a}->{b}'], new, gone = change(M[a], M[b]); print('CHANGE', a, b, C[f'{a}->{b}'], flush=True)
        if (a, b) == ('10000', '30000'):
            spots = grid(M[a], M[b], gone, new); fit0 = np.abs(M[a]['err']) <= T; fit1 = np.abs(M[b]['err']) <= T
            wh = dict(gone_unfit=where_unfit(M[a], gone & ~fit0), gone_unfit_above=where_unfit(M[a], gone & (M[a]['err'] > T)), new_fit=where_unfit(M[b], new & fit1), new_unfit=where_unfit(M[b], new & ~fit1))
    G = gauss()
    dump(OUTD/'change10k.json', dict(at=now(), tau_m=T, mesh=S, change=C, unfit_drop_spots_10000_30000=spots, where_10000_30000=wh, wrong_lineage_gaussians=G,
         rule='mesh faces scoped (frames.prep_mesh); fit = |signed distance to dense GT| <= TAU; new/gone = farther than TAU from the other mesh; GT for scoring only', scientific_verdict=None))
    print('DONE', flush=True)

if __name__ == "__main__" and len(sys.argv) == 1: main()

def spots_detail():
    """Composition of the top unfit-drop clusters 10,000 -> 30,000 (class, height above ground, error sign) and a top-view change map."""
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    st = site_tree(); a, b = mesh('10000', st), mesh('30000', st); dg = b['sc'].compute_distance(o3d.core.Tensor(a['cen'].astype('f4'))).numpy(); dn = a['sc'].compute_distance(o3d.core.Tensor(b['cen'].astype('f4'))).numpy()
    J = json.loads((OUTD/'change10k.json').read_text()); g = loadz(GT/'reference'/SITE/'dense.npz', ['xyz']); gz0 = float(np.percentile(g['xyz'][:, 2], 2)); out = []
    for s in J['unfit_drop_spots_10000_30000'][:6]:
        inb = lambda m: (m['cen'][:, 0] >= s['x0']) & (m['cen'][:, 0] <= s['x1']) & (m['cen'][:, 1] >= s['y0']) & (m['cen'][:, 1] <= s['y1'])
        sel = inb(a) & (dg > T) & (np.abs(a['err']) > T); w = a['area'][sel]
        out.append(dict(spot=[round(s['x'], 1), round(s['y'], 1)], gone_unfit_m2=round(float(w.sum()), 1), roof_wall_other_pct=[round(float(100*w[a['cls'][sel] == k].sum()/max(w.sum(), 1e-9)), 1) for k in range(3)],
                        above_gt_pct=round(float(100*w[a['err'][sel] > 0].sum()/max(w.sum(), 1e-9)), 1), height_above_ground_m_p50=round(float(np.median(a['cen'][sel, 2])-gz0), 1),
                        wrong_site_pct=round(float(100*w[a['site'][sel] == 1].sum()/max(w.sum(), 1e-9)), 1), error_m_p50=round(float(np.median(np.abs(a['err'][sel]))), 2)))
        print('SPOT', out[-1], flush=True)
    fig, ax = plt.subplots(figsize=(9, 9), dpi=110); ga = (dg > T) & (np.abs(a['err']) > T); nb = (dn > T)
    k = np.random.default_rng(0).random(len(a['cen'])) < .15; ax.scatter(a['cen'][k, 0], a['cen'][k, 1], s=.2, c='#D3D1C7', lw=0)
    ax.scatter(a['cen'][ga & k, 0], a['cen'][ga & k, 1], s=.6, c='#3C3489', lw=0, label='10k에 있던 틀린 면이 30k에 사라짐')
    kb = np.random.default_rng(1).random(len(b['cen'])) < .15; ax.scatter(b['cen'][nb & kb & (np.abs(b['err']) > T), 0], b['cen'][nb & kb & (np.abs(b['err']) > T), 1], s=.6, c='#D85A30', lw=0, label='30k에 새로 생긴 틀린 면')
    ax.scatter(b['cen'][nb & kb & (np.abs(b['err']) <= T), 0], b['cen'][nb & kb & (np.abs(b['err']) <= T), 1], s=.6, c='#1D9E75', lw=0, label='30k에 새로 생긴 맞는 면')
    t = loadz(FT/'targets'/f'{STEM}.npz', ['target']); pg = loadz(PF/'work/patch_groups.npz', ['group'])['group']; w1 = t['target'][pg == 1]; ax.scatter(w1[:, 0], w1[:, 1], s=.3, c='#C2378A', lw=0, alpha=.4, label='group 1 targets')
    for i, s in enumerate(J['unfit_drop_spots_10000_30000'][:6]): ax.add_patch(plt.Rectangle((s['x0'], s['y0']), s['x1']-s['x0'], s['y1']-s['y0'], fill=False, ec='k', lw=1)); ax.text(s['x0'], s['y1'], str(i+1), fontsize=10)
    ax.set_aspect('equal'); ax.legend(markerscale=12, fontsize=8, loc='lower left'); fig.savefig(OUTD/'change_map_10000_30000.png', bbox_inches='tight'); dump(OUTD/'spots_detail.json', dict(at=now(), ground_z_p2=gz0, spots=out, scientific_verdict=None))

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'spots': spots_detail()
