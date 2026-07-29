#!/usr/bin/env python3
"""FC-S6c Step 0-1 design freeze and no-training proxy audit.

This script does not train, does not call Stage3, and does not call Metric-v1.
It only reads existing FC-S6 Stage3Algo-v1 + Metric-v1 artifacts and writes the
FC-S6c Lmu5-Lmu8 design/proxy reports.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np


FC6 = Path("results/FC_S6_componentwise_revised_lmutual_design_validation")
OUT = Path("results/FC_S6C_lmutual_completion")
DESIGN_DOC = Path("docs/experiments/footprint_conditioned/reports/FC_S6C_LMU5_8_DESIGN_FREEZE.md")
DESIGN_OUT = OUT / "phase0_design_freeze" / "FC_S6C_LMU5_8_DESIGN_FREEZE.md"
PROXY_OUT = OUT / "phase1_proxy_audit"
RUN_LOG = OUT / "phase1_proxy_audit" / "fc_s6c_proxy_audit_run.json"

PHASE1 = FC6 / "phase1_existing_terms"
PHASE2 = FC6 / "phase2_terrain_safe"

ARMS = [
    ("A0_baseline_w0", "Baseline", PHASE1),
    ("A1_original_mutual", "Original Mutual", PHASE1),
    ("A4_terrain_normal_only", "A4 terrain-normal-only", PHASE1),
    ("A8_no_terrain_terms", "A8 no-terrain revised Mutual", PHASE1),
    ("B2_terrain_confidence_gated", "B2 terrain confidence-gated", PHASE2),
    ("A9_no_terrain_terms_ramp", "A9 no-terrain + ramp", PHASE1),
]
BIDS = ["B0", "B1", "B2", "B8", "B6", "B3", "B123", "B126", "B50", "B104"]
ROOF_COMPLEX = {"B3", "B123", "B126"}
TERRAIN_SENSITIVE = {"B104", "B6", "B50"}

METRIC_FILES = [
    PHASE1 / "term_ablation_metrics_by_bid.csv",
    PHASE2 / "terrain_safe_metrics_by_bid.csv",
]
GRAVITY = np.asarray([0.0, 1.0, 0.0], dtype=np.float64)


DESIGN_TEXT = """# FC-S6c Lmu5-Lmu8 Design Freeze

Status: design-frozen for no-training proxy audit and single-term smoke consideration.

This document freezes the proposed revised `L_mutual` completion terms beyond the accepted FC-S6b terrain-off candidate (`A8_no_terrain_terms`). It does not authorize training by itself. It also does not enable `L_structure`, G2, Stage3 changes, or Metric-v1 changes.

## Shared Constraints

- Stage2 loss construction must not use GT roof type, GT roof partition, GT final mesh, or GT semantic surfaces.
- Stage3Algo-v1 and Metric-v1 remain fixed evaluation-only consumers.
- `GroundSurface` is a Stage3 final semantic face; Stage2 uses terrain evidence / terrain primitive class.
- All terms are single-term smoke candidates first. Combined terms are not allowed until single-term smoke and gate review.
- All terms must be logged separately and must support default-off equivalence.
- All gates are computed from Stage2 predictions, geometry, support, confidence, and fixed domain/footprint assumptions only.
- Normalized weights are relative to the accepted A8 terrain-off Mutual scale. Gradient guard is enforced against the base loss gradient norm when gradient diagnostics are enabled.

## Lmu5 Split Roof-Height Relation

1. Final-output target: shell diagnostics first (`h_err`, `vol_ratio`), then semantic faces through stable RoofSurface/Terrain separation.
2. Formula:

```text
h_i = -dot(c_i, e_gravity)
H_t = stopgrad(weighted_quantile(h_i | terrain evidence, q=0.90))
Lmu5 = mean_i p_roof_i * relu((H_t + m_rt) - h_i)^2
```

`m_rt` is a small roof-terrain clearance margin in world units. This is roof-side only; terrain-side height compaction is not reintroduced here.

3. Stopgrad policy: stop gradient through `H_t`, terrain masks used to estimate `H_t`, and all quantile selection. Gradients flow only to roof probability/roof-supported geometry for the roof-side penalty.
4. Gate policy: enable only when terrain evidence count and confidence exceed fixed run-level gates; otherwise skip the term and log `gate=off`. No GT terrain surface is used.
5. Initial normalized weight: `0.05`.
6. Expected metric improvement: lower `h_err`, more stable `vol_ratio`, no loss of `ground_cov`; strongest expected signal on `B6` and roof/height-diagnostic cases.
7. Rejection condition: any easy/control regression, B104 `ground_cov` loss, mean support regression, or gradient ratio above guard; reject immediately if proxy improves but final Stage3 F/height metrics do not.
8. Required logs: `loss/mutual_lmu5_roof_height`, `mutual/lmu5_gate`, `mutual/lmu5_terrain_ref_height`, `mutual/lmu5_roof_margin_violation`, `grad_ratio/lmu5_base`.

Gradient ratio guard: `Lmu5` must stay `<= 5%` of base gradient norm.

## Lmu6 Semantic-Geometry Calibration

1. Final-output target: semantic faces and support-confidence. The term is intended to reduce high-confidence semantic/normal contradictions before Stage3 reads out RoofSurface, WallSurface, and terrain evidence.
2. Formula:

```text
d_roof = relu(tau - (n_i dot e_gravity)^2)^2
d_wall = (n_i dot e_gravity)^2
d_terrain = (1 - abs(n_i dot e_gravity))^2
Lmu6 = mean_i stopgrad(conf_i) * [p_roof_i d_roof + p_wall_i d_wall + p_terrain_i d_terrain]
```

This is a calibration term, not a new class prior. It penalizes contradictions only when the predicted semantic probability and geometry disagree.

3. Stopgrad policy: stop gradient through confidence/support scalars and optional gate masks. Gradients may flow to semantic logits and geometry, subject to the gradient ratio guard.
4. Gate policy: only apply to samples with confidence/support above threshold and semantic entropy below threshold. Ambiguous points are logged but not forced.
5. Initial normalized weight: `0.02`.
6. Expected metric improvement: improved `roof_cov`, `wall_cov`, classwise support, and fewer semantic split errors without changing Stage3.
7. Rejection condition: support-confidence improves while final F/coverage does not, or easy/control semantic coverage regresses.
8. Required logs: `loss/mutual_lmu6_sem_geom`, `mutual/lmu6_gate_rate`, `mutual/lmu6_mismatch_roof`, `mutual/lmu6_mismatch_wall`, `mutual/lmu6_mismatch_terrain`, `grad_ratio/lmu6_base`.

Gradient ratio guard: `Lmu6` must stay `<= 5%` of base gradient norm.

## Lmu7 Weak Roof-Wall Hint

1. Final-output target: face graph, specifically roof-wall adjacency candidates that Stage3 can read into a closed shell.
2. Formula:

```text
N_r(i) = local roof-neighborhood support near wall-like evidence
Lmu7 = mean_i stopgrad(g_i) * p_roof_i * p_wall_j * compat_gap(i, j)
compat_gap(i, j) = local_distance_to_roof_wall_contact + normal_parallel_violation
```

The implementation must use local predicted evidence neighborhoods, not GT roof-wall edges.

3. Stopgrad policy: stop gradient through neighbor selection, support gates, and geometric contact targets. Gradient flows only through weak semantic compatibility and local geometry residual.
4. Gate policy: require high-confidence roof and wall evidence, local support, and finite neighborhood size. Disable for sparse/ambiguous support.
5. Initial normalized weight: `0.02`.
6. Expected metric improvement: better roof-wall adjacency consistency, lower roof-wall gap flags, no topology increase in open/non-manifold edges.
7. Rejection condition: any increase in open_edges/non_manifold_edges, roof_complex regression, or gradient ratio above guard.
8. Required logs: `loss/mutual_lmu7_roof_wall`, `mutual/lmu7_gate_rate`, `mutual/lmu7_contact_gap`, `mutual/lmu7_normal_violation`, `grad_ratio/lmu7_base`.

Gradient ratio guard: `Lmu7` must stay `<= 5%` of base gradient norm.

## Lmu8 Weak Terrain-Wall Hint

1. Final-output target: face graph and shell diagnostics, specifically wall-ground adjacency and GroundSurface closure.
2. Formula:

```text
G_t = stopgrad(local terrain height/support estimate)
Lmu8 = mean_i stopgrad(g_i) * p_wall_i * relu(abs(h_wall_bottom_i - G_t) - m_wg)^2
```

This term is not a terrain-normal or terrain-height revival. It is a weak wall-ground contact hint and must be gated more strictly than Lmu7.

3. Stopgrad policy: stop gradient through terrain reference height, terrain neighbor selection, and terrain support gates. Gradient should primarily affect wall-ground contact compatibility, not terrain class mass.
4. Gate policy: enable only with stable terrain evidence, high terrain confidence, low terrain entropy, and enough local wall support. Disable by default on terrain-ambiguous buildings.
5. Initial normalized weight: `0.01`.
6. Expected metric improvement: preserve B104 `ground_cov`, improve wall-ground closure/support, and reduce hidden GroundSurface failure without terrain drift.
7. Rejection condition: any B104 `ground_cov` or `ground_support_cov` regression, terrain y-drift increase, support regression, or gradient ratio above guard.
8. Required logs: `loss/mutual_lmu8_terrain_wall`, `mutual/lmu8_gate_rate`, `mutual/lmu8_wall_ground_gap`, `mutual/lmu8_terrain_ref_height`, `grad_ratio/lmu8_base`.

Gradient ratio guard: `Lmu8` must stay `<= 2%` of base gradient norm.

## Smoke Order Rule

The no-training proxy audit must decide which terms are eligible for single-term smoke. Recommended default order is `Lmu5`, then `Lmu6`, then `Lmu7`; `Lmu8` requires stronger terrain-safety evidence because FC-S6 showed terrain terms are the main risk path.
"""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def fnum(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.6g}"


def metric_rows() -> dict[tuple[str, str], dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    wanted = {a for a, _, _ in ARMS}
    for path in METRIC_FILES:
        for row in read_csv(path):
            run = row.get("run", "")
            bid = row.get("bid", "")
            if run in wanted and bid in BIDS:
                rows[(run, bid)] = row
    return rows


def run_root(phase: Path, run: str) -> Path:
    return phase / "runs" / run


def stage3_dir(phase: Path, run: str, bid: str) -> Path:
    return run_root(phase, run) / "rendered_evidence" / "stage3_readout" / run / bid


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_evidence(phase: Path, run: str, bid: str) -> dict[str, np.ndarray]:
    path = stage3_dir(phase, run, bid) / "readout_evidence_after_stage3_v1_patch.npz"
    if not path.exists():
        return {}
    data = np.load(path, allow_pickle=True)
    return {k: data[k] for k in data.files}


def height(points: np.ndarray) -> np.ndarray:
    return -points[:, 1].astype(np.float64)


def normalized_entropy(sem_probs: np.ndarray) -> np.ndarray:
    probs = np.clip(sem_probs.astype(np.float64), 1e-8, 1.0)
    ent = -(probs * np.log(probs)).sum(axis=1)
    return ent / math.log(probs.shape[1])


def safe_quantile(values: np.ndarray, q: float) -> float | None:
    if values.size == 0:
        return None
    return float(np.quantile(values.astype(np.float64), q))


def face_normal(face: dict[str, Any]) -> np.ndarray | None:
    normal = face.get("normal")
    if normal is not None:
        n = np.asarray(normal, dtype=np.float64)
        denom = np.linalg.norm(n)
        if denom > 1e-8:
            return n / denom
    verts = np.asarray(face.get("vertices", []), dtype=np.float64)
    if len(verts) < 3:
        return None
    n = np.cross(verts[1] - verts[0], verts[2] - verts[0])
    denom = np.linalg.norm(n)
    if denom <= 1e-8:
        return None
    return n / denom


def face_heights(face: dict[str, Any]) -> np.ndarray:
    verts = np.asarray(face.get("vertices", []), dtype=np.float64)
    if verts.size == 0:
        return np.asarray([], dtype=np.float64)
    return -verts[:, 1]


def get_faces(phase: Path, run: str, bid: str) -> dict[str, dict[str, Any]]:
    sem = load_json(stage3_dir(phase, run, bid) / "semantic_faces.json")
    return {f.get("face_id", ""): f for f in sem.get("faces", []) if f.get("face_id")}


def graph_edges(phase: Path, run: str, bid: str) -> list[dict[str, Any]]:
    graph = load_json(stage3_dir(phase, run, bid) / "face_graph.json")
    return graph.get("edges", []) if isinstance(graph, dict) else []


def shell_diag(phase: Path, run: str, bid: str) -> dict[str, Any]:
    return load_json(stage3_dir(phase, run, bid) / "shell_diagnostics.json")


def lmu5_proxy(ev: dict[str, np.ndarray]) -> dict[str, float | None]:
    if not ev:
        return {"lmu5_proxy": None}
    pts = ev["points"]
    h = height(pts)
    classes = ev["classes"]
    roof_h = h[classes == 1]
    terrain_h = h[classes == 3]
    roof_p10 = safe_quantile(roof_h, 0.10)
    terrain_p90 = safe_quantile(terrain_h, 0.90)
    h_range = float(np.nanmax(h) - np.nanmin(h)) if h.size else 0.0
    margin_m = 0.15
    if roof_p10 is None or terrain_p90 is None or h_range <= 1e-8:
        return {
            "lmu5_proxy": None,
            "lmu5_roof_p10": roof_p10,
            "lmu5_terrain_p90": terrain_p90,
            "lmu5_margin": None,
            "lmu5_violation_frac": None,
        }
    margin = roof_p10 - terrain_p90
    violation = max(0.0, margin_m - margin) / h_range
    threshold = terrain_p90 + margin_m
    violation_frac = float((roof_h < threshold).mean()) if roof_h.size else None
    return {
        "lmu5_proxy": violation,
        "lmu5_roof_p10": roof_p10,
        "lmu5_terrain_p90": terrain_p90,
        "lmu5_margin": margin,
        "lmu5_violation_frac": violation_frac,
    }


def lmu6_proxy(ev: dict[str, np.ndarray]) -> dict[str, float | None]:
    if not ev:
        return {"lmu6_proxy": None}
    normals = ev["normals"].astype(np.float64)
    denom = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(denom, 1e-8)
    dot = normals @ GRAVITY
    dot2 = dot * dot
    abs_dot = np.abs(dot)
    p = ev["sem_probs"].astype(np.float64)
    conf = ev.get("confidence", np.ones(len(p), dtype=np.float64)).astype(np.float64)
    entropy = ev.get("semantic_entropy")
    if entropy is None:
        entropy = normalized_entropy(p)
    else:
        entropy = entropy.astype(np.float64)
    tau = 0.15
    roof_mismatch = p[:, 1] * np.maximum(0.0, tau - dot2) ** 2
    wall_mismatch = p[:, 2] * dot2
    terrain_mismatch = p[:, 3] * (1.0 - abs_dot) ** 2
    gate = ((conf >= 0.35) & (entropy <= 0.70)).astype(np.float64)
    weighted = conf * gate * (roof_mismatch + wall_mismatch + terrain_mismatch)
    denom_gate = float(np.maximum(gate.sum(), 1.0))
    return {
        "lmu6_proxy": float(weighted.sum() / denom_gate),
        "lmu6_roof_mismatch": float((conf * gate * roof_mismatch).sum() / denom_gate),
        "lmu6_wall_mismatch": float((conf * gate * wall_mismatch).sum() / denom_gate),
        "lmu6_terrain_mismatch": float((conf * gate * terrain_mismatch).sum() / denom_gate),
        "lmu6_gate_rate": float(gate.mean()) if len(gate) else None,
        "lmu6_entropy_mean": float(np.mean(entropy)) if len(entropy) else None,
    }


def lmu7_proxy(phase: Path, run: str, bid: str) -> dict[str, float | None]:
    faces = get_faces(phase, run, bid)
    edges = graph_edges(phase, run, bid)
    shell = shell_diag(phase, run, bid)
    n_wall = fnum(shell.get("n_wall_faces")) or 0.0
    h_range = fnum(shell.get("height_range")) or 1.0
    roof_wall_edges = [e for e in edges if e.get("semantic_pair") in {"RoofSurface--WallSurface", "WallSurface--RoofSurface"}]
    normal_terms: list[float] = []
    height_terms: list[float] = []
    for edge in roof_wall_edges:
        fa = faces.get(edge.get("face_a", ""))
        fb = faces.get(edge.get("face_b", ""))
        if not fa or not fb:
            continue
        if fa.get("semantic_type") == "WallSurface":
            wall, roof = fa, fb
        else:
            roof, wall = fa, fb
        nr = face_normal(roof)
        nw = face_normal(wall)
        if nr is not None and nw is not None:
            # Roof and wall should not be nearly parallel. Higher = worse.
            normal_terms.append(max(0.0, abs(float(np.dot(nr, nw))) - 0.35))
        rh = face_heights(roof)
        wh = face_heights(wall)
        if rh.size and wh.size:
            # Roof centroid should sit above wall centroid; weak normalized ordering check.
            height_terms.append(max(0.0, 0.25 - (float(np.mean(rh)) - float(np.mean(wh)))) / max(h_range, 1e-6))
    missing = max(0.0, n_wall - len(roof_wall_edges)) / max(n_wall, 1.0)
    normal_proxy = mean(normal_terms) if normal_terms else None
    height_proxy = mean(height_terms) if height_terms else None
    proxy = 0.5 * (normal_proxy or 0.0) + 0.5 * (height_proxy or 0.0) + missing
    return {
        "lmu7_proxy": proxy,
        "lmu7_roof_wall_edges": float(len(roof_wall_edges)),
        "lmu7_missing_adjacency_frac": missing,
        "lmu7_normal_parallel_violation": normal_proxy,
        "lmu7_height_order_violation": height_proxy,
    }


def lmu8_proxy(phase: Path, run: str, bid: str) -> dict[str, float | None]:
    faces = get_faces(phase, run, bid)
    edges = graph_edges(phase, run, bid)
    shell = shell_diag(phase, run, bid)
    n_wall = fnum(shell.get("n_wall_faces")) or 0.0
    h_range = fnum(shell.get("height_range")) or 1.0
    wall_ground_edges = [e for e in edges if e.get("semantic_pair") in {"WallSurface--GroundSurface", "GroundSurface--WallSurface"}]
    gap_terms: list[float] = []
    for edge in wall_ground_edges:
        fa = faces.get(edge.get("face_a", ""))
        fb = faces.get(edge.get("face_b", ""))
        if not fa or not fb:
            continue
        if fa.get("semantic_type") == "GroundSurface":
            ground, wall = fa, fb
        else:
            wall, ground = fa, fb
        gh = face_heights(ground)
        wh = face_heights(wall)
        if gh.size and wh.size:
            gap = abs(float(np.min(wh)) - float(np.mean(gh)))
            gap_terms.append(max(0.0, gap - 0.05) / max(h_range, 1e-6))
    missing = max(0.0, n_wall - len(wall_ground_edges)) / max(n_wall, 1.0)
    gap_proxy = mean(gap_terms) if gap_terms else None
    open_edges = fnum(shell.get("open_edges")) or 0.0
    nonmanifold = fnum(shell.get("nonmanifold_edges", shell.get("non_manifold_edges"))) or 0.0
    topo_penalty = min(1.0, (open_edges + nonmanifold) / 10.0)
    proxy = (gap_proxy or 0.0) + missing + topo_penalty
    return {
        "lmu8_proxy": proxy,
        "lmu8_wall_ground_edges": float(len(wall_ground_edges)),
        "lmu8_missing_adjacency_frac": missing,
        "lmu8_wall_ground_gap": gap_proxy,
        "lmu8_topology_penalty": topo_penalty,
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sx = math.sqrt(sum(d * d for d in dx))
    sy = math.sqrt(sum(d * d for d in dy))
    if sx <= 1e-12 or sy <= 1e-12:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


def rank(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    return pearson(rank(xs), rank(ys))


def correlation(rows: list[dict[str, Any]], proxy: str, metric: str) -> tuple[float | None, float | None, int]:
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        x = fnum(row.get(proxy))
        y = fnum(row.get(metric))
        if x is not None and y is not None and not (math.isnan(x) or math.isnan(y)):
            xs.append(x)
            ys.append(y)
    return pearson(xs, ys), spearman(xs, ys), len(xs)


def write_design_docs() -> None:
    DESIGN_DOC.parent.mkdir(parents=True, exist_ok=True)
    DESIGN_OUT.parent.mkdir(parents=True, exist_ok=True)
    DESIGN_DOC.write_text(DESIGN_TEXT)
    DESIGN_OUT.write_text(DESIGN_TEXT)


def proxy_rows() -> list[dict[str, Any]]:
    metrics = metric_rows()
    rows: list[dict[str, Any]] = []
    for run, label, phase in ARMS:
        for bid in BIDS:
            metric = metrics.get((run, bid), {})
            ev = load_evidence(phase, run, bid)
            row: dict[str, Any] = {
                "run": run,
                "label": label,
                "bid": bid,
                "status": metric.get("status", "MISSING"),
                "is_B104": int(bid == "B104"),
                "is_B6": int(bid == "B6"),
                "is_roof_complex": int(bid in ROOF_COMPLEX),
                "is_terrain_sensitive": int(bid in TERRAIN_SENSITIVE),
                "n_evidence_points": int(len(ev.get("points", []))) if ev else 0,
            }
            for fn in (lmu5_proxy, lmu6_proxy):
                row.update(fn(ev))
            row.update(lmu7_proxy(phase, run, bid))
            row.update(lmu8_proxy(phase, run, bid))
            for key in [
                "F",
                "roof_cov",
                "wall_cov",
                "ground_cov",
                "support_cov",
                "roof_support_cov",
                "wall_support_cov",
                "ground_support_cov",
                "h_err",
                "vol_ratio",
                "chamfer",
                "open_edges",
                "non_manifold_edges",
            ]:
                row[key] = metric.get(key, "")
            rows.append(row)
    return rows


def write_proxy_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "run",
        "label",
        "bid",
        "status",
        "is_B104",
        "is_B6",
        "is_roof_complex",
        "is_terrain_sensitive",
        "n_evidence_points",
        "lmu5_proxy",
        "lmu5_roof_p10",
        "lmu5_terrain_p90",
        "lmu5_margin",
        "lmu5_violation_frac",
        "lmu6_proxy",
        "lmu6_roof_mismatch",
        "lmu6_wall_mismatch",
        "lmu6_terrain_mismatch",
        "lmu6_gate_rate",
        "lmu6_entropy_mean",
        "lmu7_proxy",
        "lmu7_roof_wall_edges",
        "lmu7_missing_adjacency_frac",
        "lmu7_normal_parallel_violation",
        "lmu7_height_order_violation",
        "lmu8_proxy",
        "lmu8_wall_ground_edges",
        "lmu8_missing_adjacency_frac",
        "lmu8_wall_ground_gap",
        "lmu8_topology_penalty",
        "F",
        "roof_cov",
        "wall_cov",
        "ground_cov",
        "support_cov",
        "roof_support_cov",
        "wall_support_cov",
        "ground_support_cov",
        "h_err",
        "vol_ratio",
        "chamfer",
        "open_edges",
        "non_manifold_edges",
    ]
    write_csv(PROXY_OUT / "lmu5_8_proxy_by_bid.csv", rows, fields)


def summary_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    metric_pairs = [
        "F",
        "roof_cov",
        "wall_cov",
        "ground_cov",
        "support_cov",
        "roof_support_cov",
        "wall_support_cov",
        "ground_support_cov",
        "h_err",
        "vol_ratio",
        "chamfer",
        "open_edges",
        "non_manifold_edges",
    ]
    for proxy in ["lmu5_proxy", "lmu6_proxy", "lmu7_proxy", "lmu8_proxy"]:
        for metric in metric_pairs:
            p, s, n = correlation(rows, proxy, metric)
            out.append({"proxy": proxy, "metric": metric, "pearson": p, "spearman": s, "n": n})
    return out


def mean_by_case(rows: list[dict[str, Any]], proxy: str, flag: str) -> tuple[float | None, float | None]:
    yes = [fnum(r.get(proxy)) for r in rows if r.get(flag) == 1]
    no = [fnum(r.get(proxy)) for r in rows if r.get(flag) == 0]
    yes = [v for v in yes if v is not None]
    no = [v for v in no if v is not None]
    return (mean(yes) if yes else None, mean(no) if no else None)


def recommendation_from_alignment(rows: list[dict[str, Any]], corrs: list[dict[str, Any]]) -> dict[str, str]:
    by_proxy = {p: {} for p in ["lmu5_proxy", "lmu6_proxy", "lmu7_proxy", "lmu8_proxy"]}
    for c in corrs:
        by_proxy[c["proxy"]][c["metric"]] = c
    rec: dict[str, str] = {}
    for proxy, term in [
        ("lmu5_proxy", "Lmu5"),
        ("lmu6_proxy", "Lmu6"),
        ("lmu7_proxy", "Lmu7"),
        ("lmu8_proxy", "Lmu8"),
    ]:
        f_s = by_proxy[proxy].get("F", {}).get("spearman")
        h_s = by_proxy[proxy].get("h_err", {}).get("spearman")
        support_s = by_proxy[proxy].get("support_cov", {}).get("spearman")
        ground_s = by_proxy[proxy].get("ground_cov", {}).get("spearman")
        b6_mean, non_b6_mean = mean_by_case(rows, proxy, "is_B6")
        b104_mean, non_b104_mean = mean_by_case(rows, proxy, "is_B104")
        rc_mean, non_rc_mean = mean_by_case(rows, proxy, "is_roof_complex")
        signal = []
        anti_signal = []
        if f_s is not None and f_s < -0.20:
            signal.append("negative_with_F")
        if f_s is not None and f_s > 0.20:
            anti_signal.append("positive_with_F")
        if h_s is not None and h_s > 0.20:
            signal.append("positive_with_h_err")
        if h_s is not None and h_s < -0.20:
            anti_signal.append("negative_with_h_err")
        if support_s is not None and support_s < -0.20:
            signal.append("negative_with_support")
        if support_s is not None and support_s > 0.20:
            anti_signal.append("positive_with_support")
        if ground_s is not None and ground_s > 0.20:
            anti_signal.append("positive_with_ground_cov")
        if b6_mean is not None and non_b6_mean is not None and b6_mean > non_b6_mean * 1.10:
            signal.append("elevated_on_B6")
        if rc_mean is not None and non_rc_mean is not None and rc_mean > non_rc_mean * 1.10:
            signal.append("elevated_on_roof_complex")
        if b104_mean is not None and non_b104_mean is not None and b104_mean > non_b104_mean * 1.10:
            anti_signal.append("elevated_on_recovered_B104")

        if anti_signal:
            rec[term] = "DEFER"
            rec[f"{term}_signal"] = (
                "proxy_mismatch:" + ",".join(anti_signal)
                + ("; useful_signal:" + ",".join(signal) if signal else "")
            )
            continue

        if term == "Lmu8":
            rec[term] = (
                "DEFER"
                if len(signal) < 3
                else "PROCEED_WITH_STRICT_TERRAIN_GATES"
            )
        elif term == "Lmu7":
            rec[term] = "PROCEED" if len(signal) >= 2 else "DEFER"
        else:
            rec[term] = "PROCEED" if len(signal) >= 1 else "DEFER"
        rec[f"{term}_signal"] = ",".join(signal) if signal else "weak_proxy_signal"
    return rec


def write_alignment_report(rows: list[dict[str, Any]], corrs: list[dict[str, Any]], rec: dict[str, str]) -> None:
    PROXY_OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FC-S6c Lmu5-Lmu8 Proxy/Metric Alignment",
        "",
        "Scope: no-training audit over existing FC-S6 Stage3Algo-v1 + Metric-v1 outputs for A0, A1, A4, A8, B2, and A9.",
        "",
        "Proxy convention: higher proxy means larger predicted incompatibility / risk. A useful proxy should generally correlate negatively with F/coverage/support or positively with h_err/topology errors.",
        "",
        "## Correlation Summary",
        "",
        "| Proxy | Metric | Pearson | Spearman | N |",
        "|---|---|---:|---:|---:|",
    ]
    focus = {"F", "roof_cov", "wall_cov", "ground_cov", "support_cov", "ground_support_cov", "h_err", "vol_ratio", "chamfer", "open_edges", "non_manifold_edges"}
    for c in corrs:
        if c["metric"] not in focus:
            continue
        lines.append(
            f"| {c['proxy']} | {c['metric']} | {fmt(c['pearson'])} | {fmt(c['spearman'])} | {c['n']} |"
        )
    lines.extend([
        "",
        "## Case-Flag Means",
        "",
        "| Proxy | B104 mean | non-B104 mean | B6 mean | non-B6 mean | roof_complex mean | non-roof_complex mean |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for proxy in ["lmu5_proxy", "lmu6_proxy", "lmu7_proxy", "lmu8_proxy"]:
        b104, nb104 = mean_by_case(rows, proxy, "is_B104")
        b6, nb6 = mean_by_case(rows, proxy, "is_B6")
        rc, nrc = mean_by_case(rows, proxy, "is_roof_complex")
        lines.append(f"| {proxy} | {fmt(b104)} | {fmt(nb104)} | {fmt(b6)} | {fmt(nb6)} | {fmt(rc)} | {fmt(nrc)} |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Lmu5 is intended to target roof-terrain height separation. Its proxy should be read primarily against `h_err`, `vol_ratio`, and the B6 flag.",
        "- Lmu6 is a semantic-geometry contradiction proxy. It is most relevant if it tracks F, class coverage, or classwise support.",
        "- Lmu7 and Lmu8 use final Stage3 graph/shell read-out as a no-training proxy for relation hints. Because Stage3 closes many shells by construction, low variation in open/non-manifold metrics weakens these proxies.",
        "- A proxy with positive correlation to F/support is treated as a mismatch because the proxy convention is higher=worse.",
        "- Proxy alignment is a screening tool only. A term that proceeds still requires single-term smoke training before combination.",
        "",
        "## Proxy-Based Term Recommendation",
        "",
    ])
    for term in ["Lmu5", "Lmu6", "Lmu7", "Lmu8"]:
        lines.append(f"- `{term}`: `{rec[term]}` ({rec[term + '_signal']}).")
    (PROXY_OUT / "lmu5_8_proxy_metric_alignment.md").write_text("\n".join(lines) + "\n")


def write_smoke_recommendation(rec: dict[str, str]) -> None:
    proceed = [t for t in ["Lmu5", "Lmu6", "Lmu7", "Lmu8"] if rec[t].startswith("PROCEED")]
    defer = [t for t in ["Lmu5", "Lmu6", "Lmu7", "Lmu8"] if rec[t] == "DEFER"]
    lines = [
        "# FC-S6c Lmu5-Lmu8 Smoke Recommendation",
        "",
        "Decision scope: recommend single-term smoke eligibility only. Do not launch smoke training from this report.",
        "",
        "## Recommended Single-Term Smoke Queue",
        "",
    ]
    if proceed:
        for term in proceed:
            lines.append(f"- `{term}`: proceed to single-term smoke, with design-freeze gates and gradient guard.")
    else:
        lines.append("- No Lmu5-Lmu8 term has enough proxy signal to proceed.")
    lines.extend([
        "",
        "## Deferred Terms",
        "",
    ])
    if defer:
        for term in defer:
            lines.append(f"- `{term}`: defer; proxy signal is weak or terrain/topology risk is not isolated enough.")
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Smoke Constraints",
        "",
        "- One term per smoke arm only.",
        "- Start from the accepted A8 terrain-off Mutual candidate.",
        "- Keep `L_structure` disabled.",
        "- Keep G2 disabled.",
        "- Do not modify Stage3Algo-v1 or Metric-v1.",
        "- Do not enable M7/M8-style relation hints in combination until their single-term smoke passes.",
        "- Enforce gradient ratio guards: Lmu5-Lmu7 <= 5% of base gradient norm; Lmu8 <= 2%.",
        "",
        "## Initial Smoke Order",
        "",
    ])
    order = [t for t in ["Lmu5", "Lmu6", "Lmu7", "Lmu8"] if t in proceed]
    if order:
        for i, term in enumerate(order, 1):
            lines.append(f"{i}. `{term}`")
    else:
        lines.append("No smoke order selected.")
    (PROXY_OUT / "LMU5_8_SMOKE_RECOMMENDATION.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    write_design_docs()
    PROXY_OUT.mkdir(parents=True, exist_ok=True)
    rows = proxy_rows()
    write_proxy_csv(rows)
    corrs = summary_table(rows)
    rec = recommendation_from_alignment(rows, corrs)
    write_alignment_report(rows, corrs, rec)
    write_smoke_recommendation(rec)
    RUN_LOG.write_text(json.dumps({
        "status": "OK",
        "no_training": True,
        "stage3_rerun": False,
        "metric_rerun": False,
        "n_rows": len(rows),
        "recommendation": {k: v for k, v in rec.items() if not k.endswith("_signal")},
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
