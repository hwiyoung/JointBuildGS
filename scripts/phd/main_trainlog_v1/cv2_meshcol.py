"""Concept video v2 (first cut, 2026-11-12): colour for the meshes of every frame. CPU, no training; the mesh geometry is the original rule's mesh, unchanged.
The original TSDF integrates zero colour, so the colour is fused afterwards from the SAME render images the mesh was made from
(the 203 training views of the mesh pipeline, SH degree 0, building box; the npz 'rgb' next to 'depth'):
  every vertex is projected into every view (pixel i centre at u = i, the renderer's convention); a view counts for the vertex when the rendered
  depth at that pixel is > 0 and differs from the vertex camera-z by at most TRUNC = 0.25 m (the TSDF truncation); colour = mean rendered RGB over those views.
  Vertices with no such view stay grey (#BDBDBD, counted in meshcol.json).
Meshes (building scope: ours = analysis/mesh_<n>.npz as made by frames.prep_mesh; comparisons = faces whose centroid is inside derive_states.scope_mask, as concept_mesh.py):
  ours_<n>       analysis/mesh_<n>.npz,                               renders gtj/renders/B173nb_b10__ALS__tl_<n>
  nojudge_15000  concept_v2/gtj/meshes/..cmp_nojudge_15000/final.ply, renders concept_v2/gtj/renders/..cmp_nojudge_15000
  nojudge_30000  concept_v2/gtj/meshes/..cmp_nojudge_30000_v203,     renders concept_v2/gtj/renders/..cmp_nojudge_30000_v203 (203-view rule; RESCORE's used 219 views)
  2dgs_7000      concept_v2/gtj/meshes/..cmp_2dgs_7000/final.ply,     renders concept_v2/gtj/renders/..cmp_2dgs_7000
  2dgs_30000     concept_v2/gtj/meshes/..cmp_2dgs_30000_v203,         renders concept_v2/gtj/renders/..cmp_2dgs_30000_v203
  *_rescore219   RESCORE meshes/renders of the two 30,000 runs (record only)
Only views whose name is in the 203-view list (gtj/views/B173nb_b10.json) are used. Writes concept_v2/meshcol/<key>.npz and meshcol.json.
scientific_verdict: null"""
import sys, time
from common import *
from derive_states import scope_mask
import open3d as o3d
V2 = O/'concept_v2'; OUTM = V2/'meshcol'; TRUNC = .25; GREY = 189
RSM = RS
STATES = ['0', '100', '300', '1000', '2000', '3000', '5000', '7000', '10000', '15000', '30000']
SRC = {**{f'ours_{n}': (O/'analysis'/f'mesh_{n}.npz', O/'gtj/renders'/f'{STEM}__tl_{n}') for n in STATES},
       'nojudge_15000': (V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_15000/final.ply', V2/'gtj/renders'/f'{STEM}__cmp_nojudge_15000'),
       'nojudge_30000': (V2/'gtj/meshes'/f'{STEM}__cmp_nojudge_30000_v203/final.ply', V2/'gtj/renders'/f'{STEM}__cmp_nojudge_30000_v203'),
       '2dgs_7000': (V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_7000/final.ply', V2/'gtj/renders'/f'{STEM}__cmp_2dgs_7000'),
       '2dgs_30000': (V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_30000_v203/final.ply', V2/'gtj/renders'/f'{STEM}__cmp_2dgs_30000_v203'),
       # record only: RESCORE's 30,000 meshes (219 views = 203 real + 16 virtual) coloured from the 203 real views; 39 % / 24 % of their vertices get no view
       'nojudge_30000_rescore219': (RSM/'meshes/B173nb_b10__ALS__baseline_30000/final.ply', RSM/'renders/B173nb_b10__ALS__baseline_30000'),
       '2dgs_30000_rescore219': (RSM/'meshes/B173nb_b10__LoD2__2DGS_30000/final.ply', RSM/'renders/B173nb_b10__LoD2__2DGS_30000')}

if TL_CASE:   # another case (launch.py TL_CASE): ours from the uncut original-rule mesh (scope cut here, as frames.prep_mesh), 2DGS only, no virtual views
    SRC = {**{f'ours_{n}': (O/'gtj/meshes'/f'{STEM}__tl_{n}'/'final.ply', O/'gtj/renders'/f'{STEM}__tl_{n}') for n in STATES},
           '2dgs_7000': SRC['2dgs_7000'], '2dgs_30000': (V2/'gtj/meshes'/f'{STEM}__cmp_2dgs_30000/final.ply', V2/'gtj/renders'/f'{STEM}__cmp_2dgs_30000')}

def mesh(key, c):
    p, _ = SRC[key]
    if p.suffix == '.npz': z = loadz(p, ['vertices', 'faces']); return z['vertices'].astype(float), z['faces'].astype('i8')
    m = o3d.io.read_triangle_mesh(str(p)); V = np.asarray(m.vertices, float); F = np.asarray(m.triangles).astype('i8'); del m
    keep = scope_mask(V[F].mean(1), c); F = F[keep]; used = np.unique(F); remap = np.full(len(V), -1); remap[used] = np.arange(len(used)); return V[used], remap[F]

def colour(V, root, names):
    rec = json.loads((root/'receipt.json').read_text()); views = [v for v in rec['views'] if v['name'] in names and not v.get('virtual', False)]
    acc = np.zeros((len(V), 3)); cnt = np.zeros(len(V), 'i4')
    for v in views:
        z = loadz(root/v['file']); dep, rgb = z['depth'], z['rgb']; H, W = dep.shape; K = np.asarray(v['K']); E = np.asarray(v['W2C'])
        Xc = V@E[:3, :3].T+E[:3, 3]; zc = Xc[:, 2]; ok = zc > .01; zs = np.where(ok, zc, 1.)
        u = np.rint(K[0, 0]*Xc[:, 0]/zs+K[0, 2]); w = np.rint(K[1, 1]*Xc[:, 1]/zs+K[1, 2]); ok &= (u >= 0) & (u < W) & (w >= 0) & (w < H)
        i = np.flatnonzero(ok); ui, wi = u[i].astype(int), w[i].astype(int); d = dep[wi, ui]; g = (d > 0) & (np.abs(zc[i]-d) <= TRUNC)
        acc[i[g]] += rgb[wi[g], ui[g]]; cnt[i[g]] += 1
    C = np.where(cnt[:, None] > 0, acc/np.maximum(cnt, 1)[:, None], GREY); return np.clip(np.rint(C), 0, 255).astype('u1'), cnt, len(views), rec

def main(keys):
    c = cfg(); OUTM.mkdir(parents=True, exist_ok=True); names = {v['name'] for v in json.loads((O/'gtj/views'/f'{SITE}.json').read_text())['views']}
    old = V2/'meshcol.json'; out = json.loads(old.read_text()) if old.exists() else dict(rule=__doc__, meshes={}, scientific_verdict=None)
    for key in keys:
        if (OUTM/f'{key}.npz').exists(): print('SKIP', key, flush=True); continue
        t0 = time.monotonic(); V, F = mesh(key, c); C, cnt, nv, rec = colour(V, SRC[key][1], names)
        savez(OUTM/f'{key}.npz', V=V.astype('f4'), F=F.astype('i4'), C=C, nview=np.minimum(cnt, 65535).astype('u2'))
        out['meshes'][key] = dict(mesh=str(SRC[key][0]), renders=str(SRC[key][1]), render_receipt_sha256=sha(SRC[key][1]/'receipt.json'), views_used=nv, vertices=int(len(V)), faces=int(len(F)),
                                  vertices_without_view=int((cnt == 0).sum()), views_per_vertex_median=float(np.median(cnt)), seconds=round(time.monotonic()-t0, 1))
        out['at'] = now(); dump(old, out); print('MESHCOL', key, out['meshes'][key], flush=True)

if __name__ == '__main__': main(sys.argv[1].split(',') if len(sys.argv) > 1 else [k for k in SRC if k.startswith('ours_')])
