"""Like-for-like visibility of the final models (PHD-STAGE2-R6-FIX-v1; conf-guided image, GPU, /source = r6 fork).

  python offline_visibility.py         # mounts: /s2 (ro), /audit (r5 audit payload, ro), /r6 (rw), /artifacts/JointBuildGS (ro)

For each final model (r5 A = P_M_N and A_bias = P_M_B from PHD-STAGE2-PROTECTION-AUDIT-v1, r6 N and B), the PLY of
iteration 3500 is loaded with the calibrated cameras, the 13 training views are rendered (expected depth, accumulated
opacity) and every disk is tested with the r6 seeing rule (jbgs_judgment.compute_E_render: hidden only when more than
0.5 m behind the rendered depth; accumulated opacity < 0.05 occludes nothing). The rows equal the rows of the 3500 dump
(both are written before the densification of iteration 3500; checked). Evaluation only: nothing is trained.
Writes /r6/offline/visibility_<tag>.npz (cnt, E, xyz) and visibility.json."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/source")
import numpy as np  # noqa: E402
import torch  # noqa: E402
from arguments import ModelParams, PipelineParams  # noqa: E402
from gaussian_renderer import render  # noqa: E402
from scene import Scene  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402
import jbgs_judgment as J  # noqa: E402

MODELS = {"r5_N": ("/audit/runs/A/model", "/s2/runs/P_M_N/scene"), "r5_B": ("/audit/runs/A_bias/model", "/s2/runs/P_M_B/scene"),
          "r6_N": ("/r6/runs/N/model", "/s2/runs/P_M_N/scene"), "r6_B": ("/r6/runs/B/model", "/s2/runs/P_M_B/scene")}
OUT = Path("/r6/offline"); OUT.mkdir(parents=True, exist_ok=True)
summary = {}
for tag, (model_dir, scene_dir) in MODELS.items():
    ap = argparse.ArgumentParser(); mp = ModelParams(ap); pp = PipelineParams(ap)
    a = ap.parse_args([])
    a.source_path, a.model_path, a.eval = scene_dir, model_dir, True
    dataset, pipe = mp.extract(a), pp.extract(a)
    g = GaussianModel(dataset.sh_degree)
    with torch.no_grad():
        scene = Scene(dataset, g, load_iteration=3500, shuffle=False)
        cams = scene.getTrainCameras()
        names = [c.image_name for c in cams]
        H, W = cams[0].image_height, cams[0].image_width
        A = J._load_set(Path("/s2/inputs/maps/conf"), names, (H, W), "cuda")
        bg = torch.zeros(3, device="cuda")
        D, AL = {}, {}
        for cam in cams:
            pkg = render(cam, g, pipe, bg)
            D[cam.image_name] = pkg["surf_depth"].squeeze(0); AL[cam.image_name] = pkg["rend_alpha"].squeeze(0)
        E, cnt, n_empty = J.compute_E_render(g.get_xyz, cams, A, D, AL, 0.5, 0.05)
    dump = np.load(Path(model_dir) / "dump/iteration_3500/gaussians.npz")
    xyz = g.get_xyz.detach().cpu().numpy()
    same = bool(dump["xyz"].shape == xyz.shape and np.abs(dump["xyz"] - xyz).max() == 0)
    np.savez_compressed(OUT / f"visibility_{tag}.npz", cnt=cnt.cpu().numpy().astype(np.int16), E=E.cpu().numpy().astype(np.float32),
                        xyz=xyz.astype(np.float32))
    summary[tag] = dict(model=model_dir, n=int(xyz.shape[0]), rows_equal_dump=same, n_empty_pairs=int(n_empty),
                        n_hidden=int((cnt == 0).sum()), train_views=len(cams))
    print(tag, summary[tag], flush=True)
    del g, scene, D, AL
    torch.cuda.empty_cache()
(OUT / "visibility.json").write_text(json.dumps(dict(models=summary, rule="r6 compute_E_render, depth_tol 0.5, alpha_min 0.05",
                                                     scientific_verdict=None), indent=1))
