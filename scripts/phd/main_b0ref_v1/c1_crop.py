"""PHD-MAIN-B0REF-v1 일 1: inventory of a source file and its B0-box crop in the raw comparison frame (jointbuildgs:dev, CPU).

  python c1_crop.py <source>        source = uls_nadir | uls_manual | photogrammetry | geogs | uls_manual_v120 | fill_v120 | fill_v110
  -> /b0/crop/<source>.npz (the B0 box points: xyz local float64 (laz - world shift; GeoGS: author + [2, -29, 0]), the LAS fields),
     /b0/prep/inventory_<source>.json (file size, sha256, header, fields, CRS, point count, GPS-time range and dates, point-source ids)

LAS files are read in chunks of 4 M points and cut to the B0 box (uv rectangle of DR/s02_box/B0_b10/range.json) before anything is
kept (memory cap 8 GB, request 2.8). GPS time: LAS global-encoding bit 0 = adjusted standard GPS time (GPS seconds - 1e9); the date is
GPS epoch 1980-01-06 + (t + 1e9) s - 18 leap seconds (UTC, valid for 2017-2026). Nothing is written outside /b0. scientific_verdict: null."""
import datetime as dt
import sys
import time

import numpy as np

from b0_common import B0, SHIFT, SRC, in_rect, jdump, log, now, read_geogs, sha256

CHUNK = 4_000_000
GPS0 = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)


def gps_to_utc(t, adjusted):
    if not adjusted:
        return None
    return (GPS0 + dt.timedelta(seconds=float(t) + 1e9 - 18)).isoformat()


def header_of(f):
    h = f.header
    vl = []
    for v in h.vlrs:
        e = dict(user_id=v.user_id, record_id=v.record_id, description=v.description)
        try:
            if hasattr(v, "string"):
                e["text"] = str(v.string)[:3000]
            elif hasattr(v, "parse_crs"):
                e["crs"] = str(v.parse_crs())[:3000]
        except Exception as ex:  # noqa: BLE001
            e["error"] = str(ex)
        vl.append(e)
    crs = None
    try:
        c = h.parse_crs()
        crs = None if c is None else dict(name=c.name, epsg=c.to_epsg(), wkt=c.to_wkt()[:2000])
    except Exception as ex:  # noqa: BLE001
        crs = dict(error=str(ex))
    return dict(version=str(h.version), point_format=int(h.point_format.id), point_count=int(h.point_count),
                dimensions=[dict(name=d.name, type=str(d.dtype)) for d in h.point_format.dimensions],
                extra_dimensions=list(h.point_format.extra_dimension_names), scales=h.scales.tolist(), offsets=h.offsets.tolist(),
                mins=h.mins.tolist(), maxs=h.maxs.tolist(), global_encoding=int(h.global_encoding.value),
                adjusted_standard_gps_time=bool(h.global_encoding.gps_time_type.value == 1),
                system_identifier=str(h.system_identifier), generating_software=str(h.generating_software),
                creation_date=str(h.creation_date), number_of_points_by_return=[int(x) for x in h.number_of_points_by_return],
                vlrs=vl, crs=crs)


EXTRA = {   # files fetched during 일 4 (not in the locked config; recorded as a change in the report): name -> path under /b0/dl
    "uls_manual_v120": B0 / "dl/zenodo_v120_manual/TUM_Downtown_ULS_20241217_manual.laz",
    "fill_v120": B0 / "dl/zenodo_v120_fillparts/TUM_Downtown_ULS_20241217_manual_5mm_fillparts.laz",
    "fill_v110": B0 / "dl/zenodo_v110_fillparts/TUM_Downtown_ULS_20241217_manual_5mm_fillparts.laz",
}


def crop_las(name):
    import laspy
    p = SRC[name] if name in SRC else EXTRA[name]
    t0 = time.time()
    with laspy.open(str(p), laz_backend=laspy.LazBackend.LazrsParallel) as f:
        hdr = header_of(f)
        dims = {d["name"] for d in hdr["dimensions"]}
        keep = [k for k in ("return_number", "number_of_returns", "intensity", "classification", "gps_time", "point_source_id",
                            "scan_angle", "scan_angle_rank", "user_data", "red", "green", "blue") if k in dims]
        parts = {k: [] for k in ["xyz"] + keep}
        gmin, gmax, n_all = np.inf, -np.inf, 0
        psid_all = {}
        for pts in f.chunk_iterator(CHUNK):
            x = np.asarray(pts.x) - SHIFT[0]; y = np.asarray(pts.y) - SHIFT[1]
            n_all += len(x)
            if "gps_time" in dims:
                g = np.asarray(pts.gps_time); gmin = min(gmin, float(g.min())); gmax = max(gmax, float(g.max()))
            if "point_source_id" in dims:
                u, c = np.unique(np.asarray(pts.point_source_id), return_counts=True)
                for a, b in zip(u.tolist(), c.tolist()):
                    psid_all[a] = psid_all.get(a, 0) + b
            m = in_rect(np.column_stack([x, y]), "box")
            if m.any():
                z = np.asarray(pts.z)[m] - SHIFT[2]
                parts["xyz"].append(np.column_stack([x[m], y[m], z]))
                for k in keep:
                    parts[k].append(np.asarray(getattr(pts, k))[m])
            del x, y, m
            if n_all % (10 * CHUNK) < CHUNK:
                log(name, f"{n_all:,} read, {sum(len(a) for a in parts['xyz']):,} kept")
    out = {k: np.concatenate(v) for k, v in parts.items() if v}
    np.savez(B0 / "crop" / f"{name}.npz", **out)
    crop = dict(points=int(len(out["xyz"])), mins=out["xyz"].min(0).tolist(), maxs=out["xyz"].max(0).tolist())
    if "gps_time" in out:
        g = out["gps_time"]
        crop["gps_time"] = dict(min=float(g.min()), max=float(g.max()), utc_min=gps_to_utc(g.min(), hdr["adjusted_standard_gps_time"]),
                                utc_max=gps_to_utc(g.max(), hdr["adjusted_standard_gps_time"]))
    if "point_source_id" in out:
        u, c = np.unique(out["point_source_id"], return_counts=True)
        crop["point_source_ids"] = {int(a): int(b) for a, b in zip(u, c)}
    if "number_of_returns" in out:
        u, c = np.unique(out["number_of_returns"], return_counts=True)
        crop["number_of_returns"] = {int(a): int(b) for a, b in zip(u, c)}
    if "classification" in out:
        u, c = np.unique(out["classification"], return_counts=True)
        crop["classification"] = {int(a): int(b) for a, b in zip(u, c)}
    for k in ("red", "green", "blue", "intensity"):
        if k in out:
            crop[f"{k}_range"] = [int(out[k].min()), int(out[k].max())]
    rec = dict(source=name, path=str(p), bytes=p.stat().st_size, sha256=sha256(p), header=hdr, points_in_file=int(n_all),
               gps_time_file=dict(min=gmin, max=gmax, utc_min=gps_to_utc(gmin, hdr["adjusted_standard_gps_time"]),
                                  utc_max=gps_to_utc(gmax, hdr["adjusted_standard_gps_time"])) if np.isfinite(gmin) else None,
               point_source_ids_file={int(k): int(v) for k, v in sorted(psid_all.items())}, b0_box=crop, kept_fields=keep,
               frame="laz - world shift [690953, 5336071, 604] m (no height alignment, no cleaning)",
               seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(B0 / "prep" / f"inventory_{name}.json", rec)
    log(name, "done", crop["points"], rec["seconds"], "s")


def crop_geogs():
    t0 = time.time()
    X, rgb, hdr = read_geogs(raw=True)
    inb = in_rect(X[:, :2], "box"); ine = in_rect(X[:, :2], "eval")
    np.savez(B0 / "crop" / "geogs.npz", xyz=X, red=rgb[:, 0], green=rgb[:, 1], blue=rgb[:, 2], file_row=np.arange(len(X), dtype=np.int64))
    p = SRC["geogs"]
    Xa = X - np.array([2.0, -29.0, 0.0])
    rec = dict(source="geogs", path=str(p), bytes=p.stat().st_size, sha256=sha256(p), header_text=hdr, points_in_file=int(len(X)),
               fields=["x double", "y double", "z double", "red uchar", "green uchar", "blue uchar"],
               author_frame=dict(mins=Xa.min(0).tolist(), maxs=Xa.max(0).tolist()),
               study_raw_frame=dict(mins=X.min(0).tolist(), maxs=X.max(0).tolist(), in_box=int(inb.sum()), in_eval=int(ine.sum())),
               rgb_range=[int(rgb.min()), int(rgb.max())], rgb_distinct=int(len(np.unique(rgb[:, 0].astype(np.int64) * 65536 + rgb[:, 1] * 256 + rgb[:, 2]))),
               coordinate_decimals=dict((ax, decimals(X[:, i] - [2.0, -29.0, 0.0][i])) for i, ax in enumerate("xyz")),
               frame="author frame + [2, -29, 0] m (no height alignment)", seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(B0 / "prep" / "inventory_geogs.json", rec)
    log("geogs done", len(X))


def decimals(a, n=200000):
    """the coordinate grid of a stored column: share of values that are multiples of 1e-k m (k = 2..6) on a sample."""
    s = a[:: max(1, len(a) // n)]
    out = {}
    for k in range(2, 7):
        q = s * 10 ** k
        out[f"1e-{k}"] = float(np.mean(np.abs(q - np.round(q)) < 1e-6 * 10 ** k * 1e-3))
    return out


if __name__ == "__main__":
    (B0 / "crop").mkdir(exist_ok=True); (B0 / "prep").mkdir(exist_ok=True)
    for nm in sys.argv[1:]:
        crop_geogs() if nm == "geogs" else crop_las(nm)
