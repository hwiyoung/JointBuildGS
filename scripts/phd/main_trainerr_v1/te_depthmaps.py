"""Order 7.2 check-4 figure part 2 (GPU): render-depth maps of the two view groups for the check-4 representative point of every cell x arm.
Representative = the first point of figures/check4_<cell>_<arm>.json; views = its seen facing view and seen oblique view with the most
non-empty pixels near the point (ties lowest view index). Saves a 200x200 crop of render depth, alpha and the reference depth at the point."""
from te_render import *
@torch.no_grad()
def main():
    out = {}
    for cell in ['c1', 'c2', 'c3']:
        stem = STEMS[cell]; site = stem.split('__')[0]; vj = json.loads((GT/'views'/f'{site}.json').read_text()); views = [v for v in vj['views'] if not v['virtual']]; box = np.array(vj['box'])
        for arm in ARMS:
            rep = json.loads((D/'figures'/f'check4_{cell}_{arm}.json').read_text())['representatives'][0]; z = loadz(O/'checks'/f'{stem}__{arm}.npz', ['point_id', 'cell', 'set', 'xyz', 'normal', 'tau'])
            i = int(np.flatnonzero((z['point_id'] == rep['point_id']) & (z['cell'] == int(cell[1])) & (z['set'] == 0))[0]); pr = loadz(O/'checks'/f'{stem}__{arm}_pairs.npz')
            pp = np.flatnonzero(pr['point'] == i); res = {}
            g, full = load_model(arm_paths(stem, arm)['model']/'point_cloud/iteration_30000/point_cloud.ply', box); pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
            from renderer import install; install()
            for grp, fm_ in [('facing', 1), ('oblique', 0)]:
                q = pp[pr['facing'][pp] == fm_]
                if not len(q): res[grp] = None; continue
                j = int(pr['view'][q[np.argmin(pr['view'][q])]]); v = views[j]; K = np.asarray(v['K']); E = np.asarray(v['W2C'])
                pkg = render(camera(v['width'], v['height'], K, E, v['name']), g, pipe, bg); dep = pkg['surf_depth'].squeeze().cpu().numpy(); al = pkg['rend_alpha'].squeeze().cpu().numpy()
                X = z['xyz'][i]; c_ = X@E[:3, :3].T+E[:3, 3]; u = K[0, 0]*c_[0]/c_[2]+K[0, 2]; vv = K[1, 1]*c_[1]/c_[2]+K[1, 2]; r = 100
                x0, y0 = int(max(0, round(u)-r)), int(max(0, round(vv)-r)); x1, y1 = min(v['width'], x0+2*r), min(v['height'], y0+2*r)
                res[grp] = dict(view=v['name'], j=j, u=float(u), v=float(vv), crop=[x0, y0, x1, y1], point_camera_z=float(c_[2]))
                savez(O/'depthmaps'/f'{cell}_{arm}_{grp}.npz', depth=dep[y0:y1, x0:x1], alpha=al[y0:y1, x0:x1])
            out[f'{cell}_{arm}'] = dict(point_id=rep['point_id'], cls=rep['cls'], tau=float(z['tau'][i]), views=res); del g; torch.cuda.empty_cache()
    dump(O/'depthmaps/index.json', dict(at=now(), maps=out, scientific_verdict=None)); print('DEPTHMAPS', list(out))
if __name__ == '__main__': main()
