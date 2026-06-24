#!/usr/bin/env python3
"""C2 opacity diagnostic — dump GS-protect ckpt Gaussian means (alpha-gate BYPASS) to P_utm npz.
The C generation-band 0-points come from the TSDF alpha>0.5 re-render dropping op~0 seeds; this
extracts the Gaussian POSITIONS directly (opacity-ignored) so the same Roofer harness can test
whether the in-scope roofs come back. Also reports ckpt keys + opacity distribution (confirms
seed-flag is NOT stored in the ckpt -> seeds identified by position/footprint, not a saved mask).
Read-only of the ckpt; CPU torch.load; NO retraining. Frame: means GS-LOCAL; +[690953,5336071,604]=EPSG:25832.
"""
import argparse
from pathlib import Path
import numpy as np, torch

SHIFT = np.array([690953.0, 5336071.0, 604.0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", required=True)
    A = ap.parse_args()
    ck = torch.load(A.ckpt, map_location="cpu", weights_only=False)
    sd = ck["state_dict"] if "state_dict" in ck else ck
    print(f"[ckpt] top-keys={list(ck.keys())[:8]}")
    print(f"[ckpt] state_dict keys={list(sd.keys())}")
    print(f"[ckpt] has is_seed/seed mask in ckpt? {'YES' if any('seed' in k.lower() for k in list(ck)+list(sd)) else 'NO'}")
    means = sd["means"].float().numpy()
    opa = torch.sigmoid(sd["opacities_raw"].float()).numpy().ravel()
    print(f"[gauss] N={len(means)}  z_local[min={means[:,2].min():.1f} max={means[:,2].max():.1f}]")
    qs = np.percentile(opa, [50, 90, 99, 99.9])
    print(f"[opacity] median={np.median(opa):.4f} p90={qs[1]:.4f} p99={qs[2]:.4f} p99.9={qs[3]:.4f} "
          f"frac>0.5={np.mean(opa>0.5):.4f} frac>0.05={np.mean(opa>0.05):.4f}")
    P = means.astype(np.float64) + SHIFT
    Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(A.out, P_utm=P, opacity=opa.astype(np.float32))
    print(f"[done] N={len(P)} -> {A.out}")


if __name__ == "__main__":
    main()
