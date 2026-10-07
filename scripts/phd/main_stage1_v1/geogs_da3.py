"""PHD-MAIN-STAGE1-v1 DA3 depth of one site for GeoGS (always-trust LoD2) (jointbuildgs:geogs-da3-3d835ec-v1, GPU; network off).
Decided 2026-10-07: the official script's model call, in batches, with a scale check against MVS (geogs_scale.py).

Mounts: /model = DA3NESTED-GIANT-LARGE (revision 8615eefb, the earlier GeoGS work's pinned weights, ro), /official.py = the official
GeoGS preprocessing/get_da3_depth_with_colmap.py (db40c95, ro), /scene = /out/geogs/<site>/scene (rw), /split.json (ro).

Batches = the earlier work's revision 2 (configs/phd/geogs_p1p2p3_v1/da3_batch_revision_v2.json on main): the training views only,
sorted by file name, cut into ceil(N / 8) consecutive groups of balanced size (numpy.array_split: 7 or 8 views), disjoint; each group
needs >= 3 views whose centred camera centres have rank >= 2 (the official Sim3 alignment). Per group: the official read_colmap_data,
model.inference(image, extrinsics, intrinsics, align_to_input_ext_scale=True, process_res=840, process_res_method="upper_bound_resize",
infer_gs=False) (the official arguments plus depth-only output, as the earlier work), and the official saving: raw_depth (inference
resolution: what train.py reads and resizes), raw_depth_upsampled (cubic, as --upsample-to-original), confidence; the batch export.
GPU: process memory fraction 0.8; prediction released + gc + empty_cache after each batch (the earlier work's fix). Seed 0.

  python geogs_da3.py <site>      -> /scene/da3_prior/{raw_depth, raw_depth_upsampled, confidence, batches}/, receipt.json
scientific_verdict: null."""
import gc
import hashlib
import importlib.util
import json
import random
import resource
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from depth_anything_3.api import DepthAnything3

SCENE, MODEL, OFFICIAL = Path("/scene"), Path("/model"), Path("/official.py")
WEIGHT_SHA256 = "8899faf998dedbc230261ab736fa57015280727399429122d44d4f9e7aac2ddd"
OFFICIAL_SHA256 = "97703618afba7563b7f6f8ef2671219b525925e1474140871609db2fc2c7c2ea"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main(site):
    t0 = time.time()
    O = SCENE / "da3_prior"
    if O.exists():
        raise FileExistsError(O)
    assert sha(OFFICIAL) == OFFICIAL_SHA256, "official DA3 script differs"
    assert sha(MODEL / "model.safetensors") == WEIGHT_SHA256, "DA3 weights differ"
    split = json.loads(Path("/split.json").read_text())
    spec = importlib.util.spec_from_file_location("official_geogs_da3", OFFICIAL)
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    paths, extr, intr, stems, sizes = official.read_colmap_data(str(SCENE), "0")
    idx = {Path(p).name.rsplit(".", 1)[0]: i for i, p in enumerate(paths)}
    train = sorted(split["train"], key=lambda n: Path(paths[idx[n]]).name)
    groups = [g.tolist() for g in np.array_split(np.array(train), (len(train) + 7) // 8)]
    pre = []
    for g in groups:
        C = np.stack([-extr[idx[n], :3, :3].T @ extr[idx[n], :3, 3] for n in g])
        rank = int(np.linalg.matrix_rank(C - C.mean(0)))
        pre.append(dict(views=len(g), rank=rank))
        assert 3 <= len(g) <= 8 and rank >= 2, f"batch cannot support the official Sim3 alignment: {len(g)} views, rank {rank}"
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.cuda.set_per_process_memory_fraction(0.8, 0)
    for d in ("raw_depth", "raw_depth_upsampled", "confidence", "batches"):
        (O / d).mkdir(parents=True)
    model = DepthAnything3.from_pretrained(str(MODEL), local_files_only=True).to("cuda")
    model.eval()
    rows = []
    for b, g in enumerate(groups):
        tb = time.time()
        torch.cuda.reset_peak_memory_stats()
        ii = [idx[n] for n in g]
        bp = [paths[i] for i in ii]
        with torch.no_grad():
            pred = model.inference(image=bp, extrinsics=extr[ii], intrinsics=intr[ii], align_to_input_ext_scale=True, process_res=840,
                                   process_res_method="upper_bound_resize", infer_gs=False)
        torch.cuda.synchronize()
        assert pred.depth.shape[0] == len(g)
        stats = []
        for k, n in enumerate(g):
            d = pred.depth[k].astype(np.float32)
            c = pred.conf[k].astype(np.float32)
            v = np.isfinite(d) & (d > 0)
            np.save(O / "raw_depth" / f"{stems[ii[k]]}.npy", d)
            np.save(O / "raw_depth_upsampled" / f"{stems[ii[k]]}.npy", cv2.resize(d, sizes[ii[k]], interpolation=cv2.INTER_CUBIC).astype(np.float32))
            np.save(O / "confidence" / f"{stems[ii[k]]}.npy", c)
            stats.append(dict(view=n, shape=list(d.shape), valid=float(v.mean()), median_m=float(np.median(d[v])) if v.any() else None))
        np.savez(O / "batches" / f"batch_{b:03d}.npz", depth=pred.depth, conf=pred.conf, extrinsics=pred.extrinsics, intrinsics=pred.intrinsics,
                 input_extrinsics=extr[ii], input_intrinsics=intr[ii], names=np.array(g))
        ext_kept = bool(np.allclose(pred.extrinsics, extr[ii][:, :3, :], rtol=0, atol=1e-4))
        rows.append(dict(batch=b, views=g, input_extrinsics_kept=ext_kept, seconds=round(time.time() - tb, 1),
                         peak_cuda_allocated_gib=round(torch.cuda.max_memory_allocated() / 2 ** 30, 2), stats=stats))
        del pred
        gc.collect()
        torch.cuda.empty_cache()
        print(json.dumps(dict(batch=b, views=len(g), seconds=rows[-1]["seconds"], peak_gib=rows[-1]["peak_cuda_allocated_gib"], ext_kept=ext_kept)), flush=True)
    rec = dict(task_id="PHD-MAIN-STAGE1-v1", site=site, rule=__doc__, model="depth-anything/DA3NESTED-GIANT-LARGE", model_sha256=WEIGHT_SHA256,
               official_script_sha256=OFFICIAL_SHA256, driver_sha256=sha(__file__), train_views=len(train), batches=len(groups), batch_preflight=pre,
               batch_rows=rows, device=torch.cuda.get_device_name(0), torch=torch.__version__, cuda=torch.version.cuda, memory_fraction=0.8,
               seconds=round(time.time() - t0, 1), peak_rss_gib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20, 2), scientific_verdict=None)
    (O / "receipt.json").write_text(json.dumps(rec, indent=1))
    print("done", site, len(groups), "batches", rec["seconds"], "s")


if __name__ == "__main__":
    main(sys.argv[1])
