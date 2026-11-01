"""Party-wall gap caps and probe faces (prior_propagation_v5, PHD-MAIN-PREP-DISCARD-RULE-v1).

Moved unchanged from the PHD-MAIN-PREP-MEASURE-v1 mesh script (step02_meshes.py, order 5.7 of that task): after the
overlapping parts of party walls are cut from both walls (faces.party_wall_overlaps / cut_triangles, r10), the open edges of
every cut region are closed by thin cap quads between the two wall planes (bottom edges left open; 2 mm overlap along the
edge and beyond both planes closes numerical seams), and the cut regions themselves are kept apart as probe faces
(render-only, to count rays that would enter a gap). scientific_verdict: null."""
import numpy as np

from . import faces as fc

CAP_BASE = 1_000_000


def caps_and_probes(polys, ov):
    """polys: list of dict(tris [k, 3, 3], optional tris_uncut, o, normal, gml) indexed by polygon id; ov: the overlaps of
    faces.party_wall_overlaps (dict a, b, frame, region, area, gap_max). Returns (caps [list of 3x3], probes [list of 3x3],
    cap records, overlap index of every cap triangle, overlap index of every probe triangle)."""
    caps, probes, cap_rec, cap_ov, probe_ov = [], [], [], [], []
    for k, r in enumerate(ov):
        A, B = polys[r["a"]], polys[r["b"]]
        zmin = min(A.get("tris_uncut", A["tris"])[..., 2].min(), B.get("tris_uncut", B["tris"])[..., 2].min())
        for g in getattr(r["region"], "geoms", [r["region"]]):
            if g.geom_type != "Polygon" or g.area < 1e-8:
                continue
            xy = np.asarray(g.exterior.coords)
            for piece in fc._no_holes(g):
                pxy = np.asarray(piece.exterior.coords)[:-1]
                for (i0, i1, i2) in fc.ear_clip(pxy):
                    for W in (A, B):
                        probes.append(fc.lift(pxy[[i0, i1, i2]], r["frame"], W["tris"][0, 0] if len(W["tris"]) else W["o"], W["normal"]))
                        probe_ov.append(k)
            n_edges = 0
            for i in range(len(xy) - 1):
                e = xy[i:i + 2]
                Pa = fc.lift(e, r["frame"], A["o"], A["normal"]); Pb = fc.lift(e, r["frame"], B["o"], B["normal"])
                if (Pa[:, 2].mean() - zmin) <= 0.05 and abs(Pa[0, 2] - Pa[1, 2]) < 0.05:
                    continue                                     # bottom edge: left open
                if np.linalg.norm(Pa[1] - Pa[0]) < 1e-4:
                    continue
                # 2 mm overlap along the edge and beyond both planes closes numerical seams with the roofs and walls
                u_ = (Pa[1] - Pa[0]) / np.linalg.norm(Pa[1] - Pa[0]); w_ = r["frame"][3]
                ext_ = 0.002
                Qa0, Qa1 = Pa[0] - ext_ * u_, Pa[1] + ext_ * u_; Qb0, Qb1 = Pb[0] - ext_ * u_, Pb[1] + ext_ * u_
                sgn = np.sign(np.dot(Pa[0] - Pb[0], w_)) or 1.0
                Qa0, Qa1 = Qa0 + sgn * ext_ * w_, Qa1 + sgn * ext_ * w_; Qb0, Qb1 = Qb0 - sgn * ext_ * w_, Qb1 - sgn * ext_ * w_
                caps.append(np.array([Qa0, Qa1, Qb1])); caps.append(np.array([Qa0, Qb1, Qb0])); cap_ov += [k, k]
                n_edges += 1
            cap_rec.append(dict(overlap=k, a=polys[r["a"]]["gml"], b=polys[r["b"]]["gml"], area_m2=r["area"], gap_max_m=r["gap_max"],
                                cap_edges=n_edges))
    return caps, probes, cap_rec, cap_ov, probe_ov
