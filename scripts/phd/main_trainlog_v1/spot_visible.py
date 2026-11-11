"""Spot strips, Gaussian row (user decision 2026-11-11 '보이는 원반만'): for each key state and each thesis place, render the full scene with the r27
renderer from the place's close-up camera (far perspective at 500 m, the basis and extent of analysis/spot_strips_cams.json written by spot_strips.py cams)
through the TARGET r5 maxid .so. A Gaussian is 'visible' when it is the per-pixel max alpha*T contributor in at least one pixel. Saves, per state and place,
the visible full indices (only Gaussians whose centre projects inside the close-up box +2 m and lies within DEPTH_BAND of the place centre are rendered; for the wall also within WALL_BAND of the face plane), their pixel counts and activated parameters (xyz, scale, unit quaternion, opacity, uid) and the id image. Inference only."""
import sys, math, time, importlib.util
from render_states import *
WALL_BAND = 3.0   # m from the unseen wall face plane, same as spot_strips' wall window
DEPTH_BAND = 40.   # m along the view direction around the place centre: far background Gaussians would otherwise cover the far-perspective close-up
STATES = ['0', '1000', '2000', '3000_pre_reset', '7000', '10000', '15000', '30000']; OUTV = O/'spot_strips/visible'

def place_camera(cm, W=900):
    B = np.asarray(cm['B'], float); lo, hi = np.asarray(cm['lo'], float), np.asarray(cm['hi'], float); ctr = np.asarray(cm['ctr'], float)
    H = int(round(W*(hi[1]-lo[1])/(hi[0]-lo[0]))); cen = ctr+(lo[0]+hi[0])/2*B[0]+(lo[1]+hi[1])/2*B[1]; D_ = 500.; width = hi[0]-lo[0]
    fx = (W/2)/(width/2/D_); K = np.array([[fx, 0, W/2], [0, fx, H/2], [0, 0, 1]]); C = cen-B[2]*D_; Rw = np.stack([B[0], -B[1], B[2]]); W2C = np.eye(4); W2C[:3, :3] = Rw; W2C[:3, 3] = -Rw@C
    return W, H, K, W2C

@torch.no_grad()
def main():
    torch.cuda.set_per_process_memory_fraction(.6); OUTV.mkdir(parents=True, exist_ok=True); cams = json.loads((O/'analysis/spot_strips_cams.json').read_text())['cams']; run = RUNM/'trainlog'
    from renderer import install
    install(); rfix = raster._C; spec = importlib.util.spec_from_file_location('jbgs_target_r5_maxid', MAXID); maxid = importlib.util.module_from_spec(spec); spec.loader.exec_module(maxid)
    pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda'); rec = []
    for name in STATES:
        t0 = time.monotonic(); g, d = load(run/'scene'/f'{name}.pt')
        for place, cm in cams.items():
            W, H, K, W2C = place_camera(cm); cam = camera(W, H, K, W2C, place); Bm = np.asarray(cm['B'], float); lo, hi = np.asarray(cm['lo'], float), np.asarray(cm['hi'], float)
            qq = (d['xyz'].numpy().astype(float)-np.asarray(cm['ctr'], float))@Bm.T; near = (qq[:, 0] >= lo[0]-2) & (qq[:, 0] <= hi[0]+2) & (qq[:, 1] >= lo[1]-2) & (qq[:, 1] <= hi[1]+2) & (np.abs(qq[:, 2]) <= DEPTH_BAND)
            if place == 'wall':   # only what stands at the wall: within WALL_BAND of the unseen face plane (things in front of it are what hid it from the images)
                f = json.loads((O/'analysis/spots_v5/spots_v5.json').read_text())['places']['wall']['face']; near &= np.abs((d['xyz'].numpy().astype(float)-np.asarray(f['centre']))@np.asarray(f['normal'], float)) <= WALL_BAND
            sub = np.flatnonzero(near); kt = torch.from_numpy(sub).cuda(); gs = GaussianModel(3)
            for a_ in ['_xyz', '_features_dc', '_features_rest', '_opacity', '_scaling', '_rotation']: setattr(gs, a_, torch.nn.Parameter(getattr(g, a_)[kt].contiguous(), requires_grad=False))
            gs.active_sh_degree = g.active_sh_degree; raster._C = maxid; pk = render(cam, gs, pipe, bg); raster._C = rfix
            li = np.rint(pk['rend_dist'].squeeze().cpu().numpy()).astype('i8')-1; idx = np.where(li >= 0, sub[li.clip(0)], -1); ids, cnt = np.unique(idx[idx >= 0], return_counts=True); del gs
            q = d['rotation'][ids].numpy().astype(float); q /= np.linalg.norm(q, axis=1, keepdims=True)
            savez(OUTV/f'{name}__{place}.npz', ids=ids, pixels=cnt, xyz=d['xyz'][ids].numpy(), scale=np.exp(d['scaling'][ids].numpy()), quat=q, opacity=1/(1+np.exp(-d['opacity'][ids].numpy().reshape(-1))),
                  uid=d['uid'][ids].numpy(), id_image=idx.astype('i4'), W=W, H=H)
            rec.append(dict(state=name, place=place, near=int(len(sub)), visible=int(len(ids)), pixels=int((idx >= 0).sum()), top_pixel_share=float(cnt.max()/max(cnt.sum(), 1)) if len(cnt) else None, image=[W, H])); print('VIS', rec[-1], flush=True)
        del g, d; torch.cuda.empty_cache(); print('STATE', name, round(time.monotonic()-t0, 1), flush=True)
    dump(OUTV/'visible.json', dict(at=now(), rule=__doc__, records=rec, scientific_verdict=None))

if __name__ == '__main__': main()
