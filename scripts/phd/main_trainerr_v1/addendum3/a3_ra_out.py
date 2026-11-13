"""Work ra outputs (diagnostic only): per stem x variant scene values, place values, right-surface loss, base-vs-stored check, sections. CPU.
  values   : tables/ra_scene.csv, ra_places.csv, ra_base_check.csv
  figures  : figures/ra_section_<place>.png (base + four variants, one panel each)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
from a3_ga import load_mesh, mesh_section
STEMS = ['B0_b10__ALS', 'B173nb_b10__ALS', 'B0_b10__LoD2']; VARIANTS = ['base', 'opacity_0.5', 'opacity_0.8', 'discontinuity_0.5', 'median_depth']
VKO = {'base': '기준', 'opacity_0.5': '불투명도 0.5', 'opacity_0.8': '불투명도 0.8', 'discontinuity_0.5': '깊이 불연속 0.5 m', 'median_depth': '중앙 깊이'}
RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
STORED = {'B0_b10__ALS': RS/'addendum3_stage2/meshes/B0_b10__ALS__FINALTRAIN_30000/primary.ply', 'B173nb_b10__ALS': RS/'addendum3_stage1/meshes/B173nb_b10__ALS__FINALTRAIN_30000/primary.ply',
          'B0_b10__LoD2': RS/'addendum3_stage2/meshes/B0_b10__LoD2__FINALTRAIN_30000/primary.ply'}
def key(stem, v): return f'{stem}__ra_{v}'
def scope(stem):
    import shapely
    from shapely.geometry import shape
    c = json.loads(((R/'configs/phd/main_trainlog_v1/trainlog_v1.json') if stem.startswith('B173') else TL_CASE_CFG).read_text())['scope']
    return shape(c['footprint']), float(c['ground_z'])
def face_values(stem, path):
    import shapely
    fp, g0 = scope(stem); V, F = load_mesh(path); ctr = V[F].mean(1); a = V[F[:, 1]]-V[F[:, 0]]; b = V[F[:, 2]]-V[F[:, 0]]; A = .5*np.linalg.norm(np.cross(a, b), axis=1); h = ctr[:, 2]-g0
    de = shapely.distance(fp, shapely.points(ctr[:, 0], ctr[:, 1])); site = stem.split('__')[0]; G = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype('f8'); T = cKDTree(G)
    near = de <= 3; dg = np.full(len(F), np.nan); dg[near] = T.query(ctr[near], workers=8)[0]
    edge = (de > 0) & (de <= 3) & (h >= 12) & (dg > 1.); bld = (de <= 1) & (dg > 1.)
    return dict(edge_floater_area_m2=float(A[edge].sum()), building_off_gt_1m_area_m2=float(A[bld].sum()), faces=len(F), area_m2=float(A.sum()))

def values():
    scene = []; places = []; chk = []; ann = ccfg()['places']['annex_box']
    for stem in STEMS:
        base = A3O/'meshes'/key(stem, 'base')/'points.npz'
        if not base.exists(): continue
        bw = loadz(base, ['reference__within_tau1'])['reference__within_tau1'].astype(bool)
        for v in VARIANTS:
            m = A3O/'meshes'/key(stem, v); f = m/'score.json'
            if not f.exists(): continue
            for x in json.loads(f.read_text())['rows']:
                if x['surface'] in ('all', 'wall', 'roof') and str(x['case_id']) in ('all', '0', '1', '2', '3', '4'):
                    scene.append(dict(stem=stem, variant=v, surface=x['surface'], case_id=str(x['case_id']), n_gt=x['n_gt'], completeness_pct=x['completeness_pct'], accuracy_pct=x.get('accuracy_pct'), result_n=x.get('result_n')))
            z = loadz(m/'points.npz', ['reference__within_tau1', 'result__xyz', 'result__s_m', 'result__eligible_new', 'result__within_tau1']); rw = z['reference__within_tau1'].astype(bool)
            r = dict(stem=stem, variant=v, right_surface_loss_pct=100*float((bw & ~rw).sum())/max(1, int(bw.sum())), right_surface_gain_pct=100*float((~bw & rw).sum())/max(1, int(bw.sum())))
            X = z['result__xyz'].astype('f8'); s = z['result__s_m']
            if stem == 'B0_b10__ALS':
                k = (X[:, 0] >= ann['x'][0]) & (X[:, 0] <= ann['x'][1]) & (X[:, 1] >= ann['y'][0]) & (X[:, 1] <= ann['y'][1]) & (X[:, 2] >= ann['z'][0]) & (X[:, 2] <= ann['z'][1])
                r.update(annex_result_points=int(k.sum()), annex_farther_1m=int((k & np.isfinite(s) & (np.abs(s) > 1)).sum()), annex_no_distance=int((k & ~np.isfinite(s)).sum()))
            if stem == 'B0_b10__LoD2':
                a_, d_, zone = wall_coords(X, 'south'); e = z['result__eligible_new'].astype(bool); w = z['result__within_tau1'].astype(bool)
                r.update(south_zone_result_points=int(zone.sum()), south_behind_064_pct=pct(d_[zone] < -.64) if zone.any() else None,
                         south_wall_accuracy_pct=100*float((zone & e & w).sum())/max(1, int((zone & e).sum())))
            r.update(face_values(stem, A3O/'gtj/meshes'/key(stem, v)/'final.ply')); places.append(r); print('RA', r, flush=True)
        st = STORED[stem]; bp = A3O/'gtj/meshes'/key(stem, 'base')/'final.ply'
        V1, F1 = load_mesh(bp); V2, F2 = load_mesh(st)
        chk.append(dict(stem=stem, rebuilt=str(bp), rebuilt_sha256=sha(bp), stored=str(st), stored_sha256=sha(st), same_bytes=sha(bp) == sha(st), rebuilt_vertices=len(V1), stored_vertices=len(V2),
                        rebuilt_faces=len(F1), stored_faces=len(F2), same_vertex_array=bool(len(V1) == len(V2) and np.array_equal(V1, V2)), same_face_array=bool(len(F1) == len(F2) and np.array_equal(F1, F2)),
                        vertex_max_abs_diff_m=float(np.abs(V1-V2).max()) if len(V1) == len(V2) else None))
        a = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); sw = a['reference__FINALTRAIN_30000__within_tau1'].astype(bool); a.close()
        chk[-1]['gt_within_tau_rebuilt_vs_stored_same_pct'] = 100*float((sw == bw).mean()) if len(sw) == len(bw) else None
        chk[-1]['completeness_rebuilt_pct'] = 100*float(bw.mean()); chk[-1]['completeness_stored_pct'] = 100*float(sw.mean())
    ctable('ra_scene', scene); ctable('ra_places', places); ctable('ra_base_check', chk); print('RA_VALUES', len(scene), len(places), chk, flush=True)

def frames():
    """section frames: annex y = 1.7 (addendum2); south wall across the wall at along 7.6 m (addendum2); floater: across the nearest footprint edge at the floater_check concentration centroid."""
    out = {}
    out['annex'] = ('B0_b10__ALS', dict(origin=np.array([92., 1.7, -38.]), h=np.array([1., 0, 0]), e=np.array([0, 1., 0]), win=[-8, 8, -47, -29]))
    sw = acfg()['places']['south_wall']; p0 = np.array(sw['p0']); eu = np.array(sw['e']); n = np.array(sw['n_out'])
    out['south_wall'] = ('B0_b10__LoD2', dict(origin=np.r_[p0+7.6*eu, -34.], h=np.r_[n, 0.], e=np.r_[eu, 0.], win=[-6, 4, -45, -22]))
    import shapely
    fp, g0 = scope('B173nb_b10__ALS'); c = np.array(json.loads((R/'docs/experiments/phd/main_trainlog_v1/figures_concept_v2/floater_check/floater_check.json').read_text())['concentration']['centroid_xyz'])
    ring = np.asarray(fp.exterior.coords); seg = np.c_[ring[:-1], ring[1:]]; P = c[:2]
    def dist(sg):
        a, b = sg[:2], sg[2:]; t = np.clip(np.dot(P-a, b-a)/np.dot(b-a, b-a), 0, 1); return np.linalg.norm(P-(a+t*(b-a)))
    sg = min(seg, key=dist); t = (sg[2:]-sg[:2])/np.linalg.norm(sg[2:]-sg[:2]); hh = np.array([t[1], -t[0]])
    if fp.contains(shapely.points(*(P+hh*.5))): hh = -hh
    q = np.array([sg[0], sg[1]])+np.dot(P-sg[:2], t)*t
    out['floater'] = ('B173nb_b10__ALS', dict(origin=np.r_[q, g0+20], h=np.r_[hh, 0.], e=np.r_[t, 0.], win=[-6, 6, g0+5, g0+28]))
    return out

def figures():
    plt = korean_plt()
    for place, (stem, Fr) in frames().items():
        site = stem.split('__')[0]; G = loadz(GT/'reference'/site/'dense.npz', ['xyz'])['xyz'].astype('f8'); w = Fr['win']
        d = (G-Fr['origin'])@Fr['e']; hh = (G-Fr['origin'])@Fr['h']; k = (np.abs(d) <= .25) & (hh >= w[0]) & (hh <= w[1]) & (G[:, 2] >= w[2]) & (G[:, 2] <= w[3]); gt = np.c_[hh[k], G[k, 2]]
        fig, axs = plt.subplots(1, 5, figsize=(22, 6), dpi=100, sharey=True); srcs = {}
        for ax, v in zip(axs, VARIANTS):
            p = A3O/'gtj/meshes'/key(stem, v)/'final.ply'
            ax.scatter(gt[:, 0], gt[:, 1], s=.4, c='#BDBDBD', lw=0, rasterized=True)
            if p.exists():
                for sgm in mesh_section(load_mesh(p), Fr, w): ax.plot(sgm[:, 0], sgm[:, 1], color='#D62728', lw=.9)
                srcs[v] = str(p)
            ax.set_title(VKO[v], fontsize=10); ax.set_xlim(w[0], w[1]); ax.set_ylim(w[2], w[3]); ax.set_aspect('equal')
        hs = [plt.Line2D([], [], color='#BDBDBD', marker='o', ls='', label='참값'), plt.Line2D([], [], color='#D62728', label='메시')]
        fig.legend(handles=hs, loc='lower center', ncol=2, fontsize=9); fig.tight_layout(rect=(0, .06, 1, 1)); p = A3D/'figures'/f'ra_section_{place}.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
        dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, place=place, stem=stem, section={k: (v.tolist() if hasattr(v, 'tolist') else v) for k, v in Fr.items()}, thickness_m=.5, meshes=srcs, scientific_verdict=None))
    print('RA_FIGURES', flush=True)

if __name__ == '__main__':
    {'values': values, 'figures': figures}[sys.argv[1]]()
