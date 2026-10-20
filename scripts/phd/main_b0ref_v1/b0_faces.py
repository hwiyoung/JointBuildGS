"""PHD-MAIN-B0REF-v1 prep: the target building's LoD2 faces and the figure face, from the LoD2 and the evaluation range ONLY (no point
cloud is read; 9.1-6 of the request). (jointbuildgs:dev, CPU)

  python b0_faces.py   -> /b0/prep/faces.json

Per face: ext, kind, outward normal, compass direction, area (table, sampled), area in the evaluation range, area of the selection
space in the range (walls: lower edge + 0.5 m to upper edge - 0.5 m), lowest and highest z. The figure-1 face = the target-building
wall face with the largest area in the evaluation range. scientific_verdict: null."""
import numpy as np

from b0_common import B0, BLD, box_def, compass, face_area_in_space, jdump, lod2_faces, now


def main():
    rows = []
    for f in lod2_faces():
        a = face_area_in_space(f)
        dname, az = compass(f["normal"])
        rows.append(dict(ext=f["ext"], kind=f["kind"], type=f["type"], gml=f["gml"], normal=[round(float(x), 4) for x in f["normal"]],
                         facing=dname, azimuth_deg=round(az, 1), area_table_m2=round(f["area_table_m2"], 2), cut=f["cut"],
                         normal_flipped_to_outward=f["flipped"], triangles=int(len(f["tris"])), **{k: round(v, 3) for k, v in a.items()}))
    walls = [r for r in rows if r["kind"] == 2]
    fig = max(walls, key=lambda r: r["area_face_in_eval_m2"])
    out = dict(building=BLD, box=box_def(), faces=rows, figure1_face_ext=fig["ext"],
               figure1_rule="the target-building wall face with the largest area_face_in_eval_m2",
               totals=dict(wall_area_in_eval_m2=round(sum(r["area_face_in_eval_m2"] for r in walls), 2),
                           wall_space_area_in_eval_m2=round(sum(r["area_space_in_eval_m2"] for r in walls), 2),
                           roof_area_in_eval_m2=round(sum(r["area_face_in_eval_m2"] for r in rows if r["kind"] == 1), 2)),
               made=now(), scientific_verdict=None)
    jdump(B0 / "prep/faces.json", out)
    for r in sorted(rows, key=lambda r: (r["kind"], -r["area_face_in_eval_m2"])):
        print(r["ext"], r["type"], r["facing"], r["azimuth_deg"], r["area_table_m2"], r["area_face_m2"], r["area_face_in_eval_m2"],
              r["area_space_in_eval_m2"], r.get("z_min"), r.get("z_max"), "flip" if r["normal_flipped_to_outward"] else "")
    print("figure face", fig["ext"], out["totals"])


if __name__ == "__main__":
    main()
