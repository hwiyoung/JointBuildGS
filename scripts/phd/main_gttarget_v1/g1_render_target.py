"""Order 5 check 1: GT target patches -> 'target mesh' by the same rule as the method's target mesh (RESCORE render_patches: patch quads
+-0.125 m along the two in-plane axes, CPU ray casting on the frozen views, then the unchanged TSDF recipe of mesh_job).
Runs in the gtj container (/gtjudge = this task's shadow). argv: <stem> <family>"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1'); sys.path.insert(0, '/repo')
from inherited import *
from src.phd.metrics_v3.surface import MeshScene
GTT = Path('/te')

def main(stem, family):
    start = time.monotonic(); cfg(); site, prior = stem.split('__'); key = f'{stem}__{family}'; view = ensure_views(site)
    t = loadz(GTT/'targets'/f'{stem}.npz'); p = loadz(GTT/'surface'/site/'patches.npz', ['t1', 't2'])
    keep = t['surface_exists'] & np.isfinite(t['target']).all(1); c = t['target'][keep]; a = p['t1'][keep]*.125; b = p['t2'][keep]*.125
    V = np.stack([c-a-b, c+a-b, c+a+b, c-a+b], 1).reshape(-1, 3); F = (np.arange(len(c))[:, None, None]*4+np.array([[0, 1, 2], [0, 2, 3]])).reshape(-1, 3)
    scene = MeshScene(V, F); root = O/'renders'/key; root.mkdir(parents=True, exist_ok=True)
    savez(root/'patch_geometry.npz', vertices=V, triangles=F)
    views = json.loads((O/'views'/f'{site}.json').read_text())['views']; box = np.array(view['box']); records = []
    for i, v in enumerate(views):
        K = np.array(v['K']); W, H = v['width'], v['height']; inv = np.linalg.inv(v['W2C']); depth = np.zeros((H, W), 'f4')
        for y in range(0, H, 128):
            yy, xx = np.meshgrid(np.arange(y, min(y+128, H)), np.arange(W), indexing='ij')
            Dd = np.stack([(xx-K[0, 2])/K[0, 0], (yy-K[1, 2])/K[1, 1], np.ones_like(xx)], -1).reshape(-1, 3)@inv[:3, :3].T
            origin = np.broadcast_to(inv[:3, 3], Dd.shape); tt = scene.cast(origin, Dd); P = origin+tt[:, None]*Dd
            good = np.isfinite(tt) & (tt > 0) & ((P >= box[0]) & (P <= box[1])).all(1); depth[y:y+yy.shape[0]] = np.where(good, tt, 0).reshape(yy.shape)
        f = root/f'{i:04d}.npz'; savez(f, depth=depth, rgb=np.zeros((H, W, 3), 'u1')); records.append(dict(v, file=f.name, sha256=sha(f)))
        if i % 40 == 0: print('GT_PATCH_RENDER', key, i+1, len(views), flush=True)
    dump(root/'receipt.json', dict(status='PASS', views=records, box=box.tolist(), family=family, patches=int(keep.sum()), source_sha256=sha(__file__),
        target_sha256=sha(GTT/'targets'/f'{stem}.npz'), seconds=time.monotonic()-start, GT_read='참값 목표 판(진단용): 목표 = 참값 조각', optimization_steps=0, scientific_verdict=None))
    dump(O/'jobs'/f'{key}.json', dict(site=site, prior=prior, family=family, key=key, box=box.tolist(), scientific_verdict=None))
    print('GT_PATCH_RENDER_DONE', key, round(time.monotonic()-start), flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
