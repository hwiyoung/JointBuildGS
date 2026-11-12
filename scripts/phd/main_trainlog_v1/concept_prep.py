"""Concept figure (user request 2026-11-12, '그려줘'): what Gaussian splatting is, how it learns over iterations, and why this method gives a good mesh.
GPU inference only, one real training camera (train1 = DJI_20241217091247_0146_D, the camera_choice.json rank-1 photo), no GT, no training.
  part A (this run, r27 trainlog states 0, 300, 1000, 2000, 3000, 10000, 30000; argv may name a subset): for the Gaussians that are the per-pixel max alpha*T contributor in at least one pixel
         (renders/<state>/data.npz train1_maxid_full), save centre, activated scale, unit quaternion, opacity, DC colour (SH degree 0) and pixel count.
  part B (the same camera, final 30,000 iterations): render the two comparison runs of the same unit B173nb_b10 from main_baselines_v1
         (image-only 2DGS imgonly_2dgs_s0, prior-first GeoGS ALS geogs_ALS_fix1) with the r27 renderer: RGB, surface depth, alpha, PSNR to the photo.
         The comparison runs' own model/cameras.json hold the same camera (checked 2026-11-12: same centre, rotation and focal length).
  inputs: the photo and the TARGET depth map of that camera (stage1 maps: depth, weight, owner) are copied for the figure.
scientific_verdict: null"""
import sys, time
from render_states import *
STATES = sys.argv[1].split(',') if len(sys.argv) > 1 else ['0', '300', '1000', '2000', '3000', '10000', '30000']; OUTC = O/'concept'; C0 = 0.28209479177387814
SB = PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1/runs'/SITE
COMPARE = {'imgonly_2dgs': SB/'imgonly_2dgs_s0/model/point_cloud/iteration_30000/point_cloud.ply', 'geogs_als': SB/'geogs_ALS_fix1/model/point_cloud/iteration_30000/point_cloud.ply'}
TMAP = FT/'stage1'/STEM/'maps'

@torch.no_grad()
def main():
    torch.cuda.set_per_process_memory_fraction(.6); OUTC.mkdir(parents=True, exist_ok=True); run = RUNM/'trainlog'; rec = dict(at=now(), rule=__doc__, states={}, compare={}, scientific_verdict=None)
    tr = json.loads((O/'renders/cameras.json').read_text())['training'][0]; name = tr['name']; W, H, K, W2C = tr['width'], tr['height'], np.asarray(tr['K']), np.asarray(tr['W2C'])
    photo = np.asarray(Image.open(f'/p/fork_inputs/s61/{SITE}/scene_{PRIOR}/images/{name}.jpg').convert('RGB'), np.float32)/255.
    idx = json.loads((TMAP/'index.json').read_text())['views'][name]; tm = loadz(TMAP/idx['file'], ['depth', 'weight', 'owner'])
    savez(OUTC/'inputs.npz', photo=(photo*255).astype('u1'), target_depth=tm['depth'].astype('f4'), target_weight=tm['weight'].astype('f4'), target_owner=tm['owner'], K=K, W2C=W2C, W=W, H=H, name=name)
    rec['camera'] = dict(name=name, W=W, H=H, K=K.tolist(), W2C=W2C.tolist(), target_map=str(TMAP/idx['file']), owner_values={str(int(v)): int((tm['owner'] == v).sum()) for v in np.unique(tm['owner'])})
    for n in STATES:
        t0 = time.monotonic(); z = loadz(O/'renders'/n/'data.npz', ['train1_maxid_full']); ids, cnt = np.unique(z['train1_maxid_full'][z['train1_maxid_full'] >= 0], return_counts=True)
        d = torch.load(run/'scene'/f'{n}.pt', map_location='cpu', weights_only=False); q = d['rotation'][ids].numpy().astype(float); q /= np.linalg.norm(q, axis=1, keepdims=True)
        rgb = np.clip(.5+C0*d['f_dc'][ids].numpy().reshape(len(ids), -1)[:, :3], 0, 1)
        savez(OUTC/f'discs_{n}.npz', ids=ids, pixels=cnt, xyz=d['xyz'][ids].numpy(), scale=np.exp(d['scaling'][ids].numpy()), quat=q, opacity=1/(1+np.exp(-d['opacity'][ids].numpy().reshape(-1))), rgb=rgb.astype('f4'),
              n_all=len(d['xyz']))
        sc = np.exp(d['scaling'].numpy()).max(1); rec['states'][n] = dict(gaussians=int(len(d['xyz'])), visible=int(len(ids)), max_scale_m_p50_p90=[float(np.percentile(sc, 50)), float(np.percentile(sc, 90))], seconds=round(time.monotonic()-t0, 1))
        print('STATE', n, rec['states'][n], flush=True); del d
    from renderer import install
    install(); pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda'); cam = camera(W, H, K, W2C, name)
    for key, ply in COMPARE.items():
        if (OUTC/f'compare_{key}.npz').exists(): print('SKIP', key, flush=True); continue
        t0 = time.monotonic(); g = GaussianModel(3); g.load_ply(str(ply)); g.active_sh_degree = 3; pkg = render(cam, g, pipe, bg)
        rgb = pkg['render'].permute(1, 2, 0).clamp(0, 1).cpu().numpy(); depth = pkg['surf_depth'].squeeze().cpu().numpy(); alpha = pkg['rend_alpha'].squeeze().cpu().numpy()
        psnr = float(10*np.log10(1/float(((rgb-photo)**2).mean()))); savez(OUTC/f'compare_{key}.npz', rgb=(rgb*255).astype('u1'), depth=depth.astype('f4'), alpha=alpha.astype('f2'))
        rec['compare'][key] = dict(ply=str(ply), gaussians=int(len(g._xyz)), psnr=psnr, seconds=round(time.monotonic()-t0, 1)); print('COMPARE', key, rec['compare'][key], flush=True); del g, pkg; torch.cuda.empty_cache()
    rec['ours_30000_psnr'] = json.loads((O/'renders/30000/render.json').read_text())['train1_psnr']
    old = O/'concept/concept_prep.json'
    if old.exists():
        prev = json.loads(old.read_text()); prev['states'].update(rec['states']); prev['compare'].update(rec['compare']); rec = dict(prev, at_update=rec['at'])
    dump(OUTC/'concept_prep.json', rec); print('DONE', flush=True)

if __name__ == '__main__': main()
