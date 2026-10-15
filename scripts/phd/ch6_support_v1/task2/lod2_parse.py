"""Stream-parse the two Bavarian LoD2 CityGML tiles; per building: id, creationDate, generic attributes (building and
building parts), roofType, function, measuredHeight, GroundSurface footprint (XY, EPSG:25832). Then summarise attribute
distributions for (a) whole tiles, (b) buildings whose footprint intersects / is >= 50 % inside each region of regions_used.json.
Usage: python3 -I lod2_parse.py <lod2_dir> <regions_used.json> <out_dir>"""
import json, sys, time, collections
from pathlib import Path
from lxml import etree
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid
t0 = time.time()
lod2_dir, reg_path, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
NS = dict(gml="http://www.opengis.net/gml", bldg="http://www.opengis.net/citygml/building/1.0",
          gen="http://www.opengis.net/citygml/generics/1.0", core="http://www.opengis.net/citygml/1.0")
BLDG = "{%s}Building" % NS["bldg"]
KEYS = ["DatenquelleBodenhoehe", "DatenquelleDachhoehe", "DatenquelleLage", "Methode", "Grundrissaktualitaet",
        "Geometrietyp2DReferenz", "Gemeindeschluessel"]
def attrs_of(el):
    """generic attributes that are direct children of el"""
    d = {}
    for sa in el.findall("gen:stringAttribute", NS):
        v = sa.find("gen:value", NS)
        d[sa.get("name")] = v.text if v is not None else None
    cd = el.find("core:creationDate", NS)
    if cd is not None:
        d["creationDate"] = cd.text
    for tag in ("roofType", "function", "measuredHeight", "storeysAboveGround"):
        x = el.find("bldg:" + tag, NS)
        if x is not None:
            d[tag] = x.text
    return d
def ground_polys(el):
    polys = []
    for gs in el.iter("{%s}GroundSurface" % NS["bldg"]):
        for pl in gs.iter("{%s}posList" % NS["gml"]):
            # only exterior rings
            par = pl.getparent()
            while par is not None and par.tag not in ("{%s}exterior" % NS["gml"], "{%s}interior" % NS["gml"]):
                par = par.getparent()
            if par is None or par.tag.endswith("interior"):
                continue
            v = [float(x) for x in pl.text.split()]
            dim = int(pl.get("srsDimension", "3"))
            xy = [(v[i], v[i + 1]) for i in range(0, len(v), dim)]
            if len(xy) >= 4:
                polys.append(xy)
    return polys
blds, tiles = [], {}
for gml in sorted(lod2_dir.glob("*.gml")):
    t1 = time.time(); n = 0
    hdr = open(gml, "rb").read(4000).decode("utf-8", "ignore")
    srs = hdr.split('srsName="')[1].split('"')[0] if 'srsName="' in hdr else None
    for ev, el in etree.iterparse(str(gml), events=("end",), tag=BLDG, huge_tree=True):
        if el.getparent() is not None and el.getparent().tag == "{%s}cityObjectMember" % NS["core"]:
            rec = dict(id=el.get("{%s}id" % NS["gml"]), tile=gml.stem, attrs=attrs_of(el), parts=[])
            for bp in el.iter("{%s}BuildingPart" % NS["bldg"]):
                rec["parts"].append(dict(id=bp.get("{%s}id" % NS["gml"]), attrs=attrs_of(bp)))
            rec["footprint"] = ground_polys(el)
            blds.append(rec); n += 1
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
    tiles[gml.stem] = dict(buildings=n, srsName=srs, seconds=round(time.time() - t1, 1))
    print(gml.name, n, srs, round(time.time() - t1, 1), "s", flush=True)
# effective attribute (building level, else first part that has it)
def eff(rec, k):
    if k in rec["attrs"]:
        return rec["attrs"][k]
    vals = sorted({p["attrs"].get(k) for p in rec["parts"] if p["attrs"].get(k) is not None})
    return "|".join(vals) if vals else None
for r in blds:
    r["eff"] = {k: eff(r, k) for k in KEYS + ["creationDate", "roofType", "function", "measuredHeight"]}
    geoms = []
    for xy in r["footprint"]:
        g = Polygon(xy)
        if not g.is_valid:
            g = make_valid(g)
        geoms.append(g)
    r["_geom"] = unary_union(geoms) if geoms else None
    r["footprint_area_m2"] = r["_geom"].area if r["_geom"] is not None else 0.0
# duplicates across tiles (a building can appear in both tiles?)
ids = collections.Counter(r["id"] for r in blds)
dups = [k for k, c in ids.items() if c > 1]
reg = json.load(open(reg_path))
def dist(rs, k):
    c = collections.Counter(r["eff"][k] for r in rs)
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0]))))
def cdate_year(rs):
    c = collections.Counter((r["eff"]["creationDate"] or "None")[:4] for r in rs)
    return dict(sorted(c.items()))
summary = dict(tiles=tiles, n_buildings=len(blds), duplicate_ids_across_tiles=dups[:20], n_duplicates=len(dups),
               n_with_parts=sum(1 for r in blds if r["parts"]), no_footprint=sum(1 for r in blds if r["_geom"] is None))
uniq = {}
for r in blds:
    uniq.setdefault(r["id"], r)
U = list(uniq.values())
summary["whole_tiles"] = {k: dist(U, k) for k in ["creationDate", "Grundrissaktualitaet", "DatenquelleDachhoehe", "DatenquelleLage",
                                                   "DatenquelleBodenhoehe", "Methode", "Geometrietyp2DReferenz", "roofType"]}
summary["whole_tiles"]["creationDate_year"] = cdate_year(U)
regions = {}
for rid, rv in reg.items():
    P = Polygon(rv["polygon"])
    inter, half = [], []
    for r in U:
        g = r["_geom"]
        if g is None or not g.intersects(P):
            continue
        fr = g.intersection(P).area / max(g.area, 1e-9)
        inter.append((r, fr))
        if fr >= 0.5:
            half.append(r)
    regions[rid] = dict(area_m2=rv["area_m2"], n_intersecting=len(inter), n_half_inside=len(half),
                        ids_half_inside=sorted(r["id"] for r in half),
                        ids_partial=sorted(f'{r["id"]}({fr:.2f})' for r, fr in inter if fr < 0.5),
                        footprint_area_inside_m2=sum(r["_geom"].intersection(P).area for r, _ in inter),
                        dist_half_inside={k: dist(half, k) for k in ["creationDate", "Grundrissaktualitaet", "DatenquelleDachhoehe",
                                                                      "DatenquelleLage", "DatenquelleBodenhoehe", "Methode", "roofType"]})
summary["regions"] = regions
# union of the 4 boxes and of the 8 ranges
for name, keys in (("union_4_boxes", [k for k in reg if k.startswith("box_")]), ("union_8_ranges", [k for k in reg if k.startswith("range_")])):
    ids_ = sorted(set(i for k in keys for i in regions[k]["ids_half_inside"]))
    rs = [uniq[i] for i in ids_]
    summary[name] = dict(n_half_inside_any=len(rs), dist={k: dist(rs, k) for k in ["creationDate", "Grundrissaktualitaet", "DatenquelleDachhoehe",
                                                                                 "DatenquelleLage", "DatenquelleBodenhoehe", "Methode", "roofType"]})
# named buildings
for bid in ("DEBY_LOD2_4959323", "DEBY_LOD2_4959326", "DEBY_LOD2_4959460", "DEBY_LOD2_4906975", "DEBY_LOD2_108580335"):
    if bid in uniq:
        r = uniq[bid]
        summary.setdefault("named", {})[bid] = dict(eff=r["eff"], footprint_area_m2=round(r["footprint_area_m2"], 1), n_parts=len(r["parts"]),
                                                   part_attrs=[p["attrs"] for p in r["parts"]][:5])
summary["seconds"] = round(time.time() - t0, 1)
out.mkdir(parents=True, exist_ok=True)
json.dump(summary, open(out / "lod2_summary.json", "w"), indent=1, ensure_ascii=False)
with open(out / "lod2_buildings.csv", "w") as f:
    cols = ["id", "tile", "footprint_area_m2"] + KEYS + ["creationDate", "roofType", "function", "measuredHeight"]
    f.write(",".join(cols) + "\n")
    for r in U:
        f.write(",".join([r["id"], r["tile"], f'{r["footprint_area_m2"]:.1f}'] + [str(r["eff"][k]) for k in cols[3:]]) + "\n")
print(json.dumps({k: summary[k] for k in ("tiles", "n_buildings", "n_duplicates", "n_with_parts", "no_footprint", "seconds")}, indent=1))
# ---- footprints of buildings near the AOI (for the point-density scripts)
import numpy as np
allP = np.concatenate([np.asarray(v["polygon"]) for v in reg.values()])
x0, y0 = allP.min(0) - 20; x1, y1 = allP.max(0) + 20
fps = []
for r in U:
    g = r["_geom"]
    if g is None:
        continue
    bx = g.bounds
    if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1:
        continue
    fps.append(dict(id=r["id"], rings=r["footprint"]))
json.dump(dict(aoi_bbox=[float(x0), float(y0), float(x1), float(y1)], buildings=fps), open(out / "footprints_aoi.json", "w"))
print("footprints near AOI:", len(fps), [float(x0), float(y0), float(x1), float(y1)])
