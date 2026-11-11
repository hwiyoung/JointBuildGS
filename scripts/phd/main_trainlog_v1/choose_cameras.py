"""Pick the two training images (order 3): largest fraction of case-1 GT rows inside the building scope
visible unoccluded against the original 30,000 mesh. GT used only for display-camera choice (config GT_use). CPU."""
from common import *
import open3d as o3d
from derive_states import scope_mask

def main():
    c = cfg(); rc = c['renders']['training_images']
    rows = loadz(GT/'scenes'/STEM/'rows.npz', ['xyz']); cell = loadz(GT/'scenes'/STEM/'stage1_cells.npz', ['case_id'])
    pick = (cell['case_id'] == 1) & scope_mask(rows['xyz'], c); X = rows['xyz'][pick].astype(np.float64)
    mesh = o3d.io.read_triangle_mesh(str(RS/'addendum3_stage1/meshes/B173nb_b10__ALS__FINALTRAIN_30000/primary.ply'))
    scene = o3d.t.geometry.RaycastingScene(); scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh)); del mesh
    views = [v for v in json.loads((RS/'views'/f'{SITE}.json').read_text())['views'] if not v['virtual']]; out = []
    for v in views:
        E = np.asarray(v['W2C'], np.float64); K = np.asarray(v['K'], np.float64); q = X @ E[:3, :3].T + E[:3, 3]
        front = q[:, 2] > 0; u = K[0, 0]*q[:, 0]/np.where(front, q[:, 2], 1)+K[0, 2]; w = K[1, 1]*q[:, 1]/np.where(front, q[:, 2], 1)+K[1, 2]
        inimg = front & (u >= 0) & (w >= 0) & (u < v['width']) & (w < v['height']); ids = np.flatnonzero(inimg)
        centre = -E[:3, :3].T @ E[:3, 3]; d = X[ids]-centre; dist = np.linalg.norm(d, axis=1); ray = np.c_[np.repeat(centre[None], len(ids), 0), d/dist[:, None]].astype('f4')
        t = scene.cast_rays(o3d.core.Tensor(ray))['t_hit'].numpy() if len(ids) else np.empty(0)
        vis = ~np.isfinite(t) | (t >= dist-float(0.15))
        out.append(dict(name=v['name'], index=int(v['index']), in_image=int(len(ids)), visible=int(vis.sum()), fraction=float(vis.sum()/len(X))))
    out.sort(key=lambda r: (-r['fraction'], r['name'])); table('camera_choice', out, folder=D/'tables')
    dump(D/'camera_choice.json', dict(at=now(), rule=rc['rule'], population=int(len(X)), chosen=out[:2], top10=out[:10], mesh_sha256=sha(RS/'addendum3_stage1/meshes/B173nb_b10__ALS__FINALTRAIN_30000/primary.ply'), scientific_verdict=None))
    print('CHOSEN', out[:2], flush=True)
if __name__ == '__main__': main()
