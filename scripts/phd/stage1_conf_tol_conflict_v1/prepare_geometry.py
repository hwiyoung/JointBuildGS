"""Step 1 (jointbuildgs:dev): LoD2 polygon-id mesh (exact reproduction of the diagnostic's
CityGML recovery with polygon identity added) and Existing-ALS 2.5D TIN meshes (nominal, +1.0 m).

Writes: inputs/lod2_polygons.npz, inputs/lod2_polygons.json, inputs/lod2_nominal_recovered.obj,
        inputs/als_tin_nominal.obj, inputs/als_tin_biased.obj, inputs/als_points.npz,
        provenance/geometry.json
"""
import collections
import datetime
import json
import xml.etree.ElementTree as etree

import numpy as np
from plyfile import PlyData
from scipy.spatial import Delaunay
from shapely.geometry import Polygon
from shapely.ops import triangulate

import common as cm

rc = cm.Receipt("prepare_geometry")
cm.INP.mkdir(parents=True, exist_ok=True)
cm.PROV.mkdir(parents=True, exist_ok=True)
GML = "{http://www.opengis.net/gml}"
ns = {"g": "http://www.opengis.net/gml", "b": "http://www.opengis.net/citygml/building/2.0"}
target = cm.CFG["scene"]["target_building"]

# --- identical bounding logic to the diagnostic's recover_mesh.py -------------------------
pv = PlyData.read(str(cm.SCENE / "lod2_pcd.ply"))["vertex"]
prior = np.column_stack([pv[k] for k in "xyz"]).astype(float)
ref = json.loads((cm.DIAG / "provenance/reference_frame.json").read_text())
shift = np.array(ref["base_to_canonical"]["shift"], float) + np.array([0, 0, cm.CFG["scene"]["z_offset_m"]])
assert np.allclose(shift, [-690955., -5336042., -604. + 45.66])
lo = prior.min(0) - shift - 1
hi = prior.max(0) - shift + 1

vertices, faces, labels, ids, poly_of_tri = [], [], [], [], []
polys = []  # one record per polygon that produced triangles
hole_count = repaired = 0
for path in sorted((cm.ART / cm.CFG["scene"]["citygml_relative"]).glob("*.gml")):
    for _, b in etree.iterparse(str(path), events=("end",)):
        if not b.tag.endswith("}Building"):
            continue
        bid = b.get(GML + "id")
        for surf in (x for x in b.iter() if x.tag.split("}")[-1] in ("RoofSurface", "WallSurface", "GroundSurface")):
            kind = surf.tag.split("}")[-1]
            for poly in surf.findall(".//g:Polygon", ns):
                ring = poly.find(".//{http://www.opengis.net/gml}exterior//{http://www.opengis.net/gml}posList")
                if ring is None:
                    continue
                xyz = np.fromstring(ring.text, sep=" ").reshape(-1, 3)
                if np.any(xyz.max(0) < lo) or np.any(xyz.min(0) > hi):
                    continue
                if np.linalg.norm(xyz[0] - xyz[-1]) < 1e-8:
                    xyz = xyz[:-1]
                if len(xyz) < 3:
                    continue
                origin = xyz[0]
                _, s, vh = np.linalg.svd(xyz - origin, full_matrices=False)
                if s[1] < 1e-8:
                    continue
                uv = (xyz - origin) @ vh[:2].T
                holes = []
                for hr in poly.findall(".//g:interior//g:posList", ns):
                    h = np.fromstring(hr.text, sep=" ").reshape(-1, 3)
                    holes.append((h - origin) @ vh[:2].T)
                hole_count += len(holes)
                p = Polygon(uv, holes)
                if not p.is_valid:
                    p = p.buffer(0)
                    repaired += 1
                normal = np.sum(np.cross(xyz, np.roll(xyz, -1, axis=0)), axis=0)
                n_tri = 0
                for tri in triangulate(p):
                    if not p.covers(tri):
                        continue
                    q = np.array(tri.exterior.coords)[:3] @ vh[:2] + origin
                    if np.dot(np.cross(q[1] - q[0], q[2] - q[0]), normal) < 0:
                        q = q[[0, 2, 1]]
                    start = len(vertices)
                    vertices.extend(q)
                    faces.append([start, start + 1, start + 2])
                    labels.append(kind)
                    ids.append(bid)
                    poly_of_tri.append(len(polys))
                    n_tri += 1
                if n_tri == 0:
                    continue
                nrm = normal / max(np.linalg.norm(normal), 1e-12)
                polys.append({
                    "poly_index": len(polys), "polygon_gml_id": poly.get(GML + "id"), "surface_gml_id": surf.get(GML + "id"),
                    "building_id": bid, "citygml_type": kind, "normal": nrm.tolist(), "area_m2": float(p.area),
                    "n_triangles": n_tri, "ring_global": xyz.tolist(), "n_holes": len(holes)})
        b.clear()

vertices = np.array(vertices)
faces = np.array(faces, dtype=np.int32)
labels = np.array(labels)
ids = np.array(ids)
poly_of_tri = np.array(poly_of_tri, dtype=np.int32)

# --- exact-reproduction check against the diagnostic's recovered mesh ----------------------
cand = np.load(cm.DIAG / "provenance/mesh_recovery_candidate.npz")
orig = np.load(cm.DIAG / "provenance/original_mesh.npz")
assert np.array_equal(cand["faces"], faces), "face topology differs from diagnostic recovery"
assert np.array_equal(cand["vertices_global"], vertices), "vertex coordinates differ from diagnostic recovery"
assert np.array_equal(orig["labels"], labels) and np.array_equal(orig["building_ids"], ids)
target_face_mask = ids == target
assert np.array_equal(orig["target_face_mask"], target_face_mask)
vertices_local = vertices + shift

# --- region class of every polygon (rule: ground if GroundSurface; roof if |n_z|>0.2; else wall)
for p in polys:
    p["is_target"] = p["building_id"] == target
    if p["citygml_type"] == "GroundSurface":
        p["region"] = "ground"
    elif abs(p["normal"][2]) > cm.C["roof_abs_nz_min"]:
        p["region"] = "roof"
    else:
        p["region"] = "wall"
    ring = np.array(p["ring_global"]) + shift
    p["ring_local_xy"] = np.round(ring[:, :2], 3).tolist()
    p["z_local_mean"] = float(ring[:, 2].mean())
    del p["ring_global"]
poly_region_code = np.array([{"roof": cm.R_ROOF, "wall": cm.R_WALL, "ground": cm.R_GROUND}[p["region"]] if p["is_target"] else cm.R_OTHER
                             for p in polys], np.uint8)
np.savez(cm.INP / "lod2_polygons.npz", vertices_local=vertices_local, vertices_global=vertices, faces=faces,
         poly_of_tri=poly_of_tri, poly_region_code=poly_region_code, labels=labels, building_ids=ids,
         target_face_mask=target_face_mask, shift=shift)
tv = vertices_local[faces[target_face_mask]].reshape(-1, 3)
tlo, thi = tv.min(0), tv.max(0)
# context polygons: any building whose XY bbox intersects the ALS crop rectangle
margin = cm.C["als_crop_margin_m"]
crop_lo = tlo[:2] - margin
crop_hi = thi[:2] + margin
for p in polys:
    r = np.array(p["ring_local_xy"])
    p["in_crop"] = bool((r.min(0) <= crop_hi).all() and (r.max(0) >= crop_lo).all())
cm.write_json(cm.INP / "lod2_polygons.json", {
    "target_building": target, "shift_global_to_local": shift.tolist(), "target_bbox_local": [tlo.tolist(), thi.tolist()],
    "als_crop_local_xy": [crop_lo.tolist(), crop_hi.tolist()],
    "polygons": [p for p in polys if p["is_target"] or p["in_crop"]],
    "n_polygons_total": len(polys)})

# nominal recovered OBJ in global coordinates, same writer format as the diagnostic's lod2_biased.obj
with (cm.INP / "lod2_nominal_recovered.obj").open("w") as o:
    for vv in vertices:
        o.write("v " + " ".join(f"{x:.9f}" for x in vv) + "\n")
    for ff in faces:
        o.write("f " + " ".join(str(int(x) + 1) for x in ff) + "\n")

# --- Existing ALS crop -> 2.5D TIN ---------------------------------------------------------
import laspy
g_lo = crop_lo - shift[:2]
g_hi = crop_hi - shift[:2]
pts, cls, tiles_used, gps = [], [], [], []
for rel in cm.CFG["scene"]["als_tiles_relative"]:
    path = cm.ART / rel
    with laspy.open(str(path)) as f:
        h = f.header
        if h.maxs[0] < g_lo[0] or h.mins[0] > g_hi[0] or h.maxs[1] < g_lo[1] or h.mins[1] > g_hi[1]:
            continue
    las = laspy.read(str(path))
    x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
    c = np.asarray(las.classification)
    m = (x >= g_lo[0]) & (x <= g_hi[0]) & (y >= g_lo[1]) & (y <= g_hi[1])
    pts.append(np.column_stack([x[m], y[m], z[m]]))
    cls.append(c[m])
    gps.append(np.asarray(las.gps_time)[m])
    tiles_used.append({"path": rel, "sha256": cm.sha256_file(path), "points_in_crop": int(m.sum()),
                       "las_version": str(las.header.version), "point_format": int(las.header.point_format.id),
                       "gps_time_type": int(las.header.global_encoding.gps_time_type)})
pts = np.concatenate(pts)
cls = np.concatenate(cls)
gps = np.concatenate(gps)
class_counts = collections.Counter(cls.tolist())
keep = np.isin(cls, cm.C["als_classes"])
P = pts[keep]
Pc = cls[keep]
t0 = float(gps.min()) + 1e9  # adjusted standard GPS time
t1 = float(gps.max()) + 1e9
epoch = datetime.datetime(1980, 1, 6)
# Delaunay on centred XY: qhull's precision tolerance scales with coordinate magnitude, and
# raw EPSG:25832 values (~5e6 m) make it drop most points as 'coplanar'.
xy_centre = P[:, :2].mean(0)
tri = Delaunay(P[:, :2] - xy_centre)
simp = tri.simplices.astype(np.int32)
assert len(tri.coplanar) < 0.01 * len(P), f"qhull dropped {len(tri.coplanar)} points"

used = np.zeros(len(P), bool)
used[np.unique(simp)] = True
# orient triangles counter-clockwise in XY so the upward normal is consistent
a, b, c_ = P[simp[:, 0]], P[simp[:, 1]], P[simp[:, 2]]
cross = (b[:, 0] - a[:, 0]) * (c_[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c_[:, 0] - a[:, 0])
flip = cross < 0
simp[flip] = simp[flip][:, [0, 2, 1]]


def write_obj(path, V, F):
    with open(path, "w") as o:
        for vv in V:
            o.write("v " + " ".join(f"{x:.9f}" for x in vv) + "\n")
        for ff in F:
            o.write("f " + " ".join(str(int(x) + 1) for x in ff) + "\n")


write_obj(cm.INP / "als_tin_nominal.obj", P, simp)
Pb = P.copy()
Pb[:, 2] += cm.C["bias_m"]
write_obj(cm.INP / "als_tin_biased.obj", Pb, simp)
np.savez(cm.INP / "als_points.npz", xyz_global=P, xyz_local=P + shift, classification=Pc, in_tin=used,
         triangles=simp, shift=shift)
edge = np.linalg.norm(np.stack([a - b, b - c_, c_ - a])[:, :, :2], axis=2).max(0)
area = (crop_hi - crop_lo).prod()
geom = {
    "task_id": cm.CFG["task_id"], "scientific_verdict": None,
    "lod2": {"n_polygons": len(polys), "n_triangles": int(len(faces)), "n_buildings": int(len(set(ids.tolist()))),
             "interior_rings": hole_count, "repaired_polygons": repaired,
             "target_polygons": {k: int(v) for k, v in collections.Counter(p["region"] for p in polys if p["is_target"]).items()},
             "target_citygml_types": {k: int(v) for k, v in collections.Counter(p["citygml_type"] for p in polys if p["is_target"]).items()},
             "exact_reproduction_of_diagnostic_recovery": True,
             "target_bbox_local": [tlo.tolist(), thi.tolist()]},
    "als": {"tiles": tiles_used, "crop_local_xy": [crop_lo.tolist(), crop_hi.tolist()], "crop_global_xy": [g_lo.tolist(), g_hi.tolist()],
            "margin_m": margin, "class_counts_in_crop": {str(k): int(v) for k, v in sorted(class_counts.items())},
            "classes_used": cm.C["als_classes"], "n_points_used": int(len(P)), "n_points_in_tin": int(used.sum()),
            "density_pts_per_m2_used": float(len(P) / area), "n_qhull_coplanar_dropped": int(len(tri.coplanar)), "delaunay_note": "scipy.spatial.Delaunay on mean-centred XY (qhull default options)",
            "n_triangles": int(len(simp)),
            "max_edge_xy_quantiles_m": np.quantile(edge, [0.5, 0.9, 0.99, 1.0]).tolist(),
            "gps_time_adjusted_standard": bool(tiles_used[0]["gps_time_type"] == 1),
            "acquisition_utc_from_gps_time": [(epoch + datetime.timedelta(seconds=t0)).isoformat(), (epoch + datetime.timedelta(seconds=t1)).isoformat()],
            "height_datum_note": "ALS z treated like CityGML z (orthometric, DHHN); local z = z + shift_z (-604) + z_offset 45.66, identical to LoD2 path",
            "bias_condition": f"all crop points z + {cm.C['bias_m']} m, same triangulation",
            "substitute_used": False,
            "wall_note": "2.5D TIN has no walls; steep bridging triangles between roof and ground points stand in for walls"},
}
cm.write_json(cm.PROV / "geometry.json", geom)
print(json.dumps(geom, indent=1)[:3000])
rc.write()
