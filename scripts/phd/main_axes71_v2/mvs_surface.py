"""PHD-MAIN-AXES71-v2 일 1 'MVS 표면' (order v2 4절): the training views' MVS depth maps fused, without training, into one mesh per site by
the stage-1 post's TSDF path. CPU only, in jointbuildgs:geogs-conf-guided-v1 (the image of the stage-1 post: Open3D 0.19.0), through
run_mvs_surface.sh. No GPU, no training; every input read-only, writes only /w = AX/mvs.

  python mvs_surface.py check_fuse <site>        the CPU path below re-run on the MVS-based fusion's composite depth maps
                                                 (SB/runs/<site>/mvsfuse_LoD2/depth, zero colour as gpu_bl.depthfuse) and compared with
                                                 its GPU-run mesh SB/runs/<site>/mvsfuse_LoD2/post/mesh_tsdf.ply -> /w/check_fuse_<site>.json
  python mvs_surface.py build <site> <a|b>       -> /w/<site>/mesh_mvs_<a|b>.ply, /w/<site>/receipt_<site>.json (entry 'a' / 'b')
  python mvs_surface.py ranges <site>            per-axis vertex min / max of the MVS meshes next to the result meshes -> receipt 'frame_check'

Depth of each training view (S0/fork_inputs/s61/<site>/split.json 'train', sorted by name as the fork's readColmapSceneInfo):
  a  the depth the method's training reads with the observation-confidence mask on (fork r12 jbgs_judgment.py 603-606, 548-563,
     1225-1229, 317-329): M = maps/mvs (-> S0/s61/export/<site>/LoD2/mvs, the COLMAP geometric-pass depth, NaN = none),
     A = maps/conf (-> .../LoD2/conf, 0/1); kept where isfinite(M) & M > 0 & A > 0 (weighted_l1's valid_t)
  b  the depth the same training reads with the switch confidence_mask = 0 (jbgs_judgment.py 604: conf_photometric, mvs_photometric):
     the mask-off export (B173 주변: S0/s61/export_maskoff/B173nb_b10/LoD2; B0, R1: S2/s61/export_maskoff/<site>/LoD2) = the COLMAP
     photometric-pass depth before the geometric filter (checked equal to <view>.JPG.photometric.bin by PHD-MAIN-FILL-v1
     obs_masked/inputs_om.py, SL/prep/obs_masked/inputs.json), kept where isfinite & > 0 & conf_photometric > 0
TSDF = scripts/phd/main_stage1_v1/gpu_s1.py post / samepath and scripts/phd/main_baselines_v1/gpu_bl.py depthfuse, line by line on CPU:
  cameras    scene_LoD2/sparse/0 (images.bin, cameras.bin; scene_ALS byte-identical) read by the fork's colmap_loader; extrinsic =
             getWorld2View2(R, T) (float32, = world_view_transform.T of to_cam_open3d); intrinsic = the fork's to_cam_open3d value
             (projection of jbgs_camera_adapter.apply_projection times ndc2pix, float32) = jbgs_calibration.json K
  box mask   gpu_s1.box_of (s02 range rectangle + 2 m; z = 5th percentile of the s52 box GT - 5 m .. its maximum + 5 m) and gpu_s1.box_mask
             (unproject with the same K and inv(W2C), float32; keep inside the box and d > 0); depth outside -> 0 (extract_mesh_bounded)
  volume     o3d.pipelines.integration.ScalableTSDFVolume(voxel_length 0.05, sdf_trunc 0.25, RGB8); RGBDImage.create_from_color_and_depth(
             depth_trunc 300, depth_scale 1.0, convert_rgb_to_intensity False); extract_triangle_mesh(); no post-processing
  colour     the training image (S0/fork_inputs/s61/<site>/images/<view>.jpg, RGB) -- the colour does not change the geometry; check_fuse
             uses zeros as gpu_bl.depthfuse
Frame: the training cameras' local frame = the frame of every result mesh (S1 post, SB post); plane offset dm_common.OFFSET.
scientific_verdict: null."""
import datetime as dt
import filecmp
import json
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, "/source")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402

from scene.colmap_loader import read_extrinsics_binary, read_intrinsics_binary, qvec2rotmat  # noqa: E402
from utils.graphics_utils import getWorld2View2  # noqa: E402

TASK = "PHD-MAIN-AXES71-v2"
S0, S1, S2, SB, DR, W = Path("/s0"), Path("/s1"), Path("/s2"), Path("/sb"), Path("/dr"), Path("/w")
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
VOXEL, SDF_TRUNC, DEPTH_TRUNC = 0.05, 0.25, 300.0
KST = dt.timezone(dt.timedelta(hours=9))
OFFSET = [690953.0, 5336071.0]
MASKOFF = {"B0_b10": S2 / "s61/export_maskoff/B0_b10/LoD2", "B173nb_b10": S0 / "s61/export_maskoff/B173nb_b10/LoD2",
           "R1rep_b10": S2 / "s61/export_maskoff/R1rep_b10/LoD2"}
HOST = {"/s0": "PH/main_stage0_v1/PHD-MAIN-STAGE0-v1", "/s1": "PH/main_stage1_v1/PHD-MAIN-STAGE1-v1", "/s2": "PH/main_stage2_v1/PHD-MAIN-STAGE2-v1",
        "/sb": "PH/main_baselines_v1/PHD-MAIN-BASELINES-v1", "/dr": "PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1",
        "/w": "PH/main_axes71_v2/PHD-MAIN-AXES71-v2/mvs", "/source": "src/phd/forks/GeoGS-conf-guided-v1-r12"}
f32 = np.float32


def now():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def peak_gb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)


def jdump(p, obj):
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------------------------------------ cameras (the fork's path)
def cameras(site):
    F = S0 / "fork_inputs/s61" / site
    sc = F / "scene_LoD2"
    same = {k: filecmp.cmp(sc / k, F / "scene_ALS" / k, shallow=False) for k in ("sparse/0/images.bin", "sparse/0/cameras.bin", "jbgs_calibration.json")}
    split = json.loads((F / "split.json").read_text())
    ext = read_extrinsics_binary(str(sc / "sparse/0/images.bin"))
    intr = read_intrinsics_binary(str(sc / "sparse/0/cameras.bin"))
    cal = json.loads((sc / "jbgs_calibration.json").read_text())
    if cal["schema"] != "jointbuildgs.geogs.source_calibration.v1":
        raise SystemExit("calibration schema")
    by = {}
    for e in ext.values():
        by[os.path.basename(e.name).split(".")[0]] = e                    # dataset_readers.readColmapCameras image_name
    names = sorted(n for n in by if n in set(split["train"]))           # sorted by image_name, then the split's training names
    if len(names) != len(split["train"]):
        raise SystemExit(f"{site}: {len(split['train']) - len(names)} training names not in images.bin")
    cams = []
    for n in names:
        e = by[n]
        ci = intr[e.camera_id]
        Wd, Hd = int(ci.width), int(ci.height)
        K = np.asarray(cal["images"][n]["K"], np.float64)
        if (cal["images"][n]["width"], cal["images"][n]["height"]) != (Wd, Hd):
            raise SystemExit(f"{n}: calibration size")
        # jbgs_camera_adapter.apply_projection (float32 tensor entries) and to_cam_open3d (projection @ ndc2pix, float32)
        p00, p11 = f32(2 * K[0, 0] / Wd), f32(2 * K[1, 1] / Hd)
        p02, p12 = f32((2 * K[0, 2] + 1 - Wd) / Wd), f32((2 * K[1, 2] + 1 - Hd) / Hd)
        fx, fy = f32(f32(Wd / 2) * p00), f32(f32(Hd / 2) * p11)
        cx, cy = f32(f32(f32(Wd / 2) * p02) + f32((Wd - 1) / 2)), f32(f32(f32(Hd / 2) * p12) + f32((Hd - 1) / 2))
        R = np.transpose(qvec2rotmat(e.qvec))
        T = np.array(e.tvec)
        W2C = getWorld2View2(R, T)                                          # float32; world_view_transform.T
        cams.append(dict(name=n, W=Wd, H=Hd, fx=fx, fy=fy, cx=cx, cy=cy, K=K, W2C=W2C, colmap_model=ci.model,
                         colmap_params=[float(x) for x in ci.params]))
    return cams, dict(scene=str(sc), scene_ALS_identical=same, train_in_split=len(split["train"]), test_in_split=len(split.get("test", [])),
                      split=str(F / "split.json"))


def box_of(site):
    """gpu_s1.box_of: the stage-0 post box."""
    rng = json.loads((DR / "s02_box" / site / "range.json").read_text())
    poly = np.asarray(rng["polygon_local"], np.float64)
    gz = np.load(DR / "s52/box_gt" / site / "gt_points.npz")["xyz"][:, 2].astype(np.float64)
    return np.array([[poly[:, 0].min() - 2.0, poly[:, 1].min() - 2.0, float(np.percentile(gz, 5)) - 5.0],
                     [poly[:, 0].max() + 2.0, poly[:, 1].max() + 2.0, float(gz.max()) + 5.0]])


def box_checks(site, BOX):
    out = {}
    for tag, p in (("S1 prop_LoD2_s0 post", S1 / "stage1" / site / "prop_LoD2_s0/post/post.json"),
                   ("SB mvsfuse_LoD2 post", SB / "runs" / site / "mvsfuse_LoD2/post/post.json")):
        if p.exists():
            b = np.asarray(json.loads(p.read_text())["box"], np.float64)
            out[tag] = dict(path=str(p), equal=bool(np.array_equal(b, BOX)), max_abs_diff=float(np.abs(b - BOX).max()))
    return out


def box_mask(c, d, BOX):
    """gpu_s1.unproject + box_mask in float32."""
    H, Wd = d.shape
    v, u = np.meshgrid(np.arange(H, dtype=f32), np.arange(Wd, dtype=f32), indexing="ij")
    x = (u - c["cx"]) / c["fx"]
    y = (v - c["cy"]) / c["fy"]
    c2w = np.linalg.inv(c["W2C"].astype(f32)).astype(f32)
    Pc = np.stack([x * d, y * d, d, np.ones_like(d)], -1).reshape(-1, 4).astype(f32)
    Pw = (Pc @ c2w.T)[:, :3].reshape(H, Wd, 3)
    lo, hi = BOX[0].astype(f32), BOX[1].astype(f32)
    return ((Pw >= lo) & (Pw <= hi)).all(-1) & (d > 0)


def integrate(cams, depth_of, colour_of, BOX, log_every=25):
    """extract_mesh_bounded of the fork with the box mask; returns mesh and per-view records."""
    vol = o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
                                                       color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    rec = dict(views=0, views_without_depth=[], px=0, px_depth=0, px_in_box=0, px_in_box_le300=0)
    t_in = 0.0
    for i, c in enumerate(cams):
        d = depth_of(c)
        if d is None:
            rec["views_without_depth"].append(c["name"])
            d = np.zeros((c["H"], c["W"]), f32)
        d = np.ascontiguousarray(d, dtype=f32)
        if d.shape != (c["H"], c["W"]):
            raise SystemExit(f"{c['name']}: depth shape {d.shape}")
        mk = box_mask(c, d, BOX)
        rec["views"] += 1
        rec["px"] += int(d.size)
        rec["px_depth"] += int((d > 0).sum())
        rec["px_in_box"] += int(mk.sum())
        d[~mk] = 0.0
        rec["px_in_box_le300"] += int(((d > 0) & (d <= DEPTH_TRUNC)).sum())
        rgb = np.ascontiguousarray(colour_of(c), dtype=np.uint8)
        t0 = time.time()
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(rgb), o3d.geometry.Image(d), depth_trunc=DEPTH_TRUNC,
                                                                  convert_rgb_to_intensity=False, depth_scale=1.0)
        intr = o3d.camera.PinholeCameraIntrinsic(width=c["W"], height=c["H"], cx=float(c["cx"]), cy=float(c["cy"]), fx=float(c["fx"]), fy=float(c["fy"]))
        vol.integrate(rgbd, intrinsic=intr, extrinsic=np.asarray(c["W2C"], np.float64))
        t_in += time.time() - t0
        if (i + 1) % log_every == 0 or i + 1 == len(cams):
            print(f"[{now()}] integrated {i + 1}/{len(cams)} (integrate {t_in:.0f} s, peak {peak_gb()} GB)", flush=True)
    t0 = time.time()
    mesh = vol.extract_triangle_mesh()
    rec["seconds_integrate"] = round(t_in, 1)
    rec["seconds_extract"] = round(time.time() - t0, 1)
    rec["mean_share_of_pixels_in_box"] = rec["px_in_box"] / max(rec["px"], 1) if rec["px"] else None
    return mesh, rec


def ranges(V):
    return dict(min=[float(x) for x in V.min(0)], max=[float(x) for x in V.max(0)]) if len(V) else None


# ------------------------------------------------------------------------------------------------ inputs
def real(p):
    return os.path.realpath(p)


def maps_a(site):
    m = S0 / "fork_inputs/s61" / site / "maps"
    return Path(real(m / "mvs")), Path(real(m / "conf"))


def maps_b(site):
    return MASKOFF[site] / "mvs", MASKOFF[site] / "conf"


def colour(site):
    def f(c):
        img = cv2.imread(str(S0 / "fork_inputs/s61" / site / "images" / f"{c['name']}.jpg"), cv2.IMREAD_COLOR)
        if img is None or img.shape[:2] != (c["H"], c["W"]):
            raise SystemExit(f"image {c['name']}")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return f


# ------------------------------------------------------------------------------------------------ modes
def depth_source(site, var):
    """the depth rule of variant a / b (see the module text) and its running checks."""
    mdir, cdir = maps_a(site) if var == "a" else maps_b(site)
    mdir_a, _ = maps_a(site)
    als_mvs = S0 / "s61/export" / site / "ALS/mvs"
    st = dict(depth_maps_found=0, A_equals_validity_views=0, px_A_pos=0, px_M_valid=0, px_A_pos_M_invalid=0, px_M_valid_A_zero=0,
              ALS_export_mvs_equal_views=0, maskoff_vs_geometric=None)
    cmp_pg = dict(px_geo_valid=0, px_photo_valid=0, px_both=0, px_equal=0, px_photo_only=0, absdiff_hist_edges_m=[0, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 5, 1e30],
                  absdiff_hist=[0] * 8)
    if var == "b":
        st["maskoff_vs_geometric"] = cmp_pg

    def depth_of(c):
        fm, fc = mdir / f"{c['name']}.npy", cdir / f"{c['name']}.npy"
        if not (fm.exists() and fc.exists()):
            return None
        M = np.load(fm).astype(f32)
        A = np.load(fc).astype(f32)
        st["depth_maps_found"] += 1
        vm = np.isfinite(M) & (M > 0)
        va = A > 0
        st["px_A_pos"] += int(va.sum())
        st["px_M_valid"] += int(vm.sum())
        st["px_A_pos_M_invalid"] += int((va & ~vm).sum())
        st["px_M_valid_A_zero"] += int((vm & ~va).sum())
        st["A_equals_validity_views"] += int(np.array_equal(va, vm))
        if var == "a":
            Ma = np.load(als_mvs / f"{c['name']}.npy")
            st["ALS_export_mvs_equal_views"] += int(np.array_equal(np.isnan(Ma), np.isnan(M)) and np.array_equal(Ma[~np.isnan(Ma)], M[~np.isnan(M)]))
        else:
            G = np.load(mdir_a / f"{c['name']}.npy").astype(f32)
            vg = np.isfinite(G) & (G > 0)
            both = vg & vm & va
            cmp_pg["px_geo_valid"] += int(vg.sum())
            cmp_pg["px_photo_valid"] += int((vm & va).sum())
            cmp_pg["px_both"] += int(both.sum())
            cmp_pg["px_photo_only"] += int(((vm & va) & ~vg).sum())
            dd = np.abs(M[both].astype(np.float64) - G[both])
            cmp_pg["px_equal"] += int((dd == 0).sum())
            h, _ = np.histogram(dd, bins=cmp_pg["absdiff_hist_edges_m"])
            cmp_pg["absdiff_hist"] = [int(a + b) for a, b in zip(cmp_pg["absdiff_hist"], h)]
        return np.where(vm & va, M, f32(0)).astype(f32)
    return depth_of, st, mdir, cdir


def write_receipt(site, cams, camrec, BOX, var, entry):
    O = W / site
    O.mkdir(parents=True, exist_ok=True)
    R = O / f"receipt_{site}.json"
    r = json.loads(R.read_text()) if R.exists() else {}
    r.update(task=TASK, part="일 1 MVS 표면", site=site, cameras=camrec, training_views=[c["name"] for c in cams],
             intrinsics=dict(rule="to_cam_open3d of the calibrated fork camera (float32) = jbgs_calibration.json K (measurement K with cx, cy - 0.5)",
                             first_view=dict(name=cams[0]["name"], fx=float(cams[0]["fx"]), fy=float(cams[0]["fy"]), cx=float(cams[0]["cx"]),
                                             cy=float(cams[0]["cy"]), K_calibration=cams[0]["K"].tolist(), colmap_model=cams[0]["colmap_model"],
                                             colmap_params=cams[0]["colmap_params"]),
                             max_abs_diff_to_calibration_px=float(max(max(abs(float(c["fx"]) - c["K"][0, 0]), abs(float(c["fy"]) - c["K"][1, 1]),
                                                                          abs(float(c["cx"]) - c["K"][0, 2]), abs(float(c["cy"]) - c["K"][1, 2])) for c in cams))),
             box=dict(value=BOX.tolist(), rule="gpu_s1.box_of", checks=box_checks(site, BOX)),
             settings=dict(voxel_m=VOXEL, sdf_trunc_m=SDF_TRUNC, depth_trunc_m=DEPTH_TRUNC, depth_scale=1.0, colour="per variant (entry colour)",
                           post_processing="none", volume="open3d.pipelines.integration.ScalableTSDFVolume (legacy, CPU)",
                           open3d=o3d.__version__, image=os.environ.get("JBGS_IMAGE", ""), image_id=os.environ.get("JBGS_IMAGE_ID", ""),
                           code="scripts/phd/main_axes71_v2/mvs_surface.py (= gpu_s1.post / gpu_bl.depthfuse TSDF path on CPU)",
                           fork_helpers="src/phd/forks/GeoGS-conf-guided-v1-r12 scene/colmap_loader.py, utils/graphics_utils.getWorld2View2",
                           cpus=os.environ.get("JBGS_CPUS", ""), memory_limit=os.environ.get("JBGS_MEM", "")),
             frame=dict(rule="the training cameras' local frame (scene_<prior>/sparse/0) = the frame of every result mesh (S1, SB post TSDF); "
                             "plane offset to the survey grid dm_common.OFFSET", OFFSET=OFFSET),
             mounts=HOST, scientific_verdict=None)
    r.setdefault("variants", {})[var] = entry
    jdump(R, r)


def build(site, var):
    t_all = time.time()
    cams, camrec = cameras(site)
    BOX = box_of(site)
    depth_of, st, mdir, cdir = depth_source(site, var)
    t_load = time.time()
    mesh, rec = integrate(cams, depth_of, colour(site), BOX)
    O = W / site
    O.mkdir(parents=True, exist_ok=True)
    out = O / f"mesh_mvs_{var}.ply"
    t0 = time.time()
    o3d.io.write_triangle_mesh(str(out), mesh)
    t_write = time.time() - t0
    V = np.asarray(mesh.vertices)
    entry = dict(
        variant=var,
        what=("관측 신뢰도 마스크를 거친 MVS 깊이(학습이 마스크를 켜고 읽는 깊이) = COLMAP 기하 단계 깊이" if var == "a" else
              "마스크 전 깊이 = 관측 신뢰도 마스크 스위치를 끈 학습이 읽는 깊이 = COLMAP 광도 단계 깊이(기하 거름 전)"),
        mesh=str(out), mesh_host=str(out).replace("/w", HOST["/w"], 1),
        depth_dir=str(mdir), conf_dir=str(cdir), depth_rule="depth = M where isfinite(M) & M > 0 & A > 0, else 0 (jbgs_judgment.weighted_l1 valid_t)",
        views=rec["views"], depth_maps_used=st["depth_maps_found"], views_without_depth=rec["views_without_depth"],
        pixels=dict(all=rec["px"], with_depth=rec["px_depth"], in_box=rec["px_in_box"], in_box_le_300m=rec["px_in_box_le300"],
                    mean_share_in_box=rec["mean_share_of_pixels_in_box"]),
        mask_checks=st,
        vertices=int(len(mesh.vertices)), triangles=int(len(mesh.triangles)), vertex_range=ranges(V),
        seconds=dict(integrate=rec["seconds_integrate"], extract=rec["seconds_extract"], write=round(t_write, 1),
                     load_mask_and_other=round(time.time() - t_load - rec["seconds_integrate"] - rec["seconds_extract"] - t_write, 1),
                     all=round(time.time() - t_all, 1)),
        colour="training image RGB8", fusion="one piece (this script's integrate = extract_mesh_bounded on CPU)",
        peak_host_gb=peak_gb(), made_at=now())
    write_receipt(site, cams, camrec, BOX, var, entry)
    print(json.dumps({k: entry[k] for k in ("variant", "depth_maps_used", "vertices", "triangles", "seconds", "peak_host_gb")}), flush=True)


def prep_tiled(site, var, wd):
    """the inputs of scripts/phd/main_fill_v1/cdgs/tsdf_tiled.py (its 'prep' made on CPU from this script's cameras, box mask and depth rule):
    WD/inputs/depth_masked.npy (views x H x W, the depth handed to Open3D after the box mask), cams.npz (names, intr fx fy cx cy, wh,
    extrinsic), meta.json; the view order and every value = build(site, var) before vol.integrate."""
    t0 = time.time()
    cams, camrec = cameras(site)
    BOX = box_of(site)
    depth_of, st, mdir, cdir = depth_source(site, var)
    I = Path(wd) / "inputs"
    I.mkdir(parents=True, exist_ok=True)
    H, Wd = cams[0]["H"], cams[0]["W"]
    D = np.lib.format.open_memmap(I / "depth_masked.npy", mode="w+", dtype=f32, shape=(len(cams), H, Wd))
    rec = dict(px=0, px_depth=0, px_in_box=0, px_in_box_le300=0, views_without_depth=[])
    share, kept = [], []
    for i, c in enumerate(cams):
        d = depth_of(c)
        if d is None:
            rec["views_without_depth"].append(c["name"])
            d = np.zeros((H, Wd), f32)
        d = np.ascontiguousarray(d, dtype=f32)
        mk = box_mask(c, d, BOX)
        rec["px"] += int(d.size)
        rec["px_depth"] += int((d > 0).sum())
        rec["px_in_box"] += int(mk.sum())
        share.append(float((d > 0).mean()))
        kept.append(float(mk.mean()))
        d[~mk] = 0.0
        rec["px_in_box_le300"] += int(((d > 0) & (d <= DEPTH_TRUNC)).sum())
        D[i] = d
    D.flush()
    del D
    intr = np.array([[float(c["fx"]), float(c["fy"]), float(c["cx"]), float(c["cy"])] for c in cams], np.float64)
    np.savez(I / "cams.npz", names=np.array([c["name"] for c in cams]), intr=intr, wh=np.array([[c["W"], c["H"]] for c in cams], np.int64),
             extrinsic=np.stack([np.asarray(c["W2C"], np.float64) for c in cams]))
    meta = dict(site=site, result=f"mvs_{var}", prior_scene="LoD2 (scene_LoD2 = scene_ALS cameras)", depth_dir=str(mdir), conf_dir=str(cdir),
                box=BOX.tolist(), box_is_site_box=True, views=len(cams), width=int(Wd), height=int(H), views_without_depth=rec["views_without_depth"],
                mean_share_of_pixels_in_box=float(np.mean(kept)), mean_share_of_pixels_with_depth=float(np.mean(share)),
                pixels_kept=rec["px_in_box"], pixels=rec, mask_checks=st, depth_maps_used=st["depth_maps_found"],
                tsdf=dict(voxel_m=VOXEL, sdf_trunc_m=SDF_TRUNC, depth_trunc_m=DEPTH_TRUNC, volume_unit_resolution=16, depth_sampling_stride=4),
                made_by="scripts/phd/main_axes71_v2/mvs_surface.py prep_tiled (CPU; cameras and box mask as build)",
                seconds=round(time.time() - t0, 1), peak_host_gb=peak_gb(), written=now(), scientific_verdict=None)
    jdump(I / "meta.json", meta)
    print(json.dumps({k: meta[k] for k in ("views", "depth_maps_used", "pixels_kept", "seconds", "peak_host_gb")}), flush=True)


def receipt_tiled(site, var, wd, tag_seconds):
    """the receipt entry of a tiled build (inputs/meta.json, the merge record, the mesh)."""
    cams, camrec = cameras(site)
    BOX = box_of(site)
    meta = json.loads((Path(wd) / "inputs/meta.json").read_text())
    mj = json.loads((W / site / f"tiled_{var}.json").read_text())
    plan = json.loads((Path(wd) / "plan/plan.json").read_text())
    out = W / site / f"mesh_mvs_{var}.ply"
    m = o3d.io.read_triangle_mesh(str(out))
    V = np.asarray(m.vertices)
    tj = [json.loads(p.read_text()) for p in sorted((Path(wd) / "tiles").glob("tile*.json"))]
    ts = json.loads(tag_seconds) if tag_seconds else {}
    entry = dict(
        variant=var,
        what=("관측 신뢰도 마스크를 거친 MVS 깊이(학습이 마스크를 켜고 읽는 깊이) = COLMAP 기하 단계 깊이" if var == "a" else
              "마스크 전 깊이 = 관측 신뢰도 마스크 스위치를 끈 학습이 읽는 깊이 = COLMAP 광도 단계 깊이(기하 거름 전)"),
        mesh=str(out), mesh_host=str(out).replace("/w", HOST["/w"], 1),
        depth_dir=meta["depth_dir"], conf_dir=meta["conf_dir"], depth_rule="depth = M where isfinite(M) & M > 0 & A > 0, else 0 (jbgs_judgment.weighted_l1 valid_t)",
        views=meta["views"], depth_maps_used=meta["depth_maps_used"], views_without_depth=meta["views_without_depth"],
        pixels=dict(all=meta["pixels"]["px"], with_depth=meta["pixels"]["px_depth"], in_box=meta["pixels"]["px_in_box"],
                    in_box_le_300m=meta["pixels"]["px_in_box_le300"], mean_share_in_box=meta["mean_share_of_pixels_in_box"]),
        mask_checks=meta["mask_checks"],
        vertices=int(len(m.vertices)), triangles=int(len(m.triangles)), vertex_range=ranges(V),
        colour="zero (the tiled path writes zero colour, as gpu_bl.depthfuse; the geometry does not depend on the colour)",
        fusion=("tiled: scripts/phd/main_fill_v1/cdgs/tsdf_tiled.py plan / order / tile / merge on this script's prep_tiled inputs = the one-piece "
                "Open3D integration's voxels in every tile core, its triangles and triangle order (validated in PH/main_fill_v1/PHD-MAIN-FILL-v1/"
                "work/tsdf_tiled/validation.md); one piece ran out of memory under the 36 GB limit (B0 판 나, rc 137, 10-22 20:39)"),
        tiled=dict(work_dir=str(wd), layout=mj["tiled"]["layout"], onepiece_units=plan["onepiece_units"], onepiece_unit_gb=plan["onepiece_unit_gb"],
                   e_lat_max_m=plan["e_lat_max_m"], vertices=mj["tiled"]["vertices"], tiles=mj["tiled"]["tiles"],
                   tile_checks=[dict(k=x["k"], kept=x["kept"], blocks=dict(every_unit_one_block=x["blocks"]["every_unit_one_block"],
                                                                           units_open=x["blocks"]["units_open"],
                                                                           against_simulated_tile_order=x["blocks"]["against_simulated_tile_order"]))
                                for x in tj]),
        seconds=dict(prep=meta["seconds"], tiles=mj["seconds"]["tiles"], merge=mj["seconds"]["merge"], steps_wall=ts,
                     all=round(sum(ts.values()), 1) if ts else None),
        peak_host_gb=mj["peak_host_gb"], made_at=now())
    write_receipt(site, cams, camrec, BOX, var, entry)
    print(json.dumps({k: entry[k] for k in ("variant", "depth_maps_used", "vertices", "triangles", "seconds", "peak_host_gb")}), flush=True)


def check_fuse(site):
    t_all = time.time()
    cams, camrec = cameras(site)
    BOX = box_of(site)
    D = SB / "runs" / site / "mvsfuse_LoD2/depth"

    def depth_of(c):
        f = D / f"{c['name']}.npy"
        if not f.exists():
            return None
        d = np.load(f).astype(f32)
        return np.where(np.isfinite(d) & (d > 0), d, 0.0).astype(f32)

    def zero(c):
        return np.zeros((c["H"], c["W"], 3), np.uint8)

    mesh, rec = integrate(cams, depth_of, zero, BOX)
    V, Fc = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    ref = o3d.io.read_triangle_mesh(str(SB / "runs" / site / "mvsfuse_LoD2/post/mesh_tsdf.ply"))
    Vr, Fr = np.asarray(ref.vertices), np.asarray(ref.triangles)
    same_n = len(V) == len(Vr) and len(Fc) == len(Fr)
    out = dict(site=site, purpose="the CPU path of this script against the GPU-run post TSDF of the MVS-based fusion (same depth maps)",
               ours=dict(vertices=int(len(V)), triangles=int(len(Fc)), vertex_range=ranges(V)),
               reference=dict(path=str(SB / "runs" / site / "mvsfuse_LoD2/post/mesh_tsdf.ply"), vertices=int(len(Vr)), triangles=int(len(Fr)),
                              vertex_range=ranges(Vr)),
               same_counts=bool(same_n),
               vertices_max_abs_diff_m=float(np.abs(V - Vr).max()) if same_n else None,
               vertices_equal=bool(same_n and np.array_equal(V, Vr)), triangles_equal=bool(same_n and np.array_equal(Fc, Fr)),
               box=dict(value=BOX.tolist(), checks=box_checks(site, BOX)), views=rec["views"], views_without_depth=rec["views_without_depth"],
               mean_share_of_pixels_in_box=rec["mean_share_of_pixels_in_box"],
               reference_mean_share_of_pixels_in_box=json.loads((SB / "runs" / site / "mvsfuse_LoD2/post/post.json").read_text())["tsdf"]["mean_share_of_pixels_in_box"],
               seconds=dict(integrate=rec["seconds_integrate"], extract=rec["seconds_extract"], all=round(time.time() - t_all, 1)),
               peak_host_gb=peak_gb(), made_at=now(), open3d=o3d.__version__, scientific_verdict=None)
    if not same_n and len(V) and len(Vr):
        from scipy.spatial import cKDTree
        d1, _ = cKDTree(Vr).query(V, k=1)
        out["nearest_ours_to_reference_m"] = dict(max=float(d1.max()), q999=float(np.quantile(d1, 0.999)), share_gt_1mm=float((d1 > 1e-3).mean()))
    jdump(W / f"check_fuse_{site}.json", out)
    print(json.dumps({k: out[k] for k in ("ours", "reference", "same_counts", "vertices_max_abs_diff_m", "vertices_equal", "triangles_equal")}), flush=True)


def frame_check(site):
    R = W / site / f"receipt_{site}.json"
    r = json.loads(R.read_text())
    rows = {}
    for v in ("a", "b"):
        p = W / site / f"mesh_mvs_{v}.ply"
        if p.exists():
            m = o3d.io.read_triangle_mesh(str(p))
            rows[f"MVS 판 {'가' if v == 'a' else '나'}"] = dict(path=str(p), vertices=len(m.vertices), **ranges(np.asarray(m.vertices)))
    refs = [("본 방법 prop_LoD2_s0 (S1 post)", S1 / "stage1" / site / "prop_LoD2_s0/post/mesh_tsdf.ply"),
            ("결합 mvsfuse_LoD2 (SB post)", SB / "runs" / site / "mvsfuse_LoD2/post/mesh_tsdf.ply")]
    if site == "B173nb_b10":
        refs[0] = ("본 방법 prop_LoD2_s0 (S0 stage0 b1_LoD2 post)", S0 / "stage0/b1_LoD2/post/mesh_tsdf.ply")
    for tag, p in refs:
        if p.exists():
            m = o3d.io.read_triangle_mesh(str(p))
            rows[tag] = dict(path=str(p), vertices=len(m.vertices), **ranges(np.asarray(m.vertices)))
    g = S1 / "defs" / site / "gt_classes.npz"
    if g.exists():
        X = np.load(g)["xyz_gt_points"].astype(np.float64)
        rows["참값 점 (S1/defs gt_classes.npz xyz_gt_points)"] = dict(path=str(g), vertices=len(X), **ranges(X))
    r["frame_check"] = dict(rows=rows, box=r.get("box", {}).get("value"), made_at=now())
    jdump(R, r)
    for k, v in rows.items():
        print(k, v["vertices"], [round(x, 2) for x in v["min"]], [round(x, 2) for x in v["max"]], flush=True)


if __name__ == "__main__":
    mode, site = sys.argv[1], sys.argv[2]
    if site not in SITES:
        raise SystemExit(f"site {site}")
    print(f"[{now()}] {mode} {site} {' '.join(sys.argv[3:])} open3d {o3d.__version__}", flush=True)
    if mode == "build":
        if sys.argv[3] not in ("a", "b"):
            raise SystemExit("variant a|b")
        build(site, sys.argv[3])
    elif mode == "check_fuse":
        check_fuse(site)
    elif mode == "ranges":
        frame_check(site)
    elif mode == "prep_tiled":
        prep_tiled(site, sys.argv[3], sys.argv[4])
    elif mode == "receipt_tiled":
        receipt_tiled(site, sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")
    else:
        raise SystemExit(f"mode {mode}")
    print(f"[{now()}] done peak {peak_gb()} GB", flush=True)
