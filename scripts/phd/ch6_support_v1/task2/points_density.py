"""Stream a LAS/LAZ (or the GeoGS PLY GT) and report: header facts, GPS-time range (UTC), return / class statistics, and per
region (regions_used.json) the point count, density (points / polygon 2-D area), first-return density, density inside vs
outside LoD2 footprints, 0.5 m cell coverage; optionally a class-2 ground grid (ALS) for camera-height computation.
Points are used in their stored numeric coordinates (the main experiment uses ULS and images in the same numeric frame;
regions are EPSG:25832 numbers of that frame). Usage:
  python3 -I points_density.py <regions.json> <footprints_aoi.json> <out.json> <file> [<file> ...] [--ground <npz>] [--ply-shift dx,dy]
scientific_verdict: null"""
import json, sys, time, datetime
import numpy as np
from matplotlib.path import Path as MPath
args = sys.argv[1:]
ground_out = None; ply_shift = (0.0, 0.0)
if "--ground" in args:
    i = args.index("--ground"); ground_out = args[i + 1]; del args[i:i + 2]
if "--ply-shift" in args:
    i = args.index("--ply-shift"); ply_shift = tuple(float(v) for v in args[i + 1].split(",")); del args[i:i + 2]
reg_path, fp_path, out_path, files = args[0], args[1], args[2], args[3:]
t0 = time.time()
REG = json.load(open(reg_path)); FP = json.load(open(fp_path))
X0, Y0, X1, Y1 = FP["aoi_bbox"]
RES = 0.1
NX, NY = int(np.ceil((X1 - X0) / RES)), int(np.ceil((Y1 - Y0) / RES))
names = list(REG)
assert len(names) <= 32
regmask = np.zeros((NY, NX), np.uint32)
fpmask = np.zeros((NY, NX), bool)
def raster(poly, grid, value=None):
    P = np.asarray(poly, float)
    bx0, by0 = P.min(0); bx1, by1 = P.max(0)
    i0, i1 = max(int((bx0 - X0) / RES) - 1, 0), min(int((bx1 - X0) / RES) + 2, NX)
    j0, j1 = max(int((by0 - Y0) / RES) - 1, 0), min(int((by1 - Y0) / RES) + 2, NY)
    if i1 <= i0 or j1 <= j0:
        return
    xs = X0 + (np.arange(i0, i1) + 0.5) * RES; ys = Y0 + (np.arange(j0, j1) + 0.5) * RES
    gx, gy = np.meshgrid(xs, ys)
    inside = MPath(P).contains_points(np.stack([gx.ravel(), gy.ravel()], 1)).reshape(gx.shape)
    if value is None:
        grid[j0:j1, i0:i1] |= inside
    else:
        grid[j0:j1, i0:i1] |= (inside.astype(np.uint32) * np.uint32(value))
for k, n in enumerate(names):
    raster(REG[n]["polygon"], regmask, 1 << k)
for b in FP["buildings"]:
    for ring in b["rings"]:
        raster(ring, fpmask)
reg_cells = {n: int(((regmask >> k) & 1).sum()) for k, n in enumerate(names)}
reg_fp_cells = {n: int((((regmask >> k) & 1).astype(bool) & fpmask).sum()) for k, n in enumerate(names)}
GPS_EPOCH = datetime.datetime(1980, 1, 6)
def gps_to_utc(t_adj, adjusted=True, leap=18):
    s = t_adj + (1e9 if adjusted else 0)
    return (GPS_EPOCH + datetime.timedelta(seconds=float(s) - leap)).isoformat(timespec="seconds")
results = {}
for f in files:
    t1 = time.time()
    rec = dict(file=f)
    cnt = {n: np.zeros(8, np.int64) for n in names}   # all, first, single, last, in_fp, out_fp, class2, class6
    occ = np.zeros((int(np.ceil((Y1 - Y0) / 0.5)), int(np.ceil((X1 - X0) / 0.5))), np.int32)
    tmin, tmax = np.inf, -np.inf
    total = 0; cls_counts = {}; ret_counts = {}; nret_counts = {}
    has_time = has_cls = True
    gsum = gcnt = None
    if f.endswith(".ply"):
        with open(f, "rb") as fh:
            hdr = b""
            while b"end_header" not in hdr:
                hdr += fh.readline()
            off = len(hdr)
        nn = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        mm = np.memmap(f, dtype=np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1")]), mode="r", offset=off, shape=(nn,))
        # author local frame: E = x + 690953 + dx, N = y + 5336071 + dy (common frame = author + [2, -29, 0])
        def chunks():
            for s in range(0, nn, 5_000_000):
                c = mm[s:s + 5_000_000]
                yield dict(x=np.asarray(c["x"]) + 690953.0 + ply_shift[0], y=np.asarray(c["y"]) + 5336071.0 + ply_shift[1], z=np.asarray(c["z"]))
        rec["header"] = dict(format="PLY (Open3D)", points=nn, header=hdr.decode()[:400])
        has_time = has_cls = False
        it = chunks()
    else:
        import laspy
        fh = laspy.open(f, laz_backend=laspy.LazBackend.LazrsParallel)
        h = fh.header
        wkt = None; geokeys = None
        for v in h.vlrs:
            if "WktCoordinateSystem" in type(v).__name__:
                wkt = v.string[:400] if hasattr(v, "string") else str(v)[:400]
            if "GeoKeyDirectory" in type(v).__name__:
                geokeys = str(v.geo_keys)[:400] if hasattr(v, "geo_keys") else str(v)[:400]
        try:
            pc = h.parse_crs(); crs = (pc.to_string()[:200] if pc is not None else None)
        except Exception as e:
            crs = f"parse_crs failed: {e}"[:200]
        rec["header"] = dict(version=str(h.version), point_format=h.point_format.id, points=int(h.point_count), scales=list(map(float, h.scales)),
                             offsets=list(map(float, h.offsets)), mins=list(map(float, h.mins)), maxs=list(map(float, h.maxs)),
                             creation_date=str(h.creation_date), system_identifier=h.system_identifier, generating_software=h.generating_software,
                             global_encoding_gps_time_type=int(h.global_encoding.gps_time_type) if hasattr(h.global_encoding, "gps_time_type") else None,
                             vlrs=[type(v).__name__ + ":" + str(getattr(v, "description", ""))[:60] for v in h.vlrs], wkt=wkt, geokeys=geokeys, crs=crs,
                             evlrs=[type(v).__name__ for v in (h.evlrs or [])])
        dims = list(h.point_format.dimension_names)
        has_time = "gps_time" in dims
        adjusted = bool(rec["header"]["global_encoding_gps_time_type"])
        stem = f.split("/")[-1].split(".")[0].split("_")
        nominal = None
        if len(stem) == 2 and stem[0].isdigit():
            nominal = (float(stem[0]) * 1000, float(stem[1]) * 1000)
        if ground_out is not None:
            G0x, G0y, GR = 690000.0, 5335000.0, 2.0
            gsum = np.zeros((1000, 1000)); gcnt = np.zeros((1000, 1000), np.int64)
        def chunks():
            for pts in fh.chunk_iterator(8_000_000):
                d = dict(x=np.asarray(pts.x), y=np.asarray(pts.y), z=np.asarray(pts.z),
                         rn=np.asarray(pts.return_number), nr=np.asarray(pts.number_of_returns))
                if has_time:
                    d["t"] = np.asarray(pts.gps_time)
                d["c"] = np.asarray(pts.classification)
                if nominal is not None:                                  # LDBV tiles: keep the nominal 1 km tile (as the experiment)
                    d["nominal"] = (d["x"] >= nominal[0]) & (d["x"] < nominal[0] + 1000) & (d["y"] >= nominal[1]) & (d["y"] < nominal[1] + 1000)
                yield d
        it = chunks()
    n_nominal = 0
    for d in it:
        x, y = d["x"], d["y"]
        n = len(x); total += n
        if "t" in d and n:
            tmin = min(tmin, float(d["t"].min())); tmax = max(tmax, float(d["t"].max()))
        if "c" in d:
            u, c = np.unique(d["c"], return_counts=True)
            for a, b in zip(u, c):
                cls_counts[int(a)] = cls_counts.get(int(a), 0) + int(b)
            u, c = np.unique(d["rn"], return_counts=True)
            for a, b in zip(u, c):
                ret_counts[int(a)] = ret_counts.get(int(a), 0) + int(b)
            u, c = np.unique(d["nr"], return_counts=True)
            for a, b in zip(u, c):
                nret_counts[int(a)] = nret_counts.get(int(a), 0) + int(b)
        keep = np.ones(n, bool) if "nominal" not in d else d["nominal"]
        n_nominal += int(keep.sum())
        if gsum is not None:
            g = keep & (d["c"] == 2)
            gi = ((x[g] - 690000.0) / 2.0).astype(np.int64); gj = ((y[g] - 5335000.0) / 2.0).astype(np.int64)
            ok = (gi >= 0) & (gi < 1000) & (gj >= 0) & (gj < 1000)
            fi = gj[ok] * 1000 + gi[ok]; gsum += np.bincount(fi, weights=d["z"][g][ok], minlength=1000000).reshape(1000, 1000); gcnt += np.bincount(fi, minlength=1000000).reshape(1000, 1000)
        i = ((x - X0) / RES).astype(np.int64); j = ((y - Y0) / RES).astype(np.int64)
        inb = keep & (i >= 0) & (i < NX) & (j >= 0) & (j < NY)
        if not inb.any():
            continue
        ii, jj = i[inb], j[inb]
        bits = regmask[jj, ii]; fpi = fpmask[jj, ii]
        sel = bits != 0
        if not sel.any():
            continue
        bits, fpi, ii, jj = bits[sel], fpi[sel], ii[sel], jj[sel]
        rn = d["rn"][inb][sel] if "rn" in d else None; nr = d["nr"][inb][sel] if "nr" in d else None
        cl = d["c"][inb][sel] if "c" in d else None
        oi, oj = ii // 5, jj // 5
        occ += np.bincount(oj * occ.shape[1] + oi, minlength=occ.size).reshape(occ.shape).astype(np.int32)
        for k, nme in enumerate(names):
            m = ((bits >> k) & 1).astype(bool)
            if not m.any():
                continue
            v = cnt[nme]
            v[0] += int(m.sum())
            if rn is not None:
                v[1] += int((m & (rn == 1)).sum()); v[2] += int((m & (nr == 1)).sum()); v[3] += int((m & (rn == nr)).sum())
            v[4] += int((m & fpi).sum()); v[5] += int((m & ~fpi).sum())
            if cl is not None:
                v[6] += int((m & (cl == 2)).sum()); v[7] += int((m & (cl == 6)).sum())
    rec["total_points_read"] = total
    rec["points_in_nominal_tile"] = n_nominal
    if np.isfinite(tmin):
        adjusted = rec["header"].get("global_encoding_gps_time_type", 1)
        rec["gps_time"] = dict(min=tmin, max=tmax, adjusted_standard=bool(adjusted), utc_min=gps_to_utc(tmin, bool(adjusted)), utc_max=gps_to_utc(tmax, bool(adjusted)),
                               note="UTC = GPS epoch 1980-01-06 + (t + 1e9 if adjusted) - 18 leap seconds")
    rec["classification_counts"] = dict(sorted(cls_counts.items())) if cls_counts else None
    rec["return_number_counts"] = dict(sorted(ret_counts.items())) if ret_counts else None
    rec["number_of_returns_counts"] = dict(sorted(nret_counts.items())) if nret_counts else None
    regs = {}
    cl_present = bool(cls_counts) and not (len(cls_counts) == 1 and 0 in cls_counts)
    for k, nme in enumerate(names):
        v = cnt[nme]; A = REG[nme]["area_m2"]
        cells_r = reg_cells[nme] * RES * RES; cells_fp = reg_fp_cells[nme] * RES * RES
        m05 = ((regmask >> k) & 1)[2::5, 2::5][:occ.shape[0], :occ.shape[1]].astype(bool)
        cov = float((occ[:m05.shape[0], :m05.shape[1]][m05] > 0).mean()) if m05.any() else None
        regs[nme] = dict(area_polygon_m2=round(A, 1), area_raster_m2=round(cells_r, 1), footprint_area_m2=round(cells_fp, 1),
                         points=int(v[0]), density_all_per_m2=round(v[0] / A, 1),
                         density_first_returns_per_m2=round(v[1] / A, 1) if v[1] else None,
                         share_single_return=round(v[2] / v[0], 4) if v[0] and v[2] else None,
                         density_inside_lod2_footprints_per_m2=round(v[4] / cells_fp, 1) if cells_fp > 0 else None,
                         density_outside_footprints_per_m2=round(v[5] / max(cells_r - cells_fp, 1e-9), 1),
                         class2_per_m2=round(v[6] / A, 2) if cl_present else None, class6_per_m2=round(v[7] / A, 2) if cl_present else None,
                         coverage_0p5m_cells=round(cov, 4) if cov is not None else None)
    rec["regions"] = regs
    rec["seconds"] = round(time.time() - t1, 1)
    if gsum is not None:
        np.savez_compressed(ground_out.replace(".npz", "_" + f.split("/")[-1].split(".")[0] + ".npz"), gsum=gsum, gcnt=gcnt, origin=[690000.0, 5335000.0], res=2.0)
    results[f] = rec
    print(f, total, rec.get("gps_time", {}).get("utc_min"), rec.get("gps_time", {}).get("utc_max"), rec["seconds"], "s", flush=True)
json.dump(dict(results=results, raster_res_m=RES, rule="density = points whose XY falls in the region raster (0.1 m) / polygon area; inside/outside footprints = LoD2 GroundSurface raster (0.1 m)", seconds=round(time.time() - t0, 1)), open(out_path, "w"), indent=1)
