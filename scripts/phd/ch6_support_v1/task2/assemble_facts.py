"""Assemble facts_6_3.json from the computed JSON files in this folder (no new measurement).
Usage: python3 -I assemble_facts.py <task2_dir> <prep_payload_dir>"""
import json, sys, datetime
from pathlib import Path
S, PREP = Path(sys.argv[1]), Path(sys.argv[2])
L = lambda p: json.load(open(S / p))
reg = L("regions_used_plus.json"); lod2 = L("lod2/lod2_summary.json"); gsd = L("gsd_views.json")["summary"]
xmp = L("xmp_all.json")["summary"]; exif = L("exif_probe.json")
uls_n = list(L("density_uls_nadir.json")["results"].values())[0]; uls_m = list(L("density_uls_manual.json")["results"].values())[0]
gtc = list(L("density_gtclean.json")["results"].values())[0]; als = L("density_als_aggregated.json"); als_raw = L("density_als.json")["results"]
views = json.load(open(PREP / "step01/views.json")); bviews = json.load(open(PREP / "step06/box_views.json"))
def dens(rec, k):
    v = rec["regions"].get(k)
    if v is None:
        return None
    return dict(points=v["points"], per_m2_all=v["density_all_per_m2"], per_m2_first_returns=v["density_first_returns_per_m2"],
                per_m2_inside_lod2_footprints=v["density_inside_lod2_footprints_per_m2"], per_m2_outside_footprints=v["density_outside_footprints_per_m2"],
                share_single_return=v["share_single_return"], coverage_0p5m_cells=v["coverage_0p5m_cells"])
boxes = {}
for b in ("B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"):
    g = gsd["boxes"][b]
    boxes[b] = dict(box_area_m2=round(reg[f"box_{b}"]["area_m2"], 1), eval_area_m2=round(reg[f"eval_{b}"]["area_m2"], 1), label=reg[f"box_{b}"]["label"],
                    views=dict(train=dict(total=g["train"]["n"], nadir=g["train"]["nadir"], oblique=g["train"]["oblique"]),
                               test=dict(total=g["test"]["n"], nadir=g["test"]["nadir"], oblique=g["test"]["oblique"]),
                               candidate_counts_step06=bviews["views"][b]["counts"]),
                    camera_height_agl_nadir_train_m=g["train"]["H_agl_nadir"],
                    gsd_ground_nadir_train=dict(original_cm=g["train"]["gsd_ground_nadir_original_cm"]["median"], train_grid_cm=g["train"]["gsd_ground_nadir_train_grid_cm"]["median"]),
                    surface_gsd_train_views=dict(original_cm_median=g["train"]["surface_gsd_original_cm"]["median"], train_grid_cm_median=g["train"]["surface_gsd_train_grid_cm"]["median"],
                                                 train_grid_cm_nadir=(g["train"]["surface_gsd_train_grid_cm_nadir"] or {}).get("median"),
                                                 train_grid_cm_oblique=(g["train"]["surface_gsd_train_grid_cm_oblique"] or {}).get("median"),
                                                 surface_depth_m_nadir=g["train"]["surface_depth_m_nadir"], surface_depth_m_oblique=g["train"]["surface_depth_m_oblique"],
                                                 n_views_with_depth=g["train"]["n_views_with_depth_in_box"]),
                    uls_nadir=dict(box=dens(uls_n, f"box_{b}"), eval=dens(uls_n, f"eval_{b}")),
                    uls_manual=dict(box=dens(uls_m, f"box_{b}"), eval=dens(uls_m, f"eval_{b}")),
                    als_2022=dict(box=als[f"box_{b}"], eval=als[f"eval_{b}"]),
                    lod2=dict(n_buildings_half_inside_box=lod2["regions"][f"box_{b}"]["n_half_inside"], ids_half_inside=lod2["regions"][f"box_{b}"]["ids_half_inside"],
                              partial=lod2["regions"][f"box_{b}"]["ids_partial"], attrs=lod2["regions"][f"box_{b}"]["dist_half_inside"]))
boxes["B0_b10"]["gt_clean_B0"] = dict(file="phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/evaluation_reference/r1_b1_sub002_transformed.ply",
                                      points_total=gtc["header"]["points"], target_footprint=dens(gtc, "fp_B0_target_4959323"),
                                      per_m2_all_points_over_footprint_area=round(gtc["header"]["points"] / reg["fp_B0_target_4959323"]["area_m2"], 1),
                                      uls_nadir_same_footprint=dens(uls_n, "fp_B0_target_4959323"), als_same_footprint=als["fp_B0_target_4959323"])
ranges = {}
for r in ("R1", "R2", "R3", "R3E", "R4", "R5", "SW", "B0"):
    v = views["views"][r]["counts"]
    ranges[r] = dict(area_m2=round(reg[f"range_{r}"]["area_m2"], 1), label=reg[f"range_{r}"]["label"], views=v,
                     uls_nadir=dens(uls_n, f"range_{r}"), uls_manual=dens(uls_m, f"range_{r}"), als_2022=als[f"range_{r}"],
                     lod2=dict(n_half_inside=lod2["regions"][f"range_{r}"]["n_half_inside"], n_intersecting=lod2["regions"][f"range_{r}"]["n_intersecting"],
                               attrs=lod2["regions"][f"range_{r}"]["dist_half_inside"]))
d0, d1 = datetime.date(2022, 2, 27), datetime.date(2024, 12, 17)
facts = dict(
    generated=datetime.datetime.now().isoformat(timespec="seconds"), scientific_verdict=None,
    images=dict(n_published=962, n_posed_opf=937, n_unposed=25, camera_exif=dict(make="DJI", model="L2", product="DJI Enterprise L2", drone="Matrice 350 RTK",
                width=5280, height=3956, focal_mm=12.29, focal_35mm=24, f_number=2.8, shutter="Mechanical", pixel_pitch_um_opf=3.3944917929292924,
                opf_sensor_name="Generic_DJI_L2_12.3_5280x3956"),
                xmp_summary={k: xmp[k] for k in ("gps_status", "rtk_flag", "rtk_std_m", "utc_first", "utc_last", "createdate_first", "createdate_last", "blocks_gap_120s",
                                                  "relative_altitude_rounded_5m")},
                pix4d_calibrated=dict(f_px=3717.199209328326, cx=2649.8785097217174, cy=1951.823292554264, model="radial3_tangential2 (COLMAP FULL_OPENCV)"),
                undistorted=gsd["camera"], tilt_counts_937=gsd["tilt_counts"], nadir_threshold_deg=20.0,
                camera_height_agl=dict(rel75_images=gsd["H_agl_rel_alt_75m_images"], n_rel75=gsd["n_rel_alt_75m"], low_alt_images=gsd["H_agl_low_alt_images"],
                                       nadir_le20=gsd["H_agl_nadir"], oblique=gsd["H_agl_oblique"]),
                gsd_ground_75m_nadir=dict(original_cm=gsd["gsd_ground_rel75_original_cm"], train_grid_cm=gsd["gsd_ground_rel75_train_grid_cm"])),
    uls=dict(nadir=dict(header=uls_n["header"], gps_time=uls_n["gps_time"], classes=uls_n["classification_counts"], returns=uls_n["return_number_counts"]),
             manual=dict(header=uls_m["header"], gps_time=uls_m["gps_time"], classes=uls_m["classification_counts"], returns=uls_m["return_number_counts"])),
    als=dict(tiles={k.split("/")[-1]: dict(points=v["total_points_read"], per_m2_tile=round(v["points_in_nominal_tile"] / 1e6, 2), gps_utc=[v["gps_time"]["utc_min"], v["gps_time"]["utc_max"]],
                    header_creation_date=v["header"]["creation_date"], generating_software=v["header"]["generating_software"], system_identifier=v["header"]["system_identifier"],
                    point_format=v["header"]["point_format"], las_version=v["header"]["version"], crs_vlr_present=bool(v["header"]["wkt"] or v["header"]["geokeys"]),
                    classes=v["classification_counts"]) for k, v in als_raw.items()}),
    lod2=dict(tiles=lod2["tiles"], n_buildings=lod2["n_buildings"], whole_tiles=lod2["whole_tiles"], union_8_ranges=lod2["union_8_ranges"], union_4_boxes=lod2["union_4_boxes"],
              named=lod2["named"]),
    boxes=boxes, ranges=ranges,
    datum=dict(gcg2016_zeta_at_site_m=[45.655, 45.668], bridge_constant_m=45.7, frame_shift=[690953.0, 5336071.0, 604.0]),
    time=dict(als_utc="2022-02-27 17:56:14-18:52:16", uls_nadir_utc="2024-12-17 07:42:37-08:12:54", uls_manual_utc="2024-12-17 08:37:29-09:36:48",
              images_utc="2024-12-17 07:42:53-09:37:05 (XMP UTCAtExposure)", als_to_uas_days=(d1 - d0).days, als_to_uas_years=round((d1 - d0).days / 365.25, 2),
              lod2_grundrissaktualitaet="2025-02-17 (all buildings in the 8 ranges)", uas_to_lod2_footprint_currency_days=(datetime.date(2025, 2, 17) - d1).days))
json.dump(facts, open(S / "facts_6_3.json", "w"), indent=1, ensure_ascii=False, default=str)
print("written", S / "facts_6_3.json", (S / "facts_6_3.json").stat().st_size, "bytes; days ALS->UAS", (d1 - d0).days)
