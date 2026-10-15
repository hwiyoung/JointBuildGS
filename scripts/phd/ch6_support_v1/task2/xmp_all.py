"""Read DJI XMP + EXIF time of every JPEG member of Images.zip (first 128 KB of each member only).
Usage: python3 -I xmp_all.py <Images.zip> <out.json>"""
import json, re, sys, zipfile, collections, statistics, time
t0 = time.time()
z = zipfile.ZipFile(sys.argv[1])
keys = ["RelativeAltitude", "AbsoluteAltitude", "GimbalPitchDegree", "GimbalYawDegree", "UTCAtExposure", "RtkFlag", "RtkStdLon", "RtkStdLat",
        "RtkStdHgt", "GpsStatus", "AltitudeType", "LRFTargetDistance", "ShutterType", "DroneModel", "ProductName", "CalibratedFocalLength", "DewarpFlag"]
recs = {}
comp = collections.Counter()
for zi in z.infolist():
    if not zi.filename.lower().endswith(".jpg"):
        continue
    comp[zi.compress_type] += 1
    with z.open(zi) as fh:
        head = fh.read(131072)
    m = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", head, re.S)
    d = {}
    if m:
        for k, v in re.findall(rb'drone-dji:([A-Za-z]+)="([^"]*)"', m.group(0)):
            if k.decode() in keys:
                d[k.decode()] = v.decode()
        cd = re.search(rb'xmp:CreateDate="([^"]*)"', m.group(0))
        d["CreateDate"] = cd.group(1).decode() if cd else None
    recs[zi.filename.split("/")[-1]] = d
def f(x):
    try:
        return float(x)
    except Exception:
        return None
rel = [f(r.get("RelativeAltitude")) for r in recs.values()]
pit = [f(r.get("GimbalPitchDegree")) for r in recs.values()]
summary = dict(n=len(recs), zip_compress_types={str(k): v for k, v in comp.items()},
               gps_status=collections.Counter(r.get("GpsStatus") for r in recs.values()),
               rtk_flag=collections.Counter(r.get("RtkFlag") for r in recs.values()),
               altitude_type=collections.Counter(r.get("AltitudeType") for r in recs.values()),
               shutter=collections.Counter(r.get("ShutterType") for r in recs.values()),
               drone=collections.Counter(r.get("DroneModel") for r in recs.values()),
               product=collections.Counter(r.get("ProductName") for r in recs.values()),
               relative_altitude_rounded_5m=dict(sorted(collections.Counter(round(x / 5) * 5 for x in rel if x is not None).items())),
               gimbal_pitch_rounded_5deg=dict(sorted(collections.Counter(round(x / 5) * 5 for x in pit if x is not None).items())),
               rtk_std_m=dict(lon_median=statistics.median(f(r["RtkStdLon"]) for r in recs.values() if r.get("RtkStdLon")),
                              lat_median=statistics.median(f(r["RtkStdLat"]) for r in recs.values() if r.get("RtkStdLat")),
                              hgt_median=statistics.median(f(r["RtkStdHgt"]) for r in recs.values() if r.get("RtkStdHgt")),
                              hgt_max=max(f(r["RtkStdHgt"]) for r in recs.values() if r.get("RtkStdHgt"))),
               utc_first=min(r["UTCAtExposure"] for r in recs.values() if r.get("UTCAtExposure")),
               utc_last=max(r["UTCAtExposure"] for r in recs.values() if r.get("UTCAtExposure")),
               createdate_first=min(r["CreateDate"] for r in recs.values() if r.get("CreateDate")),
               createdate_last=max(r["CreateDate"] for r in recs.values() if r.get("CreateDate")),
               seconds=round(time.time() - t0, 1))
# flight blocks: gaps > 120 s in file-name time
names = sorted(recs)
def ts(n):
    s = n.split("_")[1]
    return int(s[8:10]) * 3600 + int(s[10:12]) * 60 + int(s[12:14])
blocks = []; cur = [names[0]]
for a, b in zip(names, names[1:]):
    if ts(b) - ts(a) > 120:
        blocks.append(cur); cur = [b]
    else:
        cur.append(b)
blocks.append(cur)
summary["blocks_gap_120s"] = [dict(first=bl[0], last=bl[-1], n=len(bl),
                                   rel_alt_median=statistics.median([f(recs[x].get("RelativeAltitude")) for x in bl if recs[x].get("RelativeAltitude")]),
                                   pitch_median=statistics.median([f(recs[x].get("GimbalPitchDegree")) for x in bl if recs[x].get("GimbalPitchDegree")]))
                              for bl in blocks]
json.dump(dict(summary=summary, per_image=recs), open(sys.argv[2], "w"), indent=1, default=str)
print(json.dumps(summary, indent=1, default=str))
