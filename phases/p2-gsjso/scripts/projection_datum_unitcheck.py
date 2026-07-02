#!/usr/bin/env python3
"""A0 unit check for the projection vertical-datum fix.

No reconstruction or retraining. Projects one orthometric ground point before
and after the fix into one near-nadir and one strong-oblique view, then writes
the numeric pixel delta and the image-projection impact inventory.
"""
from __future__ import annotations

import csv
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/workspace/JointBuildGS/phases/p2-gsjso/scripts")
from evidence_cards_v2 import (  # noqa: E402
    DATA,
    GEOJSON,
    REPO,
    clip_near,
    distort,
    gml_building,
    nadir_of,
    parse_cam_model,
    parse_cameras,
    to_cam,
)
from projection_datum import describe_projection_config, projection_geoid_m  # noqa: E402


RUN_ID = "20260702_A0_projection_fix"
OUT_CSV = REPO / "docs/projection_datum_unitcheck.csv"
OUT_MD = REPO / "docs/projection_datum_fix.md"
RUN_DIR = REPO / "runs" / RUN_ID
BUILDING = "4906972"


IMPACT_ROWS = [
    ("phases/p2-gsjso/scripts/projection_datum.py", "new shared datum utility; config-driven zeta for orthometric image projection"),
    ("configs/projection_datum.json", "config parameter for zeta; 45.7/48.0/A1-zeta are replaceable values"),
    ("phases/p2-gsjso/scripts/evidence_cards_v2.py", "card v2 LoD2/ALS/footprint projection, roof masks, view angle selection"),
    ("phases/p2-gsjso/scripts/evidence_cards.py", "legacy evidence card projection path"),
    ("phases/p2-gsjso/scripts/projection_gate.py", "historical retracted gate imports evidence_cards_v2 projection functions"),
    ("phases/p2-gsjso/scripts/projection_gate2.py", "wide-search projection gate imports evidence_cards_v2 projection functions"),
    ("phases/p2-gsjso/scripts/gate_diag.py", "clean visual diagnostic imports evidence_cards_v2 projection functions"),
    ("phases/p2-gsjso/scripts/population_aux_v3.py", "observation geometry projection plus camera-point vectors now use ellipsoidal point Z"),
    ("phases/p2-gsjso/scripts/texture_anchor_check.py", "texture anchor crops use population_aux_v3.project"),
    ("phases/p2-gsjso/scripts/add_lowtex_v4.py", "lowtex v4 uses texture_anchor_check/build_crop and population camera parsing"),
    ("phases/p2-gsjso/scripts/ztest.py", "diagnostic keeps explicit geoid_m=0 pre-fix simulation for old-vs-fix figures"),
    ("phases/p2-gsjso/scripts/zmultiview.py", "diagnostic keeps explicit geoid_m=0 pre-fix simulation for old-vs-fix figures"),
    ("phases/p2-gsjso/scripts/zfix_visual.py", "inherits ztest.proj_dz pre-fix simulation"),
    ("phases/p2-gsjso/scripts/zresolve.py", "inherits ztest.proj_dz pre-fix simulation"),
]


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception as exc:  # pragma: no cover - provenance best effort
        return f"unavailable: {exc}"


def footprints() -> dict[str, np.ndarray]:
    out = {}
    for f in json.load(open(GEOJSON))["features"]:
        bid = f["properties"]["building_id"].replace("DEBY_LOD2_", "")
        g = f["geometry"]
        ring = np.array(
            g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len),
            float,
        )
        if bid not in out or len(ring) > len(out[bid]):
            out[bid] = ring
    return out


def project_point(point_ortho: np.ndarray, cam, params: np.ndarray, sr: dict, geoid_m: float) -> np.ndarray:
    cc = clip_near(to_cam(point_ortho[None], cam, sr, geoid_m=geoid_m))
    if len(cc) == 0:
        return np.array([np.nan, np.nan])
    return distort(cc, params)[0]


def pick_views(point_ortho: np.ndarray, cams, params: np.ndarray, sr: dict, W: int, H: int):
    candidates = []
    for cam in cams:
        uv = project_point(point_ortho, cam, params, sr, projection_geoid_m())
        if not np.isfinite(uv).all() or not (0 <= uv[0] < W and 0 <= uv[1] < H):
            continue
        nad = nadir_of(cam, point_ortho, geoid_m=projection_geoid_m())
        candidates.append((nad, cam, uv))
    if not candidates:
        raise RuntimeError("no camera sees the unit-check point")
    near = min(candidates, key=lambda t: abs(t[0] - 5.0))
    strong_pool = [t for t in candidates if t[0] >= 45.0]
    strong = min(strong_pool, key=lambda t: abs(t[0] - 55.0)) if strong_pool else max(candidates, key=lambda t: t[0])
    return [("near_nadir", near), ("strong_oblique", strong)]


def write_versions() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            f"run_id: {RUN_ID}",
            f"git_head: {git_head()}",
            "command: python3 phases/p2-gsjso/scripts/projection_datum_unitcheck.py",
            f"projection_config: {describe_projection_config()}",
            f"python: {platform.python_version()}",
            f"numpy: {np.__version__}",
            "container: jointbuildgs-p0-tools:t0 or compatible; Docker --user required by task",
            "crs: geo EPSG:25832; OPF/COLMAP EPSG:32632 local with ellipsoidal Z",
            "reconstruction_or_retraining: none",
            "",
        ]
    )
    (RUN_DIR / "versions.txt").write_text(text)


def write_report(rows: list[dict[str, object]]) -> None:
    lines = [
        "# projection_datum_fix -- A0 projection-fix",
        "",
        "> Observe only. No reconstruction/retraining. Geo CRS EPSG:25832; OPF/COLMAP frame EPSG:32632 with ellipsoidal Z.",
        "",
        "## Config",
        "",
        f"- {describe_projection_config()}",
        "- Orthometric image-projection inputs add `orthometric_geoid_m` before the existing base_to_canonical shift.",
        "- Ellipsoidal inputs keep the historical `shift_z=-604` path by passing `input_datum=ellipsoidal`.",
        "- 3D/seed paths are not controlled by this A0 utility.",
        "",
        "## Unit Check",
        "",
        "| view_class | view_nadir_deg | view | pre_u | pre_v | post_u | post_v | du_px | dv_px | shift_px |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| {view_class} | {view_nadir_deg:.2f} | {view} | {pre_u:.2f} | {pre_v:.2f} | "
            "{post_u:.2f} | {post_v:.2f} | {du_px:.2f} | {dv_px:.2f} | {shift_px:.2f} |".format(**r)
        )
    lines.extend(
        [
            "",
            "Interpretation note: near-nadir can have small pixel movement, while oblique movement grows with the vertical datum correction. This is a unit verification of the code path, not a pass/fail judgment.",
            "",
            "## Image-Projection Impact Inventory",
            "",
            "| path | impact |",
            "|---|---|",
        ]
    )
    for path, impact in IMPACT_ROWS:
        lines.append(f"| `{path}` | {impact} |")
    lines.extend(
        [
            "",
            "## Missing External Spec",
            "",
            "- Root file `원격발주_투영fix·LS정합·재게이트·재계산체인_레시피감사_20260702.md` was not present in this checkout; this A0 follows `CLAUDE.md`, `docs/projection_geoid_rootcause.md`, and the retracted `docs/projection_gate.md` note.",
            "",
            "## 판정 필요 지점",
            "",
            "- A0 has no 합/불 판정 item; A1 must estimate zeta numerically and may update the config default.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n")


def main() -> None:
    sr = json.load(open(DATA / "work/opf/opf/scene_reference_frame.json"))["base_to_canonical"]
    W, H, params = parse_cam_model(DATA / "work/colmap/sparse/0/cameras.txt")
    cams = parse_cameras(DATA / "work/colmap/sparse/0/images.txt", sr)
    fp = footprints()
    gb = gml_building(BUILDING)
    if not gb or not gb["roof"] or not gb["wall"] or BUILDING not in fp:
        raise RuntimeError(f"missing GML/footprint for {BUILDING}")
    ring = fp[BUILDING]
    ground_z = float(np.vstack(gb["wall"] + gb["roof"])[:, 2].min())
    point = np.array([float(ring[:, 0].mean()), float(ring[:, 1].mean()), ground_z])
    zeta = projection_geoid_m()
    rows = []
    for view_class, (nadir, cam, _uv) in pick_views(point, cams, params, sr, W, H):
        pre = project_point(point, cam, params, sr, 0.0)
        post = project_point(point, cam, params, sr, zeta)
        delta = post - pre
        rows.append(
            {
                "building_id": f"DEBY_LOD2_{BUILDING}",
                "point_e": round(float(point[0]), 3),
                "point_n": round(float(point[1]), 3),
                "point_H_ortho": round(float(point[2]), 3),
                "geoid_m": round(float(zeta), 6),
                "view_class": view_class,
                "view_nadir_deg": round(float(nadir), 3),
                "view": cam.name,
                "pre_u": round(float(pre[0]), 3),
                "pre_v": round(float(pre[1]), 3),
                "post_u": round(float(post[0]), 3),
                "post_v": round(float(post[1]), 3),
                "du_px": round(float(delta[0]), 3),
                "dv_px": round(float(delta[1]), 3),
                "shift_px": round(float(math.hypot(delta[0], delta[1])), 3),
            }
        )
    with open(OUT_CSV, "w", newline="") as f:
        cols = list(rows[0].keys())
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    write_versions()
    write_report(rows)
    for r in rows:
        print(
            f"{r['view_class']} nadir={r['view_nadir_deg']:.2f} shift={r['shift_px']:.2f}px "
            f"pre=({r['pre_u']:.1f},{r['pre_v']:.1f}) post=({r['post_u']:.1f},{r['post_v']:.1f})"
        )
    print(f"[done] {OUT_CSV}")
    print(f"[done] {OUT_MD}")
    print(f"[done] {RUN_DIR / 'versions.txt'}")


if __name__ == "__main__":
    main()
