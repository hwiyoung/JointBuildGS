"""Extract per-building RoofSurface reference planes from the original CityGML LoD2
tiles (EPSG:25832, P0 raw — read-only) for the 199 target buildings."""
import json, os, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np

A = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
TILES = [A / "phase-payloads/p0-audit/data/raw/lod2/690_5334.gml",
         A / "phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"]
FP = A / ("phase-payloads/p2/c1_c2_shared_footprint_199_v3/"
          "P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson")
OUT = Path(os.environ.get("JBGS_GATE5_WORK", "/tmp/jbgs_gate5_work")) / "lod2_ref_planes.json"
ORIGIN = np.array([690700.0, 5335700.0, 0.0])
GML = "{http://www.opengis.net/gml}"
BLDG = "{http://www.opengis.net/citygml/building/1.0}"

targets = {f["properties"]["stable_id"] for f in json.load(open(FP))["features"]}
out = {}
for tile in TILES:
    for _, el in ET.iterparse(str(tile), events=("end",)):
        if el.tag != BLDG + "Building":
            continue
        bid = el.get(GML + "id")
        if bid in targets:
            planes = []
            for rs in el.iter(BLDG + "RoofSurface"):
                for pl in rs.iter(GML + "posList"):
                    v = np.array([float(x) for x in pl.text.split()]).reshape(-1, 3) - ORIGIN
                    if len(v) < 4:
                        continue
                    # Newell normal (upward)
                    n = np.zeros(3)
                    for i in range(len(v) - 1):
                        a, b = v[i], v[i + 1]
                        n += np.cross(a, b)
                    ln = np.linalg.norm(n)
                    if ln < 1e-9:
                        continue
                    n /= ln
                    if n[2] < 0:
                        n = -n
                    planes.append({"ring": [[round(float(x), 2), round(float(y), 2)] for x, y, _ in v],
                                   "normal": [round(float(c), 4) for c in n]})
            if planes:
                out[bid] = planes
        el.clear()
json.dump(out, open(OUT, "w"), separators=(",", ":"))
cnt = [len(v) for v in out.values()]
print(f"buildings {len(out)}/199, roof surfaces total {sum(cnt)}, max/bldg {max(cnt)}")
