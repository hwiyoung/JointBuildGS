"""Build a portable SRDM point-cloud report from sealed candidates and evaluation.

All point plots are DISPLAY_ONLY. No rendered-image quality metric is computed.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate as ev

COLORS = {"keep": "#18864b", "rejected": "#db463d", "unassessed": "#d6a52c"}
LABELS = {"SRDM_IMAGE_ONLY": "SRDM 영상만", "SRDM_FILTER_OFF": "SRDM 불일치 제거 끔", "SRDM_NATIVE": "SRDM 두 단계 재구현"}
# Figures use ASCII labels so plotting does not depend on a Korean font package.
PLOT_LABELS = {"SRDM_IMAGE_ONLY": "SRDM image only", "SRDM_FILTER_OFF": "SRDM filtering off", "SRDM_NATIVE": "SRDM two-stage reimplementation"}


def choose(points, cap):
    return np.arange(len(points))[::max(1, int(np.ceil(len(points) / cap)))]


def savefig(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def write_ply(path, points, colors):
    """Binary export keeps scene-local double coordinates and point-aligned RGB."""
    records = np.empty(len(points), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8"),
                                         ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    for index, name in enumerate(("x", "y", "z")):
        records[name] = points[:, index]
    for index, name in enumerate(("red", "green", "blue")):
        records[name] = colors[:, index]
    header = ("ply\nformat binary_little_endian 1.0\ncomment scene_local_EPSG25832_provenance_in_report\n"
              f"element vertex {len(points)}\nproperty double x\nproperty double y\nproperty double z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    with path.open("xb") as handle:
        handle.write(header.encode("ascii"))
        records.tofile(handle)


def camera_project(points, pair):
    rectified = (points - pair["rectified_left_to_world_t"]) @ pair["rectified_left_to_world_R"]
    projected = rectified @ pair["P1"][:, :3].T + pair["P1"][:, 3]
    with np.errstate(divide="ignore", invalid="ignore"):
        uv = projected[:, :2] / projected[:, 2:3]
    return uv, rectified[:, 2]


def cloud_panel(axis, points, colors, domain, title, cap, elevation=35, azimuth=-65, total_points=None):
    selected = choose(points, cap)
    if len(selected):
        point = points[selected]
        color = colors[selected] / 255.0 if colors is not None else point[:, 2]
        axis.scatter(point[:, 0], point[:, 1], point[:, 2], c=color, s=.45,
                     cmap="viridis" if colors is None else None,
                     vmin=domain["bbox_min"][2] if colors is None else None,
                     vmax=domain["bbox_max"][2] if colors is None else None, linewidths=0)
    else:
        axis.text2D(.2, .5, "NO POINTS", transform=axis.transAxes)
    lower, upper = domain["bbox_min"], domain["bbox_max"]
    axis.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]), zlim=(lower[2], upper[2]),
             xlabel="local X (m)", ylabel="local Y (m)", zlabel="local Z (m)")
    axis.set_box_aspect(np.array(upper) - lower)
    axis.view_init(elev=elevation, azim=azimuth)
    total = len(points) if total_points is None else int(total_points)
    axis.set_title(f"{title}\n{total:,} native points; display {len(selected):,}", fontsize=9)


def metric_table(region):
    header = "<tr><th>Arm</th><th>Points</th><th>Interpolated</th><th>Candidate→UAS median / P95 m</th><th>UAS→candidate median / P95 m</th><th>UAS within 0.5 m</th></tr>"
    def number(value):
        return "NA" if value is None else f"{value:.3f}"
    rows = []
    for arm, data in region["arms"].items():
        forward = data["measurements"]["native"]["candidate_to_reference"]
        backward = data["measurements"]["native"]["reference_to_candidate"]
        fraction = backward["fraction_within_m"].get("0.5")
        status_text = {"EMPTY_PREDICTION": "EMPTY_PREDICTION — 이 단일 영상쌍의 ROI 예측 점 없음",
                       "REFERENCE_ABSENT": "REFERENCE_ABSENT — ROI 참조 점 없음"}.get(data.get("status"), "")
        label = LABELS[arm] + ("<br><small>" + status_text + "</small>" if status_text else "")
        rows.append(f"<tr><td>{label}</td><td>{data['native_points_in_roi']:,}</td><td>{data['interpolated_points']:,}</td>"
                    f"<td>{number(forward['median_m'])} / {number(forward['p95_m'])}</td>"
                    f"<td>{number(backward['median_m'])} / {number(backward['p95_m'])}</td><td>{number(fraction)}</td></tr>")
    return "<table>" + header + "".join(rows) + "</table>"


def paired_region_section(paired_root, output, region_id):
    source = paired_root / region_id
    region = ev.read_json(source / "paired_analysis.json")
    target = output / region_id / "data" / "paired"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    comparison = region["comparisons"]["SRDM_FILTER_OFF_to_SRDM_NATIVE"]
    primary = comparison["common_all_three_primary"]
    counts = primary["threshold_counts_m"]["0.25"]
    base = region_id + "/data/paired/"
    return ('<h3>같은 왼쪽 픽셀의 거리 변화</h3>'
            '<p>세 방법 모두 비보간 원매칭 점이 고정 ROI 안에 있는 픽셀만 직접 대응합니다. '
            'Δ거리 = SRDM 두 단계 재구현 − 불일치 제거 끔이며, 음수는 UAS 최근접 거리 감소입니다. '
            '이 차이는 정답 여부나 시간차 오류의 판정이 아닙니다.</p>'
            '<table><tr><th>세 방법 공통 픽셀</th><th>유한 거리차</th><th>거리 감소 ≥ 0.25 m</th>'
            '<th>거리 증가 ≥ 0.25 m</th><th>|거리차| &lt; 0.25 m</th></tr>'
            f'<tr><td>{primary["n_pixels"]:,}</td><td>{primary["n_finite_delta"]:,}</td>'
            f'<td>{counts["distance_reduction_ge"]:,}</td><td>{counts["distance_increase_ge"]:,}</td>'
            f'<td>{counts["absolute_change_lt"]:,}</td></tr></table>'
            '<p>불일치 제거 끔 → 두 단계 재구현의 원매칭 지원 변화는 공통 픽셀 거리표와 별도로 셉니다: '
            f'추가(gained) {comparison["gained_measured_pixels"]:,}개, '
            f'소실(lost) {comparison["lost_measured_pixels"]:,}개. '
            f'이 중 참조 XY 지원이 없는 경우는 추가 {comparison["gained"]["reference_xy_absent_unknown"]:,}개, '
            f'소실 {comparison["lost"]["reference_xy_absent_unknown"]:,}개이며 원인은 미확정입니다.</p>'
            f'<p><a href="{base}paired_analysis.json">영역 paired JSON</a> · '
            f'<a href="{base}common_pixel_deltas.csv.gz">공통 픽셀 거리차 CSV.gz</a> · '
            f'<a href="{base}measured_pixel_union.csv.gz">전체 원매칭 지원 CSV.gz</a> · '
            f'<a href="{base}aligned_rays.npz">픽셀 대응 원자료 NPZ</a></p>'
            '<figure><figcaption>세 방법 공통 원매칭 픽셀의 UAS 거리차 — 모든 영역에서 −2~2 m 고정, 범위 초과 수 별도 표시</figcaption>'
            f'<a href="{base}common_pixel_delta.png"><img loading="lazy" src="{base}common_pixel_delta.png" '
            'alt="같은 왼쪽 픽셀에서 두 단계 재구현과 불일치 제거 끔의 최근접 거리차"></a></figure>')


def region_figures(run_root, eval_root, output, region, config, paired_root=None):
    rid, domain = region["id"], region["domain"]
    dest = output / rid
    dest.mkdir()
    data_dest = dest / "data"
    data_dest.mkdir()
    pair = ev.load_npz(run_root / rid / "pair.npz")
    decision = ev.load_npz(run_root / rid / "decision.npz")
    reference = ev.load_npz(eval_root / rid / "reference_display.npz")
    clouds, payloads = {}, {}
    downloads = []
    cap = int(config.get("display_max_points", 200000))
    for arm in ev.ARMS:
        source = run_root / rid / arm / "result.npz"
        payload = ev.load_npz(source)
        points = ev.xyz(payload["xyz"], arm)
        mask = ev.roi_mask(points, domain)
        clouds[arm] = (points[mask], payload["rgb"][mask])
        payloads[arm] = payload
        write_ply(data_dest / (arm + ".ply"), *clouds[arm])
        shutil.copy2(source, data_dest / (arm + ".npz"))
        downloads.append(f'<a href="{rid}/data/{arm}.ply">{LABELS[arm]} PLY</a> · <a href="{rid}/data/{arm}.npz">raw NPZ</a>')
    for filename in ("decision.npz", "pair.npz"):
        shutil.copy2(run_root / rid / filename, data_dest / filename)
        downloads.append(f'<a href="{rid}/data/{filename}">{filename}</a>')
    shutil.copytree(eval_root / rid, data_dest / "evaluation")
    downloads.append(f'<a href="{rid}/data/evaluation/evaluation.json">evaluation JSON</a> · '
                     f'<a href="{rid}/data/evaluation/als_decision_reference.csv.gz">ALS decision raw CSV.gz</a> · '
                     f'<a href="{rid}/data/evaluation/height_grid_auxiliary.csv.gz">auxiliary height cells CSV.gz</a>')
    for arm in ev.ARMS:
        downloads.append(f'<a href="{rid}/data/evaluation/{arm}/candidate_distances.csv.gz">{LABELS[arm]} point distances CSV.gz</a> · '
                         f'<a href="{rid}/data/evaluation/{arm}/reference_distances.csv.gz">UAS→{LABELS[arm]} CSV.gz</a>')
    left, right = pair["left_rgb"], pair["right_rgb"]
    height, width = left.shape[:2]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    axes[0].imshow(left)
    axes[0].set_title("Matching input: rectified left RGB")
    axes[1].imshow(right)
    axes[1].set_title("Matching input: rectified right RGB")
    axes[2].imshow(left)
    prior = ev.xyz(decision["als_xyz"], "decision ALS")
    uv = pair.get("als_pixel_xy")
    if uv is None or np.asarray(uv).shape != (len(prior), 2):
        uv, _ = camera_project(prior, pair)
    for state, color in COLORS.items():
        mask = np.asarray(decision[state], dtype=bool) & ev.roi_mask(prior, domain)
        mask &= np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < width) & (uv[:, 1] >= 0) & (uv[:, 1] < height)
        axes[2].scatter(uv[mask, 0], uv[mask, 1], s=5, c=color, label=f"{state}: {mask.sum():,}", alpha=.8)
    axes[2].set_title("ALS decisions projected on the same left input")
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.set(xlim=(0, width), ylim=(height, 0))
        axis.axis("off")
    savefig(fig, dest / "input_decision_overlay.png")
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    lo, hi = float(pair["disparity_min"]), float(pair["disparity_max"])
    weak = decision.get("weak_disparity", decision.get("weak_disparity_map"))
    if weak is not None and np.asarray(weak).shape == (height, width):
        weak_valid = decision.get("weak_valid", np.isfinite(weak))
        image = axes[0, 0].imshow(np.where(weak_valid, weak, np.nan), cmap="turbo", vmin=lo, vmax=hi)
        fig.colorbar(image, ax=axes[0, 0], label="full-resolution disparity (px)")
    else:
        axes[0, 0].text(.2, .5, "Weak disparity map unavailable", transform=axes[0, 0].transAxes)
    axes[0, 0].set_title("Weak matching / unassessed pixels omitted")
    axes[0, 1].imshow(pair["sparse_disparity"], cmap="turbo", vmin=lo, vmax=hi)
    axes[0, 1].set_title("Input sparse ALS disparity")
    state_map = np.full((height, width), np.nan)
    for value, key in enumerate(("prior_keep", "prior_reject", "prior_untestable")):
        if key in decision and np.asarray(decision[key]).shape == state_map.shape:
            state_map[np.asarray(decision[key], dtype=bool)] = value
    if np.isfinite(state_map).any():
        from matplotlib.colors import ListedColormap
        axes[0, 2].imshow(state_map, cmap=ListedColormap(list(COLORS.values())), vmin=0, vmax=2)
    else:
        axes[0, 2].text(.05, .5, "Raster decision unavailable; see native point overlay", transform=axes[0, 2].transAxes, fontsize=8)
    axes[0, 2].set_title("Sparse decision: green keep / red reject / gold unassessed")
    for axis, arm in zip(axes[1], ev.ARMS):
        payload = payloads[arm]
        axis.imshow(np.where(payload["valid"], payload["disparity"], np.nan), cmap="turbo", vmin=lo, vmax=hi)
        axis.set_title(PLOT_LABELS[arm] + " final disparity", fontsize=9)
    for axis in axes.ravel():
        axis.axis("off")
    savefig(fig, dest / "disparity_comparison.png")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axis, arm in zip(axes, ev.ARMS):
        payload = payloads[arm]
        masks = np.zeros(payload["valid"].shape, dtype=np.uint8)
        masks[np.asarray(payload["valid"], bool)] = 1
        masks[np.asarray(payload["interpolated_mask"], bool)] = 2
        axis.imshow(masks, vmin=0, vmax=2, cmap="viridis")
        axis.set_title(PLOT_LABELS[arm] + "\n0 invalid / 1 original / 2 interpolated", fontsize=9)
        axis.axis("off")
    savefig(fig, dest / "validity_interpolation_masks.png")
    fig = plt.figure(figsize=(17, 10))
    for index, arm in enumerate(ev.ARMS):
        axis = fig.add_subplot(2, 3, index + 1, projection="3d")
        cloud_panel(axis, *clouds[arm], domain, PLOT_LABELS[arm] + " / native RGB", cap)
    mask = ev.roi_mask(prior, domain)
    colors = np.tile(np.array([214, 165, 44], np.uint8), (len(prior), 1))
    colors[np.asarray(decision["keep"], bool)] = [24, 134, 75]
    colors[np.asarray(decision["rejected"], bool)] = [219, 70, 61]
    cloud_panel(fig.add_subplot(2, 3, 4, projection="3d"), prior[mask], colors[mask], domain, "Original ALS / decision colors", cap)
    cloud_panel(fig.add_subplot(2, 3, 5, projection="3d"), reference["xyz"], None, domain, "UAS reference / height colors", cap,
                total_points=region["reference_points"])
    fig.text(.69, .15, "Same ROI, axes and camera in all panels.\nDISPLAY_ONLY deterministic subsets.\nRGB comes from the matching image.\nPoint density is not evidence of detail recovery.\nUAS coverage absence remains unknown.", fontsize=10)
    savefig(fig, dest / "same_view_pointclouds.png")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axis, arm in zip(axes, ev.ARMS):
        axis.imshow(left)
        points, colors = clouds[arm]
        selected = choose(points, cap)
        projected, depth = camera_project(points[selected], pair)
        visible = np.isfinite(projected).all(axis=1) & (depth > 0)
        order = np.flatnonzero(visible)[np.argsort(depth[visible])[::-1]]
        axis.scatter(projected[order, 0], projected[order, 1], c=colors[selected][order] / 255, s=.6, linewidths=0)
        axis.set(xlim=(0, width), ylim=(height, 0), title=PLOT_LABELS[arm])
        axis.axis("off")
    fig.suptitle("Point projection on matching input (DISPLAY_ONLY, not GS rendering or independent appearance evaluation)", fontsize=10)
    savefig(fig, dest / "same_camera_projection.png")
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), constrained_layout=True)
    center = (np.array(domain["bbox_min"]) + domain["bbox_max"]) / 2
    half_width = float(config.get("section_half_width_m", .25))
    for row, (dim, axis_label, other_dim, ref_key) in enumerate(((0, "X", 1, "section_x"), (1, "Y", 0, "section_y"))):
        for axis, arm in zip(axes[row], ev.ARMS):
            points, colors = clouds[arm]
            sl = np.abs(points[:, dim] - center[dim]) <= half_width
            uas = reference[ref_key]
            axis.scatter(uas[:, other_dim], uas[:, 2], s=2, c="black", alpha=.3, label="UAS reference", zorder=1)
            prior_slice = mask & (np.abs(prior[:, dim] - center[dim]) <= half_width)
            axis.scatter(prior[prior_slice, other_dim], prior[prior_slice, 2], s=5, c="#c55a28", alpha=.65, label="Original ALS", zorder=2)
            axis.scatter(points[sl, other_dim], points[sl, 2], s=5, c="#0072b2", label="Prediction (same native points)", zorder=3)
            axis.set(xlim=(domain["bbox_min"][other_dim], domain["bbox_max"][other_dim]),
                     ylim=(domain["bbox_min"][2], domain["bbox_max"][2]), xlabel="XY section coordinate (m)", ylabel="local Z (m)",
                     title=f"{PLOT_LABELS[arm]}\n{axis_label} = {center[dim]:.3f} +/- {half_width:.3f} m")
            axis.legend(fontsize=7)
            axis.grid(alpha=.2)
    savefig(fig, dest / "fixed_sections.png")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for arm in ev.ARMS:
        raw = ev.load_npz(eval_root / rid / arm / "native_distances.npz")
        for axis, key in zip(axes, ("candidate_to_reference", "reference_to_candidate")):
            distances = np.sort(raw[key][np.isfinite(raw[key])])
            if len(distances):
                selected = choose(distances, 5000)
                axis.plot(distances[selected], (selected + 1) / len(raw[key]), label=PLOT_LABELS[arm])
            axis.set(xlabel="3D nearest-point distance (m)", ylabel="fraction of all source points", ylim=(0, 1), title=key)
            axis.legend(fontsize=8)
            axis.grid(alpha=.2)
    savefig(fig, dest / "native_distance_ecdf.png")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    decision_ref = ev.load_npz(eval_root / rid / "als_decision_reference.npz")
    for axis, supported_only in zip(axes, (False, True)):
        for state, color in COLORS.items():
            selected = decision_ref["in_roi"] & np.asarray(decision[state], bool)
            if supported_only:
                selected &= decision_ref["reference_xy_support"]
            distances = np.sort(decision_ref["distance_to_reference"][selected])
            finite_indices = np.flatnonzero(np.isfinite(distances))
            if len(finite_indices):
                reduced = finite_indices[choose(finite_indices, 5000)]
                axis.plot(distances[reduced], (reduced + 1) / len(distances), color=color, label=f"{state} (n={len(distances)})")
        axis.set(xlabel="ALS to UAS point distance (m)", ylabel="fraction of decision-state points", ylim=(0, 1),
                 title="Reference XY-supported cells only" if supported_only else "All ALS points in fixed ROI")
        axis.grid(alpha=.2)
        if axis.lines:
            axis.legend(fontsize=8)
    savefig(fig, dest / "als_decision_distance_ecdf.png")
    plots = [("input_decision_overlay.png", "실제 매칭 입력과 원 ALS 판단"),
             ("disparity_comparison.png", "약한 매칭과 최종 시차 — 공통 색 범위"),
             ("validity_interpolation_masks.png", "무효·원 매칭·보간 영역"),
             ("same_view_pointclouds.png", "같은 좌표·시점의 원 점군"),
             ("same_camera_projection.png", "동일 입력 카메라 투영 — 독립 외관 평가는 아님"),
             ("fixed_sections.png", "고정 ROI 중심 단면 — 청색 예측점 / 검정 UAS / 주황 원 ALS; 같은 위치·폭"),
             ("native_distance_ecdf.png", "원 점군 양방향 참조 거리 분포"),
             ("als_decision_distance_ecdf.png", "ALS 유지·제외·미판단의 연속 참조 거리 — 정답 라벨이 아님")]
    figures = "".join(f'<figure><figcaption>{caption}</figcaption><a href="{rid}/{filename}"><img loading="lazy" src="{rid}/{filename}" alt="{caption}"></a></figure>' for filename, caption in plots)
    paired = paired_region_section(paired_root, output, rid) if paired_root is not None else ""
    return f'<section id="{rid}"><h2>{rid}</h2>{metric_table(region)}<p>공통 XY 지원 셀: {region["common_all_arm_reference_xy_cells"]:,}; UAS 지원 셀: {region["reference_xy_cells"]:,}. 공통 지원·밀도 민감도·보간 제외 결과는 JSON/CSV에서 별도 확인합니다.</p><details><summary>원자료 및 색 점군 내려받기</summary><p>' + "<br>".join(downloads) + "</p></details>" + paired + figures + "</section>"


def run(run_root, evaluation, output, paired_root=None):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run project report generation in Docker")
    summary = ev.read_json(evaluation / "evaluation.json")
    if summary.get("scientific_verdict", "missing") is not None or summary.get("reference_accessed") is not True:
        raise ValueError("Completed null-verdict evaluation required")
    for name, expected in summary["gate"]["outputs"].items():
        if ev.sha(run_root / name) != expected:
            raise ValueError(f"Candidate changed since evaluation: {name}")
    paired_sha256 = None
    if paired_root is not None:
        paired = ev.read_json(paired_root / "paired_analysis.json")
        if paired.get("scientific_verdict", "missing") is not None or paired.get("candidate_update_performed") is not False:
            raise ValueError("Null-verdict paired analysis without candidate updates required")
        if paired["candidate_sha256"] != summary["gate"]["outputs"]:
            raise ValueError("Paired analysis candidate lineage differs from evaluation")
        if paired["evaluation_input_sha256"].get("evaluation.json") != ev.sha(evaluation / "evaluation.json"):
            raise ValueError("Paired analysis does not refer to this evaluation")
        if paired["fixed_delta_color_range_m"] != [-2., 2.] or .25 not in paired["thresholds_m"]:
            raise ValueError("Paired analysis display range or existing threshold differs")
        if [region["id"] for region in paired["regions"]] != [region["id"] for region in summary["regions"]]:
            raise ValueError("Paired analysis region membership differs from evaluation")
        for region in paired["regions"]:
            if ev.read_json(paired_root / region["id"] / "paired_analysis.json") != region:
                raise ValueError("Paired region summary differs from its parent summary")
        paired_sha256 = ev.sha(paired_root / "paired_analysis.json")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(evaluation / "metrics.csv", output / "metrics.csv")
    shutil.copy2(evaluation / "evaluation.json", output / "evaluation.json")
    if paired_root is not None:
        shutil.copy2(paired_root / "paired_analysis.json", output / "paired_analysis.json")
    sections = [region_figures(run_root, evaluation, output, region, summary["config"], paired_root) for region in summary["regions"]]
    paired_navigation = '<a href="paired_analysis.json">공통 픽셀 분석 JSON</a>' if paired_root is not None else ""
    frame = html.escape(json.dumps(summary["frame"], ensure_ascii=False))
    document = ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>SRDM P1/P2/P3 development evaluation</title><style>'
                'body{font:16px/1.6 system-ui,sans-serif;margin:32px auto;max-width:1280px;padding:0 20px;background:#f7f8fa;color:#172232}'
                'h1,h2{line-height:1.3}nav a{margin-right:18px}section{margin-top:48px}table{border-collapse:collapse;width:100%;font-size:14px;background:white}'
                'th,td{border:1px solid #d8dee8;padding:8px;text-align:left}figure{margin:24px 0;background:white;padding:14px;border-radius:8px}'
                'img{display:block;max-width:100%;height:auto}figcaption{font-weight:600;margin-bottom:8px}details{padding:12px;background:#e9eef5}'
                'a{color:#155eae}code{font-size:13px;overflow-wrap:anywhere}.note{padding:16px;background:#fff4d6}</style>'
                '<h1>SRDM P1/P2/P3 개발 평가</h1><nav><a href="#P1">P1</a><a href="#P2">P2</a><a href="#P3">P3</a>'
                '<a href="metrics.csv">정량표 CSV</a><a href="evaluation.json">전체 평가 JSON</a>' + paired_navigation + '</nav>'
                '<p>원문 기반 SRDM 재구현의 정적 ALS 판단과 후속 색 점군을 비교합니다. 공식 구현 실행 또는 원논문 수치 재현으로 표시하지 않습니다.</p>'
                '<p class="note">UAS 최근접 거리는 참조 편차이며 유지·제외의 정답 라벨이 아닙니다. 가림과 시간차 오류를 자동 구별하지 않습니다. '
                '모든 그림은 표시용이며 원 점군으로 계산한 수치와 분리됩니다. GS 렌더 품질·LoD2 성능·확증 결론은 평가하지 않았습니다. '
                '<strong>scientific_verdict: null</strong></p><p>좌표 계보: <code>' + frame + '</code></p>'
                '<p>' + html.escape(summary["limitations"]) + '</p>' + "".join(sections) + '</html>')
    (output / "index.html").write_text(document)
    files = {str(path.relative_to(output)): ev.sha(path) for path in output.rglob("*") if path.is_file()}
    ev.write_json(output / "report_receipt.json", {"scientific_verdict": None, "role": "DEVELOPMENT_DISPLAY_AND_EVIDENCE_PACKAGE",
                  "evaluation_sha256": ev.sha(evaluation / "evaluation.json"), "paired_analysis_sha256": paired_sha256,
                  "builder_sha256": ev.sha(__file__), "outputs": files})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evaluation", "--evaluation-root", dest="evaluation", type=Path, required=True)
    parser.add_argument("--paired-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.run_root, args.evaluation, args.output, args.paired_root)
