"""Parse scene.obj into per-building GT face dicts.

Each building group in scene.obj is either:
  (v1) `building_NN_<type>`                                   — legacy grid scene
  (v2+) `<bag_name>_<type>`  e.g. `NL.IMBAG.Pand.0363...._gable` — natural block
Both are parsed. Non-matching groups (ground_plane, etc.) are skipped.

Output per building:
    {"building_id": int, "name": str, "type": str, "faces": [
        {"vertices": (Nv,3) ndarray, "material": "Roof"|"Wall"|"Ground"|"Terrain",
         "semantic_class": 1|2|3, "normal": (3,), "centroid": (3,), "area": float},
        ...
    ]}

Semantic class mapping (matching K=4 scheme):
    Roof->1  Wall->2  Ground->3  Terrain->3
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np


MATERIAL_TO_CLASS = {
    "Roof": 1,
    "Wall": 2,
    "Ground": 3,
    "Terrain": 3,
}

KNOWN_ROOF_TYPES = {"flat", "shed", "gable", "hip", "tri-slope", "complex"}


# Step 2-1 bug: cameras.bin were written in Blender world frame (axes swapped vs
# OBJ), while scene.obj was kept in COLMAP -Y-up frame. Trained primitives
# converged into the Blender frame (92% of them fall in the transformed scene
# bbox). To evaluate, transform OBJ → Blender: (x, y, z) → (x, -z, y).
def obj_to_primitive_frame(p: np.ndarray) -> np.ndarray:
    q = p.copy()
    q[..., 1] = -p[..., 2]
    q[..., 2] =  p[..., 1]
    return q


def _parse_face_token(tok: str) -> int:
    """f v/vt/vn or f v//vn or f v → return vertex index (1-based)."""
    return int(tok.split("/", 1)[0])


def parse_scene_obj(obj_path: str | Path, frame: str = "obj") -> Dict:
    """Return dict with keys: vertices (V,3), buildings (list of per-building dicts).

    frame: "obj" (default, for v2+ datasets where cameras.bin is correctly
           in OBJ/COLMAP frame). Use "primitive" only for legacy v1 checkpoints
           trained with the Step 2-1 camera frame bug (primitives ended up in
           Blender frame, so GT must be transformed to align).
    """
    lines = Path(obj_path).read_text().splitlines()
    verts: List[List[float]] = []
    buildings: List[Dict] = []
    cur_group = None
    cur_mat = None
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        head, *rest = ln.split()
        if head == "v":
            verts.append([float(x) for x in rest[:3]])
        elif head in ("g", "o"):
            name = rest[0] if rest else ""
            bid, bname, btype = None, name, None
            if name.startswith("building_"):
                # v1 legacy grid scene: building_NN_<type>
                parts = name.split("_")
                try:
                    bid = int(parts[1])
                    btype = "_".join(parts[2:]) if len(parts) >= 3 else "unknown"
                    bname = name
                except (ValueError, IndexError):
                    bid = None
            else:
                # v2 natural block: <bag_name>_<type>. Accept if final suffix is a known type
                parts = name.rsplit("_", 1)
                if len(parts) == 2 and parts[1] in KNOWN_ROOF_TYPES:
                    btype = parts[1]
                    bname = parts[0]
                    bid = len(buildings)  # sequential id
            if btype is not None:
                buildings.append({"building_id": bid, "name": bname, "type": btype,
                                  "faces": []})
                cur_group = buildings[-1]
            else:
                cur_group = None  # ground_plane or other
        elif head == "usemtl":
            cur_mat = rest[0] if rest else None
        elif head == "f":
            if cur_group is None or cur_mat is None:
                continue
            idxs = [_parse_face_token(t) - 1 for t in rest]  # 0-based
            vp = np.array([verts[i] for i in idxs], dtype=np.float64)
            if frame == "primitive":
                vp = obj_to_primitive_frame(vp)
            if vp.shape[0] < 3:
                continue
            # planar polygon: use Newell for normal
            n = _newell_normal(vp)
            nrm = np.linalg.norm(n)
            if nrm < 1e-10:
                continue
            n = n / nrm
            area = _polygon_area(vp, n)
            cls = MATERIAL_TO_CLASS.get(cur_mat, 0)
            cur_group["faces"].append({
                "vertex_indices": idxs,
                "vertices": vp,
                "material": cur_mat,
                "semantic_class": cls,
                "normal": n,
                "centroid": vp.mean(axis=0),
                "area": float(area),
            })
    V = np.array(verts, dtype=np.float64)
    if frame == "primitive":
        V = obj_to_primitive_frame(V)
    return {
        "vertices": V,
        "buildings": buildings,
        "frame": frame,
    }


def _newell_normal(poly: np.ndarray) -> np.ndarray:
    """Newell's method for planar polygon normal (non-unit)."""
    N = poly.shape[0]
    n = np.zeros(3)
    for i in range(N):
        a = poly[i]
        b = poly[(i + 1) % N]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return n


def _polygon_area(poly: np.ndarray, n: np.ndarray) -> float:
    """Signed area of planar polygon w.r.t. given unit normal n."""
    N = poly.shape[0]
    s = 0.0
    for i in range(N):
        s += np.dot(n, np.cross(poly[i], poly[(i + 1) % N]))
    return abs(s) * 0.5


def building_bboxes(gt: Dict, pad: float = 1.0):
    """Return (B,2,3) bbox [min, max] per building, padded."""
    bboxes = []
    for b in gt["buildings"]:
        vs = np.concatenate([f["vertices"] for f in b["faces"]], axis=0)
        mn = vs.min(axis=0) - pad
        mx = vs.max(axis=0) + pad
        bboxes.append((mn, mx))
    return bboxes


if __name__ == "__main__":
    import sys
    import json
    p = sys.argv[1] if len(sys.argv) > 1 else "results/phase2_synthesis/scene.obj"
    gt = parse_scene_obj(p)
    print(f"vertices={gt['vertices'].shape[0]} buildings={len(gt['buildings'])}")
    for b in gt["buildings"][:3]:
        print(f"  {b['name']} type={b['type']} faces={len(b['faces'])}")
        for f in b["faces"][:2]:
            print(f"    mat={f['material']} cls={f['semantic_class']} "
                  f"area={f['area']:.2f} normal={f['normal']}")
