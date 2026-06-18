"""Step 1b helper — dump GS Gaussian centers from final.pt to a torch-free .npz.

Read-only analysis (no engine logic). Runs in the GS dev container (needs torch);
the heavy geo analysis (tum_qc_analyze.py) runs in the P0 tools image which has
geopandas-less GDAL/laspy but no torch, hence this split.

Out frame = GS LOCAL (OPF canonical). EPSG:25832 = local + [690953, 5336071, 604]
(scene_reference_frame.json base_to_canonical.shift; 02_opf2colmap.py:201-211).
"""
import numpy as np, torch
from pathlib import Path

CKPT = Path("/workspace/JointBuildGS/results/tum_transfer/run/ckpt/final.pt")
OUT = Path("/workspace/JointBuildGS/results/tum_transfer/analysis/gs_centers.npz")
OUT.parent.mkdir(parents=True, exist_ok=True)

ck = torch.load(CKPT, map_location="cpu", weights_only=False)
sd = ck["state_dict"]
means = sd["means"].numpy().astype(np.float32)            # (N,3) local
opacity = torch.sigmoid(sd["opacities_raw"]).numpy().astype(np.float32).ravel()
np.savez(OUT, means=means, opacity=opacity)
print(f"[dump] N={means.shape[0]}  opacity>0.05={(opacity>0.05).sum()}  -> {OUT}")
print(f"[dump] local bbox min={np.round(means.min(0),1)} max={np.round(means.max(0),1)}")
