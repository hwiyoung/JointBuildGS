"""Semantic seeding for textureless buildings (P2 implementation ①).

PROBLEM
-------
P0/P2 diagnostics showed the 8 "recovery" buildings are textureless: SfM/MVS
produces ~0 points inside their footprints, so a 2DGS model initialised from the
COLMAP sparse cloud has *no Gaussians to optimise* there — the surface can never
be recovered, regardless of the joint-optimisation losses.

This module generates Gaussian SEEDS for those buildings from SEMANTIC LABELS
ALONE (no reference geometry, no MVS depth), using the same multi-view semantic
visual-hull *carve* as the E-R3 recoverability diagnostic
(``scripts/evidence_and_attributes/population_analysis/er3_recoverability_diag.py``). The occupancy voxels
that carve produces ARE the seeds: each occupied voxel becomes one Gaussian seed
whose centre is the voxel centre, class is the dominant (roof/wall) label, and
colour is the scene mean. The seeds are concatenated onto the SfM init points
before the model is built (see ``train.py``).

SCOPE (P2 step ①)
-----------------
This produces seeds at *init only* — it answers "do seeds get created inside the
textureless footprints?". Depth precision (the carve columns are thick / depth-
ambiguous, hence E-R3 verdict "D") and training survival are step ②, not here.

FRAME (critical — must match the SfM/COLMAP frame so seeds land correctly)
-------------------------------------------------------------------------
GS-LOCAL = EPSG:25832 - SHIFT, SHIFT = world_offset = [690953, 5336071, 604]
(pure translation; the GS frame is ellipsoidal height). Therefore:

  * footprint xy (EPSG) -> local: ``xy - world_offset[:2]``
  * z is taken directly in the GS-local band ``[z_min, z_max]``. The geoid
    correction (45.7 m for E5 canonical) is ALREADY baked into the semantic labels
    (rendered with shift_z = 604 - 45.7 = 558.3) and into
    the band, which is why ``z_local = Hoehe_orthometric + geoid - 604`` holds.
    The default band [-55, 5] is retained as the semantic seed search band.

Because the carve projects voxels (GS-local) into the *training* COLMAP poses and
reads the geoid-fixed label there, each occupied voxel centre is already in the
SfM frame — seeds concatenate onto ``ds.points_xyz`` with NO transform.

The ``geoid`` raster (``de_bkg_gcg2016.tif``) is therefore NOT needed at seed time
when the band is supplied directly (the labels encode it); it is accepted only as
optional provenance / for a future per-building band derived from LoD2 heights.
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

import numpy as np

# Class ids shared with the engine (BG=0, Roof=1, Wall=2, Terrain=3).
ROOF_CODE_DEFAULT = 1
WALL_CODE_DEFAULT = 2
WORLD_OFFSET_DEFAULT = (690953.0, 5336071.0, 604.0)
SURFACE_SEED_SCHEMA = "jointbuildgs.s3ap.surface_seeds.v1"
SFM_INIT_OPACITY = 0.10
SEMANTIC_SEED_INIT_OPACITY = 0.25
SURFACE_SEED_INIT_OPACITY = 0.10


# ---------------------------------------------------------------------------
# camera adapter — reuse the *training* poses so the seed frame == SfM frame
# ---------------------------------------------------------------------------
@dataclass
class SeedCamera:
    name: str
    K: tuple              # (fx, fy, cx, cy) at native resolution
    R: np.ndarray         # (3,3) world->cam rotation (COLMAP w2c)
    t: np.ndarray         # (3,) world->cam translation
    W: int
    H: int


def cameras_from_frames(frames: Sequence) -> List[SeedCamera]:
    """Build the carve camera list from ``ColmapDataset.frames``.

    Uses each frame's *native* intrinsics/size (the geoid-fixed labels were
    rendered at native resolution, downscale=1.0). This guarantees the seed
    carve uses the identical poses the trainer uses.
    """
    cams: List[SeedCamera] = []
    for fr in frames:
        K = np.asarray(fr.K, dtype=np.float64)
        cams.append(SeedCamera(
            name=fr.name,
            K=(float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])),
            R=np.asarray(fr.R, dtype=np.float64),
            t=np.asarray(fr.t, dtype=np.float64).reshape(3),
            W=int(fr.width), H=int(fr.height),
        ))
    return cams


def cameras_from_colmap(colmap_dir: str | Path) -> List[SeedCamera]:
    """Standalone path (CLI / verification): load poses from a COLMAP sparse dir.

    Resolves ``sparse`` -> ``sparse/0`` like the dataloader.
    """
    from .colmap_io import read_cameras_bin, read_images_bin

    colmap_dir = Path(colmap_dir)
    if (colmap_dir / "0" / "cameras.bin").exists():
        colmap_dir = colmap_dir / "0"
    cams = read_cameras_bin(colmap_dir / "cameras.bin")
    imgs = read_images_bin(colmap_dir / "images.bin")
    out: List[SeedCamera] = []
    for im in imgs.values():
        cam = cams[im.camera_id]
        K = cam.K()
        out.append(SeedCamera(
            name=im.name,
            K=(float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])),
            R=im.R(), t=im.tvec.reshape(3),
            W=int(cam.width), H=int(cam.height),
        ))
    out.sort(key=lambda c: c.name)
    return out


# ---------------------------------------------------------------------------
# footprints (GeoJSON polygons or {id:[minx,miny,maxx,maxy]} bbox dict)
# ---------------------------------------------------------------------------
def _poly_bbox(coords) -> List[float]:
    xs = [c[0] for ring in coords for c in ring]
    ys = [c[1] for ring in coords for c in ring]
    return [min(xs), min(ys), max(xs), max(ys)]


def load_footprints(path: str | Path, id_field: str = "building_id") -> Dict[str, List[float]]:
    """Return {building_id: [minx, miny, maxx, maxy]} in the footprint CRS."""
    import json

    data = json.load(open(path))
    if isinstance(data, dict) and "features" not in data:
        return {str(k): list(map(float, v)) for k, v in data.items()}
    out: Dict[str, List[float]] = {}
    for ft in data.get("features", []):
        props = ft.get("properties", {}) or {}
        bid = props.get(id_field) or props.get("id") or props.get("name")
        if bid is None:
            continue
        g = ft.get("geometry", {}) or {}
        gt, co = g.get("type"), g.get("coordinates")
        if gt == "Polygon":
            bb = _poly_bbox(co)
        elif gt == "MultiPolygon":
            bb = _poly_bbox([r for poly in co for r in poly])
        else:
            continue
        # union per id so multi-part buildings (same id, several features) keep full extent
        bid = str(bid)
        if bid in out:
            o = out[bid]
            out[bid] = [min(o[0], bb[0]), min(o[1], bb[1]), max(o[2], bb[2]), max(o[3], bb[3])]
        else:
            out[bid] = bb
    return out


def match_building(bid: str, footprints: Dict[str, List[float]]) -> Optional[List[float]]:
    if bid in footprints:
        return footprints[bid]
    for k, v in footprints.items():
        if bid in k or k in bid:
            return v
    return None


# ---------------------------------------------------------------------------
# voxel grid + multi-view semantic carve  (adapted from er3_recoverability_diag)
# ---------------------------------------------------------------------------
def build_grid(bbox_local: Sequence[float], z_min: float, z_max: float, voxel: float):
    """Voxel centres (N,3) over (x,y) bbox x [z_min, z_max] in the LOCAL frame."""
    minx, miny, maxx, maxy = bbox_local
    xs = np.arange(minx, maxx + voxel, voxel)
    ys = np.arange(miny, maxy + voxel, voxel)
    zs = np.arange(z_min, z_max + voxel, voxel)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    V = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    return V


@dataclass
class SeedResult:
    xyz: np.ndarray            # (M,3) seed centres, GS-LOCAL frame (== SfM frame)
    rgb: np.ndarray            # (M,3) seed colours in [0,1]
    sem: np.ndarray            # (M,)  class id (roof_code / wall_code)
    per_building: Dict[str, dict]   # diagnostics per building
    init_opacity: Optional[np.ndarray] = None
    is_surface_seed: Optional[np.ndarray] = None
    metadata: Optional[dict] = None


@dataclass
class ConcatenatedSeeds:
    """Init arrays plus lineage attributes, with legacy three-value unpacking.

    ``xyz, rgb, sem = concat_seeds(...)`` remains valid.  New callers inspect
    ``init_opacity`` and ``is_surface_seed`` explicitly, avoiding a breaking
    change to the Phase-2 semantic-carve utilities.
    """

    xyz: np.ndarray
    rgb: np.ndarray
    sem: np.ndarray
    init_opacity: np.ndarray
    is_surface_seed: np.ndarray

    def __iter__(self) -> Iterator[np.ndarray]:
        yield self.xyz
        yield self.rgb
        yield self.sem


def _metadata_json_scalar(raw: np.ndarray, path: Path) -> dict:
    if not isinstance(raw, np.ndarray) or raw.shape != ():
        raise ValueError(f"{path}: metadata_json must be a scalar JSON string")
    value = raw.item()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        metadata = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: metadata_json is not valid JSON") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: metadata_json must decode to an object")
    return metadata


def _validate_surface_seed_metadata(metadata: dict, path: Path) -> None:
    required = {
        "schema": SURFACE_SEED_SCHEMA,
        "seed_type": "surface",
        "coordinate_frame": "GS-local",
        "crs": "EPSG:25832",
        "gt_used_for_seed_generation": False,
        "lod2_used_for_seed_generation": False,
        "als_used_for_seed_generation": False,
    }
    for key, expected in required.items():
        if metadata.get(key) != expected:
            raise ValueError(f"{path}: metadata {key!r} must equal {expected!r}")

    # Truth geometry is allowed in downstream score artifacts, never in this
    # init artifact.  Reject disguised side channels as well as the obvious
    # top-level names.  The three explicit false declarations above are the
    # only permitted truth-related metadata keys.
    declared_false = {
        "gt_used_for_seed_generation",
        "lod2_used_for_seed_generation",
        "als_used_for_seed_generation",
    }
    forbidden_tokens = ("ground_truth", "reference_roof", "lod2", "als")

    def walk(value, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                name = str(key).lower()
                full = f"{prefix}.{key}" if prefix else str(key)
                truth_named = (
                    name == "gt"
                    or name.startswith("gt_")
                    or name.endswith("_gt")
                    or any(token in name for token in forbidden_tokens)
                )
                if truth_named and key not in declared_false:
                    raise ValueError(
                        f"{path}: forbidden truth-geometry metadata field {full!r}"
                    )
                walk(child, full)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f"{prefix}[{index}]")

    walk(metadata)


def load_surface_seed_npz(path: str | Path) -> SeedResult:
    """Load a strict S3-A-prime seed-surface artifact.

    Only the four contract arrays are accepted.  In particular, a score/LoD2/ALS array
    cannot hitchhike into model initialization.  Coordinates are already in
    the COLMAP/GS-local metric frame; no transform or GT-derived correction is
    applied here.
    """

    path = Path(path)
    with np.load(path, allow_pickle=False) as npz:
        required = {"xyz", "rgb", "sem", "metadata_json"}
        missing = sorted(required - set(npz.files))
        extra = sorted(set(npz.files) - required)
        if missing:
            raise ValueError(f"{path}: missing required arrays {missing}")
        if extra:
            raise ValueError(f"{path}: unexpected arrays {extra}")
        xyz = np.asarray(npz["xyz"])
        rgb = np.asarray(npz["rgb"])
        sem = np.asarray(npz["sem"])
        metadata = _metadata_json_scalar(npz["metadata_json"], path)

    if xyz.dtype != np.float32 or xyz.ndim != 2 or xyz.shape[1:] != (3,):
        raise ValueError(f"{path}: xyz must be float32 with shape (N,3)")
    if rgb.dtype != np.float32 or rgb.shape != xyz.shape:
        raise ValueError(f"{path}: rgb must be float32 with shape {xyz.shape}")
    if sem.dtype != np.int64 or sem.shape != (len(xyz),):
        raise ValueError(f"{path}: sem must be int64 with shape ({len(xyz)},)")
    if len(xyz) == 0:
        raise ValueError(f"{path}: a surface-seed artifact must contain at least one point")
    if not np.isfinite(xyz).all() or not np.isfinite(rgb).all():
        raise ValueError(f"{path}: xyz/rgb must be finite")
    if np.any((rgb < 0.0) | (rgb > 1.0)):
        raise ValueError(f"{path}: rgb must lie in [0,1]")
    if np.any((sem < 0) | (sem > 3)):
        raise ValueError(f"{path}: sem values must lie in [0,3]")
    _validate_surface_seed_metadata(metadata, path)
    return SeedResult(
        xyz=xyz.copy(),
        rgb=rgb.copy(),
        sem=sem.copy(),
        per_building=dict(metadata.get("per_building") or {}),
        init_opacity=np.full(len(xyz), SURFACE_SEED_INIT_OPACITY, np.float32),
        is_surface_seed=np.ones(len(xyz), dtype=np.bool_),
        metadata=metadata,
    )


def perturb_surface_seed(
    seeds: SeedResult,
    *,
    height_delta_m: float = 0.0,
    tilt_deg: float = 0.0,
    tilt_axis_xy: Optional[Sequence[float]] = None,
    tilt_pivot_xy: Optional[Sequence[float]] = None,
) -> SeedResult:
    """Apply the locked synthetic seed perturbation in GS-local metres.

    Height is applied first.  Tilt rotates about a horizontal axis through the
    supplied XY pivot and the perturbed seed median Z.  Only the external seed
    coordinates change; SfM points and every supervision map remain untouched.
    """

    xyz = np.asarray(seeds.xyz, dtype=np.float32).copy()
    delta = float(height_delta_m)
    angle = float(tilt_deg)
    if not np.isfinite(delta) or not np.isfinite(angle):
        raise ValueError("surface seed perturbation values must be finite")
    xyz[:, 2] += delta
    if abs(angle) > 0.0:
        if tilt_axis_xy is None or tilt_pivot_xy is None:
            raise ValueError("nonzero surface seed tilt requires axis_xy and pivot_xy")
        axis_xy = np.asarray(tilt_axis_xy, dtype=np.float64)
        pivot_xy = np.asarray(tilt_pivot_xy, dtype=np.float64)
        if axis_xy.shape != (2,) or pivot_xy.shape != (2,) or not (
            np.isfinite(axis_xy).all() and np.isfinite(pivot_xy).all()
        ):
            raise ValueError("surface seed tilt axis/pivot must be finite XY vectors")
        norm = float(np.linalg.norm(axis_xy))
        if norm <= 1e-12:
            raise ValueError("surface seed tilt axis must be nonzero")
        axis = np.array([axis_xy[0] / norm, axis_xy[1] / norm, 0.0], np.float64)
        radians = np.deg2rad(angle)
        skew = np.array(
            [[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]],
            dtype=np.float64,
        )
        rotation = (
            np.eye(3, dtype=np.float64)
            + np.sin(radians) * skew
            + (1.0 - np.cos(radians)) * (skew @ skew)
        )
        pivot = np.array([pivot_xy[0], pivot_xy[1], float(np.median(xyz[:, 2]))])
        xyz = ((xyz.astype(np.float64) - pivot) @ rotation.T + pivot).astype(np.float32)
    metadata = dict(seeds.metadata or {})
    metadata["applied_perturbation"] = {
        "height_delta_m": delta,
        "tilt_deg": angle,
        "tilt_axis_xy": None if tilt_axis_xy is None else list(map(float, tilt_axis_xy)),
        "tilt_pivot_xy": None if tilt_pivot_xy is None else list(map(float, tilt_pivot_xy)),
        "tilt_pivot_z_rule": "median seed z after height delta",
    }
    return SeedResult(
        xyz=xyz,
        rgb=seeds.rgb.copy(),
        sem=seeds.sem.copy(),
        per_building=dict(seeds.per_building),
        init_opacity=None if seeds.init_opacity is None else seeds.init_opacity.copy(),
        is_surface_seed=None if seeds.is_surface_seed is None else seeds.is_surface_seed.copy(),
        metadata=metadata,
    )


def _carve_one(cams: Sequence[SeedCamera], semantic_dir: Path, bbox_local: Sequence[float],
               z_min: float, z_max: float, voxel: float, tau: float, min_obs: int,
               roof_code: int, wall_code: int, _label_cache: dict):
    """Carve one building -> (seed_voxels (M,3) local, seed_class (M,), stats).

    For every voxel, project into every view and accumulate roof/wall votes.
    Occupied iff observed >= min_obs and max(roof_vote, wall_vote) >= tau.
    Class = whichever of roof/wall has more hits (ties -> roof).
    """
    from PIL import Image

    V = build_grid(bbox_local, z_min, z_max, voxel)
    obs = np.zeros(len(V), np.int32)
    roof = np.zeros(len(V), np.int32)
    wall = np.zeros(len(V), np.int32)

    for cam in cams:
        stem = os.path.splitext(os.path.basename(cam.name))[0]
        mask = _label_cache.get(stem, False)
        if mask is False:
            mpath = semantic_dir / (stem + ".png")
            if not mpath.exists():
                _label_cache[stem] = None
                mask = None
            else:
                try:
                    m = np.asarray(Image.open(mpath))
                except Exception:
                    m = None
                if m is not None and m.ndim == 3:
                    m = m[:, :, 0]
                _label_cache[stem] = m
                mask = m
        if mask is None:
            continue
        H, W = mask.shape[:2]
        fx, fy, cx, cy = cam.K
        # Rescale native intrinsics to the LABEL resolution. Labels are native today
        # (ratio 1.0 -> no-op), but if a label set is ever rendered downscaled, projecting
        # native-pixel u,v into a smaller mask would silently sample the wrong pixels.
        if W != cam.W or H != cam.H:
            sx, sy = W / cam.W, H / cam.H
            fx, cx, fy, cy = fx * sx, cx * sx, fy * sy, cy * sy
        Xc = (cam.R @ V.T) + cam.t.reshape(3, 1)        # world->cam: (3,N)
        z = Xc[2]
        front = z > 1e-6
        u = np.empty_like(z)
        v = np.empty_like(z)
        u[front] = fx * Xc[0, front] / z[front] + cx
        v[front] = fy * Xc[1, front] / z[front] + cy
        inb = front & (u >= 0) & (u < W) & (v >= 0) & (v < H)
        idx = np.where(inb)[0]
        if idx.size == 0:
            continue
        lab = mask[v[idx].astype(np.int32), u[idx].astype(np.int32)]
        obs[idx] += 1
        roof_hit = idx[lab == roof_code]
        if roof_hit.size:
            roof[roof_hit] += 1
        wall_hit = idx[lab == wall_code]
        if wall_hit.size:
            wall[wall_hit] += 1

    with np.errstate(divide="ignore", invalid="ignore"):
        denom = np.maximum(obs, 1)
        roof_vote = np.where(obs >= min_obs, roof / denom, 0.0)
        wall_vote = np.where(obs >= min_obs, wall / denom, 0.0)
    occ = (obs >= min_obs) & ((roof_vote >= tau) | (wall_vote >= tau))
    sel = np.where(occ)[0]
    cls = np.where(roof[sel] >= wall[sel], roof_code, wall_code).astype(np.int64)
    stats = dict(n_seed=int(occ.sum()),
                 n_roof=int((cls == roof_code).sum()),
                 n_wall=int((cls == wall_code).sum()),
                 n_voxels_grid=int(len(V)))
    return V[sel], cls, stats


def build_semantic_seeds(
    cameras: Sequence[SeedCamera],
    semantic_dir: str | Path,
    footprints_path: str | Path,
    buildings: Sequence[str],
    scene_rgb,
    id_field: str = "building_id",
    world_offset: Sequence[float] = WORLD_OFFSET_DEFAULT,
    z_min: float = -55.0,
    z_max: float = 5.0,
    bands: Optional[Dict[str, Sequence[float]]] = None,
    voxel: float = 1.0,
    tau: float = 0.6,
    min_obs: int = 5,
    roof_code: int = ROOF_CODE_DEFAULT,
    wall_code: int = WALL_CODE_DEFAULT,
    max_seeds_per_building: int = 0,
    geoid: Optional[str] = None,   # provenance only; labels already encode geoid
    verbose: bool = True,
) -> SeedResult:
    """Carve semantic seeds for ``buildings`` and return them in the GS-local frame.

    Args mirror the E-R3 carve. ``scene_rgb`` (3,) in [0,1] colours all seeds
    (task: colour = scene mean). ``max_seeds_per_building`` > 0 subsamples each
    building's seeds (stride) to cap M; 0 keeps all (one seed per occupied voxel).
    """
    semantic_dir = Path(semantic_dir)
    footprints = load_footprints(footprints_path, id_field)
    offset = np.asarray(world_offset, dtype=np.float64)
    scene_rgb = np.asarray(scene_rgb, dtype=np.float32).reshape(3)

    label_cache: dict = {}    # stem -> mask | None (shared across buildings)
    all_xyz: List[np.ndarray] = []
    all_sem: List[np.ndarray] = []
    per_building: Dict[str, dict] = {}

    for bid in buildings:
        bbox = match_building(bid, footprints)
        if bbox is None:
            per_building[bid] = dict(n_seed=0, reason="no footprint")
            if verbose:
                print(f"[seed] {bid}: no footprint -> 0 seeds")
            continue
        bbox_local = [bbox[0] - offset[0], bbox[1] - offset[1],
                      bbox[2] - offset[0], bbox[3] - offset[1]]
        # P2 impl ②: per-building band overrides the global [z_min, z_max] when provided.
        if bands is not None and bid in bands:
            zmn, zmx = float(bands[bid][0]), float(bands[bid][1])
        else:
            zmn, zmx = z_min, z_max
        xyz, cls, stats = _carve_one(
            cameras, semantic_dir, bbox_local, zmn, zmx, voxel, tau, min_obs,
            roof_code, wall_code, label_cache)
        stats["band"] = [round(zmn, 2), round(zmx, 2)]
        if max_seeds_per_building and len(xyz) > max_seeds_per_building:
            step = int(np.ceil(len(xyz) / max_seeds_per_building))
            xyz, cls = xyz[::step], cls[::step]
            # recompute reported counts from the strided set so stats == what is emitted
            stats["n_before_subsample"] = stats["n_seed"]
            stats["n_seed"] = int(len(xyz))
            stats["n_roof"] = int((cls == roof_code).sum())
            stats["n_wall"] = int((cls == wall_code).sum())
        all_xyz.append(xyz)
        all_sem.append(cls)
        per_building[bid] = stats
        if verbose:
            print(f"[seed] {bid}: {stats['n_seed']} seeds "
                  f"(roof={stats['n_roof']} wall={stats['n_wall']})")

    if all_xyz:
        xyz = np.concatenate(all_xyz, axis=0).astype(np.float32)
        sem = np.concatenate(all_sem, axis=0).astype(np.int64)
    else:
        xyz = np.zeros((0, 3), np.float32)
        sem = np.zeros((0,), np.int64)
    rgb = np.broadcast_to(scene_rgb, (len(xyz), 3)).astype(np.float32).copy()
    return SeedResult(
        xyz=xyz,
        rgb=rgb,
        sem=sem,
        per_building=per_building,
        init_opacity=np.full(len(xyz), SEMANTIC_SEED_INIT_OPACITY, np.float32),
        is_surface_seed=np.zeros(len(xyz), dtype=np.bool_),
        metadata={"seed_type": "semantic_carve"},
    )


def concat_seeds(
    points_xyz: np.ndarray,
    points_rgb: np.ndarray,
    seeds: SeedResult,
    *,
    points_sem: Optional[np.ndarray] = None,
    points_init_opacity: Optional[np.ndarray] = None,
    points_surface_seed: Optional[np.ndarray] = None,
) -> ConcatenatedSeeds:
    """Concatenate existing init points and a seed batch without losing lineage."""
    n_sfm = len(points_xyz)
    if points_sem is None:
        points_sem = np.full(n_sfm, -1, np.int64)
    else:
        points_sem = np.asarray(points_sem)
        if points_sem.dtype != np.int64 or points_sem.shape != (n_sfm,):
            raise ValueError("points_sem must be int64 with shape (N,)")
    if points_init_opacity is None:
        points_init_opacity = np.full(n_sfm, SFM_INIT_OPACITY, np.float32)
    else:
        points_init_opacity = np.asarray(points_init_opacity, dtype=np.float32)
        if points_init_opacity.shape != (n_sfm,):
            raise ValueError("points_init_opacity must have shape (N,)")
    if points_surface_seed is None:
        points_surface_seed = np.zeros(n_sfm, dtype=np.bool_)
    else:
        points_surface_seed = np.asarray(points_surface_seed)
        if points_surface_seed.dtype != np.bool_ or points_surface_seed.shape != (n_sfm,):
            raise ValueError("points_surface_seed must be bool with shape (N,)")

    seed_opacity = seeds.init_opacity
    if seed_opacity is None:
        seed_opacity = np.full(len(seeds.xyz), SEMANTIC_SEED_INIT_OPACITY, np.float32)
    seed_surface = seeds.is_surface_seed
    if seed_surface is None:
        seed_surface = np.zeros(len(seeds.xyz), dtype=np.bool_)
    xyz = np.concatenate([points_xyz, seeds.xyz], axis=0).astype(np.float32)
    rgb = np.concatenate([points_rgb, seeds.rgb], axis=0).astype(np.float32)
    sem = np.concatenate([points_sem, seeds.sem]).astype(np.int64)
    opacity = np.concatenate([points_init_opacity, seed_opacity]).astype(np.float32)
    is_surface = np.concatenate([points_surface_seed, seed_surface]).astype(np.bool_)
    if not np.isfinite(opacity).all() or np.any((opacity <= 0.0) | (opacity >= 1.0)):
        raise ValueError("all initialization opacities must be finite and lie in (0,1)")
    return ConcatenatedSeeds(xyz, rgb, sem, opacity, is_surface)
