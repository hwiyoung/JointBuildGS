"""Run real native CUDA surfel projection and Open3D intrinsic recovery checks."""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

from scripts.phd.geogs_p1p2p3_v1.input.jbgs_camera_adapter import apply_projection
from scripts.phd.geogs_p1p2p3_v1.input.prepare import write_json, sha


def run(source, output):
    sys.path.insert(0, str(source))
    from scene.cameras import Camera
    from diff_surfel_rasterization import GaussianRasterizer, GaussianRasterizationSettings
    from utils.mesh_utils import to_cam_open3d
    from utils.point_utils import depths_to_points

    W, H = 1400, 1013
    K = np.array([[922.0550838163813, 0., 702.6193018201524],
                  [0., 922.470063461439, 499.79701601553825], [0., 0., 1.]])
    xyz = torch.tensor([[-1., -.75, 5.], [0., 0., 5.], [1., .75, 5.]], device="cuda")
    expected = (xyz.cpu().numpy() @ K.T)
    expected = expected[:, :2] / expected[:, 2:]
    records = {}
    for mode in ("native_fov_only", "source_calibrated"):
        camera = Camera(colmap_id=1, R=np.eye(3), T=np.zeros(3),
            FoVx=2*math.atan(W/(2*K[0,0])), FoVy=2*math.atan(H/(2*K[1,1])),
            image=torch.zeros((3,H,W)), gt_alpha_mask=None, image_name="fixture", uid=0)
        if mode == "source_calibrated":
            apply_projection(camera, dict(width=W, height=H, K=K.tolist()))
        settings = GaussianRasterizationSettings(image_height=H, image_width=W,
            tanfovx=math.tan(camera.FoVx*.5), tanfovy=math.tan(camera.FoVy*.5),
            bg=torch.zeros(3,device="cuda"), scale_modifier=1., viewmatrix=camera.world_view_transform,
            projmatrix=camera.full_proj_transform, sh_degree=0, campos=camera.camera_center,
            prefiltered=False, debug=False)
        raster = GaussianRasterizer(raster_settings=settings)
        rgb, radii, maps = raster(means3D=xyz, means2D=torch.zeros_like(xyz),
            shs=None, colors_precomp=torch.eye(3,device="cuda"),
            opacities=torch.full((3,1),.6,device="cuda"),
            scales=torch.full((3,2),.015,device="cuda"),
            rotations=torch.tensor([[1.,0.,0.,0.]]*3,device="cuda"), cov3D_precomp=None)
        rgb_np = rgb.detach().cpu().numpy().astype(np.float64)
        yy, xx = np.indices((H,W))
        centers = np.array([[float((image*xx).sum()/image.sum()), float((image*yy).sum()/image.sum())] for image in rgb_np])
        recovered = to_cam_open3d([camera])[0].intrinsic.intrinsic_matrix
        point = depths_to_points(camera, torch.full((1,H,W),5.,device="cuda"))[H//2*W+W//2].cpu().numpy()
        desired = 5*np.linalg.solve(K,np.array([W//2,H//2,1.]))
        records[mode] = dict(measured_centers_px=centers.tolist(), expected_source_centers_px=expected.tolist(),
            delta_centers_px=(centers-expected).tolist(), max_abs_projection_error_px=float(np.abs(centers-expected).max()),
            recovered_open3d_K=recovered.tolist(), recovered_K_max_abs_error=float(np.abs(recovered-K).max()),
            official_depths_to_points_center_delta_m=(point-desired).tolist(), radii=radii.cpu().tolist())
        if mode == "source_calibrated" and (records[mode]["max_abs_projection_error_px"] > .03 or np.abs(recovered-K).max() > 1e-4):
            raise RuntimeError("Native rasterizer and Open3D calibration gate failed")
    output.mkdir(parents=True,exist_ok=False)
    receipt = dict(status="NATIVE_CUDA_SOURCE_PROJECTION_AND_TSDF_INTRINSICS_PASS", scientific_verdict=None,
        records=records, fixture="Three isolated colored native planar Gaussian splats at known camera XYZ; real CUDA render centroids.",
        limitations=["Native point_utils uses a further half-pixel offset; retained and quantified here.",
                     "Original LoD2Depth Open3D pinhole rays sample u+0.5/v+0.5; its depth convention requires separate surface-ray fixture."],
        source_files={name:sha(source/name) for name in ["scene/cameras.py", "utils/mesh_utils.py", "utils/point_utils.py",
          "submodules/diff-surfel-rasterization/cuda_rasterizer/forward.cu"]},
        adapter_sha256=sha(Path(__file__).with_name("jbgs_camera_adapter.py")), source_sha256=sha(__file__))
    write_json(output/"receipt.json",receipt)
    print(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run(args.source,args.output)
