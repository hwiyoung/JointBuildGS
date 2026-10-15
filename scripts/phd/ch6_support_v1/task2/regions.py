"""Build the region polygons (EPSG:25832) used for the data section: 8 search ranges, 4 experiment boxes (box = evaluation
range + band) and their 4 evaluation ranges. Sources (read-only):
  <PREP>/step01/ranges.json      search ranges (polygon_epsg25832)
  <PREP>/step06/box_ranges.json  boxes (polygon_epsg25832, eval_u/eval_v in the object frame)
Frame: configs/phd/main_prep_measure_v1/prep_v5.json  world_shift (690953, 5336071, 604), u axis 70 deg ccw from easting.
Usage: python3 -I regions.py <PREP> <out.json>"""
import json, sys, math
prep, out = sys.argv[1], sys.argv[2]
SHIFT = (690953.0, 5336071.0)
a = math.radians(70.0)
B = [[math.cos(a), math.sin(a)], [math.sin(a), -math.cos(a)]]
def uv_to_xy(u, v):            # common.uv_to_xy: uv @ basis
    return (u * B[0][0] + v * B[1][0] + SHIFT[0], u * B[0][1] + v * B[1][1] + SHIFT[1])
def area(P):
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2
R = json.load(open(f"{prep}/step01/ranges.json"))
BX = json.load(open(f"{prep}/step06/box_ranges.json"))
reg = {}
for rid in ("R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"):
    P = R[rid]["polygon_epsg25832"]
    reg[f"range_{rid}"] = dict(kind="search_range", polygon=P, area_m2=area(P), label=R[rid]["label"])
for bid in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
    b = BX[bid]
    P = b["polygon_epsg25832"]
    reg[f"box_{bid}"] = dict(kind="box", polygon=P, area_m2=area(P), label=b["label"], recorded_area_m2=b["area_m2"])
    (u0, u1), (v0, v1) = b["eval_u"], b["eval_v"]
    E = [uv_to_xy(u0, v0), uv_to_xy(u1, v0), uv_to_xy(u1, v1), uv_to_xy(u0, v1)]
    reg[f"eval_{bid}"] = dict(kind="evaluation_range", polygon=[list(p) for p in E], area_m2=area(E), recorded_area_m2=b["eval_area_m2"])
# check: recomputed box polygon from uv equals the stored one
for bid in ("B0_b10",):
    b = BX[bid]; (u0, u1), (v0, v1) = b["u_m"], b["v_m"]
    chk = uv_to_xy(u0, v0)
    print("frame check", bid, chk, b["polygon_epsg25832"][0])
json.dump(reg, open(out, "w"), indent=1)
for k, v in reg.items():
    print(k, round(v["area_m2"], 1), v.get("recorded_area_m2"))
