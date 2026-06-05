#!/usr/bin/env python3
"""FC-S6c-0 Lmu design-to-formula audit.

Inspection-only report generator. It does not train, launch smoke jobs, call
Stage3, call Metric-v1, enable L_structure, or start G2.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from textwrap import dedent


OUT = Path("results/FC_S6C_lmutual_design_to_formula_audit")
BOUNDARY = {
    "inspection_only": True,
    "training_started": False,
    "smoke_jobs_launched": False,
    "l_structure_enabled": False,
    "g2_started": False,
    "stage3_modified": False,
    "metric_v1_modified": False,
    "gt_roof_type_used_for_loss": False,
    "gt_roof_partition_used_for_loss": False,
    "gt_final_mesh_used_for_loss": False,
    "gt_semantic_surfaces_used_for_loss": False,
}


TERMS = [
    {
        "term": "Lmu1",
        "name": "wall verticality",
        "target_labels": "semantic_faces",
        "final_output_target": "semantic_faces / WallSurface",
        "target_statement": "Lmu1 targets semantic_faces / WallSurface by making wall primitive normals usable for Stage3 wall plane fitting.",
        "precondition": "WallSurface read-out needs wall primitives to have wall-like normals, meaning normals are approximately perpendicular to gravity.",
        "formula": "implemented: Lmu1 = mean_i p_wall_i * (n_i dot e_gravity)^2",
        "formula_matches": "YES, for the wall-normal precondition.",
        "formula_risks": "In full bidirectional mode p_wall is not detached, so false wall probability can either pull non-wall geometry toward wall-like normals or reduce wall probability instead of correcting geometry.",
        "suggested_correction": "For a pure geometry-prior smoke variant, use stopgrad(p_wall). Keep bidirectional mode only when the hypothesis is explicitly semantic-geometry coupling.",
        "semantic_gradient": "yes through p_wall in current full mode",
        "normal_gradient": "yes through dot(n, gravity)^2",
        "center_gradient": "no",
        "confidence_gate_gradient": "no confidence gate in current term",
        "gradient_intended": "partly",
        "gradient_risk": "Bidirectional semantics make interpretation harder; false positives can move geometry.",
        "stopgrad_policy": "Current implementation: no stopgrad in full mode; sem2geo mode detaches p_wall.",
        "gate_logic": "Current active term is effectively always-on for all primitives, weighted by p_wall.",
        "expected_gate_on_rate": "near 100% sample participation, soft-weighted by p_wall",
        "always_off_failure": "Only off if term mask/weight disables it.",
        "always_on_failure": "Always-on soft weighting can act on low-confidence false wall mass.",
        "allowed_inputs_only": "yes: predicted normals, semantic logits, fixed gravity",
        "required_logs": "loss/mutual_wall_vertical, mutual/mass_wall, entropy/wall, grad_ratio/lmu1_base or grad_norm/mutual component",
        "gate_status": "VALID_BUT_NEEDS_CONFIDENCE_SUPPORT_GATE_FOR_NEW_SMOKE",
        "proxy_definition": "wall-normal violation weighted by predicted wall probability; compare with wall_cov and wall_support_cov.",
        "proxy_status": "PROXY_NOT_NEEDED_YET",
        "higher_proxy_risk": "yes",
        "proxy_variation": "expected; existing A2/A8 results already partially cover this term",
        "proxy_alignment": "not re-audited in FC-S6c-0; existing FC-S6 arms give empirical sanity",
        "proxy_issue": "proxy not required before using current A8 candidate because Lmu1 is retained and partially tested",
        "proxy_revision": "If isolated again, compute per-bid wall-normal violation before Stage3 and correlate with wall_cov/wall_support_cov.",
        "primary_metric": "wall_cov",
        "secondary_metric": "wall_support_cov, support_cov",
        "no_regression_gates": "roof_cov, ground_cov, easy/control F, open_edges, non_manifold_edges",
        "case_behavior": "B0/B1/B2/B8/B50 should not regress; roof-complex cases should not lose roof coverage from false wall attraction.",
        "failure_interpretation": "Wall proxy improves but wall_cov/support do not improve means Stage3 wall read-out is not using the corrected primitive normal signal.",
        "decision": "FORMULA_OK_PROCEED_TO_PROXY",
    },
    {
        "term": "Lmu2",
        "name": "roof non-wall prior",
        "target_labels": "semantic_faces",
        "final_output_target": "semantic_faces / RoofSurface",
        "target_statement": "Lmu2 targets semantic_faces / RoofSurface by preventing roof primitives from collapsing into wall-like normal evidence.",
        "precondition": "RoofSurface read-out needs roof primitives to avoid wall-like horizontal normals while allowing valid sloped roof normals.",
        "formula": "implemented: Lmu2 = mean_i p_roof_i * relu(tau - (n_i dot e_gravity)^2)^2",
        "formula_matches": "YES, with tau margin caveat.",
        "formula_risks": "Very steep roofs with low |n dot gravity| can be penalized; p_roof is not detached in full mode, so the term can lower roof probability instead of fixing roof normals.",
        "suggested_correction": "Keep tau conservative and log roof-complex failures. For geometry-prior mode, use stopgrad(p_roof).",
        "semantic_gradient": "yes through p_roof in current full mode",
        "normal_gradient": "yes when (n dot gravity)^2 < tau",
        "center_gradient": "no",
        "confidence_gate_gradient": "no confidence gate in current term",
        "gradient_intended": "partly",
        "gradient_risk": "Can obscure whether improvements come from roof logits or roof geometry; steep roof edge cases may be over-regularized.",
        "stopgrad_policy": "Current implementation: no stopgrad in full mode; sem2geo mode detaches p_roof.",
        "gate_logic": "Current active term is always-on, soft-weighted by p_roof.",
        "expected_gate_on_rate": "near 100% sample participation, active only where roof probability and wall-like normals coincide",
        "always_off_failure": "Only off if term mask/weight disables it.",
        "always_on_failure": "Always-on soft weighting can suppress true steep roof evidence.",
        "allowed_inputs_only": "yes: predicted normals, semantic logits, fixed gravity",
        "required_logs": "loss/mutual_roof_nonwall, mutual/mass_roof, entropy/roof, roof normal quantiles, grad_ratio/lmu2_base",
        "gate_status": "VALID_WITH_STEEP_ROOF_GUARD",
        "proxy_definition": "roof wall-like normal violation weighted by predicted roof probability; compare with roof_cov and roof_support_cov.",
        "proxy_status": "PROXY_NOT_NEEDED_YET",
        "higher_proxy_risk": "yes",
        "proxy_variation": "expected, especially B3/B123/B126",
        "proxy_alignment": "not re-audited in FC-S6c-0; existing A3/A8 results partially cover this term",
        "proxy_issue": "roof-complex evaluator risk can mask term utility",
        "proxy_revision": "If isolated again, report roof-complex split separately and include steep-roof normal-bin diagnostics.",
        "primary_metric": "roof_cov",
        "secondary_metric": "roof_support_cov, roof_complex F",
        "no_regression_gates": "wall_cov, ground_cov, easy/control F, topology",
        "case_behavior": "B3/B123/B126 must not regress; B2/B0/B1 easy sanity should remain stable.",
        "failure_interpretation": "Roof proxy improves but roof_complex F drops means the term is over-regularizing steep/complex roof evidence or Stage3 decomposition dominates.",
        "decision": "FORMULA_OK_PROCEED_TO_PROXY",
    },
    {
        "term": "Lmu3",
        "name": "terrain normal stability",
        "target_labels": "semantic_faces",
        "final_output_target": "semantic_faces / GroundSurface candidate via terrain primitive evidence",
        "target_statement": "Lmu3 targets semantic_faces / GroundSurface indirectly by making terrain primitive normals stable enough for Stage3 ground read-out.",
        "precondition": "GroundSurface read-out needs terrain evidence normals to be horizontal-surface-like, but this does not guarantee correct terrain height.",
        "formula": "implemented: Lmu3 = mean_i p_terrain_i * terrain_gate_i * (1 - abs(n_i dot e_gravity))^2",
        "formula_matches": "YES for the normal-only precondition, NO for height or drift.",
        "formula_risks": "Can create confident wrong-height terrain evidence; p_terrain is not detached in full mode; terrain gate defaults may be none/always-on.",
        "suggested_correction": "Do not use alone as a revised terrain term. Require terrain confidence/support gates and pair with explicit height/drift diagnostics if revisited.",
        "semantic_gradient": "yes through p_terrain in current full mode",
        "normal_gradient": "yes through abs(dot)",
        "center_gradient": "no",
        "confidence_gate_gradient": "no; gate is no_grad when configured",
        "gradient_intended": "partly",
        "gradient_risk": "It can improve normal appearance while worsening terrain class mass or height evidence.",
        "stopgrad_policy": "Current implementation detaches terrain_gate; p_terrain is live unless sem2geo mode is used.",
        "gate_logic": "none/confidence/class_mass/mass_entropy modes exist; default none is soft always-on.",
        "expected_gate_on_rate": "none: near 100% soft participation; configured gates: unknown until logged",
        "always_off_failure": "class_mass or mass_entropy gate can turn the whole term off for a run.",
        "always_on_failure": "none gate can affect low-confidence terrain everywhere.",
        "allowed_inputs_only": "yes: predicted semantic probabilities, normals, fixed gravity",
        "required_logs": "loss/mutual_terrain_normal, mutual/terrain_gate_rate, mutual/mass_terrain, entropy/terrain, terrain normal quantiles",
        "gate_status": "VALID_MECHANISM_BUT_EMPIRICALLY_RISKY",
        "proxy_definition": "terrain normal violation weighted by p_terrain; compare with ground_cov and ground_support_cov.",
        "proxy_status": "PROXY_NOT_NEEDED_YET",
        "higher_proxy_risk": "yes",
        "proxy_variation": "expected",
        "proxy_alignment": "A8 terrain-off being safer means normal stability alone is not enough evidence for retention.",
        "proxy_issue": "normal proxy cannot diagnose height drift",
        "proxy_revision": "If revisited, add terrain y-quantile drift and B104 guard before smoke.",
        "primary_metric": "ground_cov",
        "secondary_metric": "ground_support_cov, terrain y quantiles",
        "no_regression_gates": "B104 ground_cov, easy/control F, support_cov, topology",
        "case_behavior": "B104 must remain recovered; B6/B50 terrain-sensitive cases must not hide drift.",
        "failure_interpretation": "Normal proxy improves but B104 or ground_support regresses means the term is fixing the wrong precondition.",
        "decision": "REJECT_TERM_FOR_NOW",
    },
    {
        "term": "Lmu4",
        "name": "terrain height compactness",
        "target_labels": "semantic_faces;shell_diagnostics",
        "final_output_target": "GroundSurface height evidence and shell height/volume",
        "target_statement": "Lmu4 targets GroundSurface evidence and shell height by stabilizing terrain primitive height without using final GroundSurface GT.",
        "precondition": "Stage3 needs terrain primitive heights to form a stable local ground reference rather than a drifting terrain cluster.",
        "formula": "implemented terrain-side height: mean_i p_terrain_i * gate_i * relu(h_i - H_t)^2, with fixed H_t or terrain quantile reference",
        "formula_matches": "PARTIAL. It is one-sided terrain-below-reference regularization, not true compactness around a robust local terrain cluster.",
        "formula_risks": "Fixed threshold can be wrong; quantile can select the wrong terrain cluster; p_terrain can escape; compaction can damage B104-like terrain evidence.",
        "suggested_correction": "Revise to robust local median/Huber compactness using predicted terrain evidence only, with strict confidence/support gates and stopgrad reference.",
        "semantic_gradient": "yes through p_terrain if not detached",
        "normal_gradient": "no direct normal gradient",
        "center_gradient": "yes through height",
        "confidence_gate_gradient": "no through current gate/reference",
        "gradient_intended": "partly",
        "gradient_risk": "Can push heights or semantic mass in ways that reduce ground_cov.",
        "stopgrad_policy": "Quantile reference is detached; p_terrain is live unless sem2geo mode is used.",
        "gate_logic": "terrain_gate_mode plus terrain reference availability; not support-aware by default",
        "expected_gate_on_rate": "unknown; can be always-on in default none mode",
        "always_off_failure": "class-mass/entropy gate can skip the term globally.",
        "always_on_failure": "none gate can compact wrong low-confidence terrain mass.",
        "allowed_inputs_only": "yes when using predicted terrain evidence only",
        "required_logs": "loss/mutual_terrain_height, mutual/terrain_ref_height, terrain height quantiles, terrain gate rate, B104 terrain y drift",
        "gate_status": "NEEDS_STRICT_SUPPORT_CONFIDENCE_GATE",
        "proxy_definition": "terrain height spread/drift proxy; compare with B104 ground_cov, ground_support_cov, h_err, vol_ratio.",
        "proxy_status": "PROXY_NEEDS_REVISION",
        "higher_proxy_risk": "should be yes",
        "proxy_variation": "current robust variant did not beat A8; more local proxy needed",
        "proxy_alignment": "not sufficient under current global formulation",
        "proxy_issue": "does not distinguish stable terrain plane from wrong terrain cluster",
        "proxy_revision": "Use local terrain median absolute deviation plus B104-specific y-quantile drift from predicted evidence.",
        "primary_metric": "ground_cov",
        "secondary_metric": "ground_support_cov, h_err, vol_ratio",
        "no_regression_gates": "B104 ground_cov/support, easy/control F, open/non-manifold",
        "case_behavior": "B104 is the guard; B6 alone cannot validate it.",
        "failure_interpretation": "If terrain compactness improves proxy but ground_cov drops, the formula is compacting the wrong cluster.",
        "decision": "FORMULA_NEEDS_REVISION",
    },
    {
        "term": "Lmu5",
        "name": "split roof-height relation",
        "target_labels": "shell_diagnostics",
        "final_output_target": "shell_diagnostics / height-volume, with secondary RoofSurface stability",
        "target_statement": "Lmu5 targets shell_diagnostics by keeping roof evidence above a predicted terrain reference so Stage3 height and volume are stable.",
        "precondition": "Roof primitive heights must sit above a reliable terrain evidence reference, without reintroducing terrain-side negative transfer.",
        "formula": "proposed: h_i=-dot(c_i,e_g); H_t=stopgrad(weighted_quantile(h_i | terrain evidence,q=0.90)); Lmu5=mean_i p_roof_i*relu((H_t+m_rt)-h_i)^2",
        "formula_matches": "PARTIAL. It is roof-side only and matches the height-order precondition, but q=0.90 and p_roof live gradient create escape/saturation risks.",
        "formula_risks": "The proxy was zero because existing roof-terrain margins are already positive; p_roof can decrease instead of moving geometry; B6 should not be primary success because it is partly Stage3/evaluator height-sensitive.",
        "suggested_correction": "Use stopgrad(p_roof) for geometry-prior smoke, log roof margin distribution, and revise proxy to signed margin percentile/near-violation rather than hard relu only.",
        "semantic_gradient": "yes if p_roof is live in proposed formula",
        "normal_gradient": "no",
        "center_gradient": "yes through roof height",
        "confidence_gate_gradient": "no; terrain reference and gates should be stopgrad",
        "gradient_intended": "no, not if the hypothesis is roof-side geometry height correction",
        "gradient_risk": "Can lower roof probability instead of fixing roof height; B6 may overstate success.",
        "stopgrad_policy": "Terrain reference must be stopgrad; p_roof should be stopgrad for a geometry-prior smoke.",
        "gate_logic": "terrain evidence count/confidence gate plus finite terrain quantile; no GT surface",
        "expected_gate_on_rate": "unknown; current proxy suggests hard margin violation is almost never active",
        "always_off_failure": "relu margin and q=0.90 can make the term effectively always zero.",
        "always_on_failure": "too-small margin/gate can affect all roof candidates if terrain reference is wrong.",
        "allowed_inputs_only": "yes if using predicted terrain evidence only",
        "required_logs": "loss/mutual_lmu5_roof_height, mutual/lmu5_gate, mutual/lmu5_terrain_ref_height, mutual/lmu5_roof_margin_violation, grad_ratio/lmu5_base",
        "gate_status": "UNVERIFIED_AND_POSSIBLY_EFFECTIVELY_OFF",
        "proxy_definition": "current hard roof-terrain margin violation proxy",
        "proxy_status": "PROXY_NEEDS_REVISION",
        "higher_proxy_risk": "yes by design, but current values are all zero",
        "proxy_variation": "none in FC-S6c proxy audit",
        "proxy_alignment": "not measurable because proxy is saturated at zero",
        "proxy_issue": "zero proxy likely indicates margin/proxy failure, not scientific rejection of height relation",
        "proxy_revision": "Use continuous signed margin, low roof percentile minus terrain high percentile, and near-margin fraction; report B6 as secondary only.",
        "primary_metric": "h_err",
        "secondary_metric": "vol_ratio, roof_cov",
        "no_regression_gates": "B104 ground_cov/support, easy/control F, topology",
        "case_behavior": "B6 can be monitored but not used alone as success; B104 must not regress.",
        "failure_interpretation": "If revised proxy varies but smoke does not improve h_err/vol_ratio, roof height relation is not read out by Stage3 under current algorithm.",
        "decision": "PROXY_NEEDS_REVISION",
    },
    {
        "term": "Lmu6",
        "name": "semantic-geometry calibration",
        "target_labels": "semantic_faces;support_confidence",
        "final_output_target": "semantic_faces and support_confidence",
        "target_statement": "Lmu6 is intended to target semantic_faces and support_confidence by aligning semantic logits with geometry-derived class evidence.",
        "precondition": "High-confidence primitives should not carry contradictory semantic class and geometry cues into Stage3.",
        "formula": "proposed: d_roof=relu(tau-(n dot e_g)^2)^2; d_wall=(n dot e_g)^2; d_terrain=(1-abs(n dot e_g))^2; Lmu6=mean stopgrad(conf_i)*(p_roof d_roof+p_wall d_wall+p_terrain d_terrain)",
        "formula_matches": "NO for semantic calibration. This is a semantic-weighted geometry prior unless geometry is teacher-side and logits are the only target.",
        "formula_risks": "Both semantic logits and geometry receive gradients, so it is unclear whether it calibrates semantics or changes geometry; proxy correlated positively with F/support, suggesting it measured structured evidence quality rather than contradiction risk.",
        "suggested_correction": "For calibration, use KL(stopgrad(s_geom_i) || p_i) or CE from stopgrad geometry pseudo-distribution to semantic logits. For geometry prior, detach p_i and rename the term.",
        "semantic_gradient": "yes",
        "normal_gradient": "yes in proposed formula",
        "center_gradient": "no",
        "confidence_gate_gradient": "confidence is stopgrad",
        "gradient_intended": "no for a semantic-calibration hypothesis",
        "gradient_risk": "Interpretability risk: semantic and geometry can move together and hide mismatch.",
        "stopgrad_policy": "Must choose: semantic calibration = stopgrad geometry teacher; geometry prior = stopgrad p_i. Current design chooses neither.",
        "gate_logic": "confidence/support and entropy thresholds proposed",
        "expected_gate_on_rate": "unknown; must log to avoid selecting only already-good evidence",
        "always_off_failure": "strict confidence/entropy gate can leave no calibration samples.",
        "always_on_failure": "loose gate can force ambiguous/roof-complex samples into wrong pseudo-labels.",
        "allowed_inputs_only": "yes if using predicted normals/probabilities/confidence only",
        "required_logs": "loss/mutual_lmu6_sem_geom, mutual/lmu6_gate_rate, mismatch by class, KL/CE terms, grad_ratio/lmu6_base",
        "gate_status": "UNVERIFIED",
        "proxy_definition": "current semantic-geometry mismatch scalar",
        "proxy_status": "PROXY_TARGET_MISMATCH",
        "higher_proxy_risk": "no under current proxy; it correlated positively with F/support",
        "proxy_variation": "yes, but direction is inverted/mismatched",
        "proxy_alignment": "positive with F/support and ground_cov; weak for h_err",
        "proxy_issue": "proxy likely measures confident structured evidence rather than contradiction",
        "proxy_revision": "Define teacher-side geometry pseudo-label disagreement: CE(stopgrad(geom_class), p) or 1 - p_geom_class for high-confidence geometry bins.",
        "primary_metric": "support_cov",
        "secondary_metric": "roof_cov, wall_cov, ground_cov, classwise support",
        "no_regression_gates": "all_10 F, easy/control F, roof_complex F, support_cov",
        "case_behavior": "B0/B1/B2 should remain stable; roof-complex cases must not be over-calibrated into simpler classes.",
        "failure_interpretation": "If semantic proxy improves but support/F do not, the geometry teacher or calibration target is not aligned with Stage3 read-out.",
        "decision": "TARGET_MISMATCH",
    },
    {
        "term": "Lmu7",
        "name": "weak roof-wall hint",
        "target_labels": "face_graph;shell_diagnostics",
        "final_output_target": "face_graph / roof-wall adjacency and shell roof-wall contact",
        "target_statement": "Lmu7 targets face_graph / roof-wall adjacency by making predicted roof and wall evidence locally compatible before Stage3 shell assembly.",
        "precondition": "Stage3 needs local roof-like evidence near wall-like evidence with compatible contact height and non-parallel normals.",
        "formula": "audited smoke formula: select predicted roof-wall local pairs within radius r using stopgrad neighbor selection; Lmu7=mean stopgrad(g_ij)*stopgrad(p_pair_conf)*relu(d_contact(i,j)-m_rw)^2 + lambda_n*relu(abs(n_roof dot n_wall)-eta)^2",
        "formula_matches": "YES if implemented with predicted evidence neighborhoods only and explicit contact distance.",
        "formula_risks": "False roof-wall pairs can create wrong adjacency pressure; final Stage3 graph closes many shells, so topology metrics alone may not reveal damage.",
        "suggested_correction": "Freeze the explicit pair definition above before smoke. Log valid pair count and pair confidence. Do not use GT roof-wall edges.",
        "semantic_gradient": "optional weak semantic gradient only if p_pair_conf is not detached; recommended first smoke detaches pair confidence",
        "normal_gradient": "yes through normal compatibility if normals are trainable target",
        "center_gradient": "yes through contact distance",
        "confidence_gate_gradient": "no; gates and neighbor selection stopgrad",
        "gradient_intended": "yes with recommended stopgrad gates/pair weights",
        "gradient_risk": "If pair weights are live, the model can escape by lowering roof/wall confidence instead of fixing contact.",
        "stopgrad_policy": "Stopgrad neighbor selection, pair gate, support/confidence weights. Let only local geometry residual receive gradient in first smoke.",
        "gate_logic": "high-confidence roof and wall evidence, support threshold, finite local neighborhood, max pair distance, nonzero valid pair count",
        "expected_gate_on_rate": "nonzero on roof-wall-rich cases; must be logged by bid",
        "always_off_failure": "too-small radius or too-strict support gate can yield zero valid pairs.",
        "always_on_failure": "too-large radius can connect unrelated roof/wall evidence.",
        "allowed_inputs_only": "yes if using predicted evidence, support, confidence, fixed gravity/domain only",
        "required_logs": "loss/mutual_lmu7_roof_wall, mutual/lmu7_gate_rate, mutual/lmu7_valid_pair_count, mutual/lmu7_contact_gap, mutual/lmu7_normal_violation, grad_ratio/lmu7_base",
        "gate_status": "UNVERIFIED_BUT_SPECIFIABLE",
        "proxy_definition": "roof-wall incompatibility proxy from Stage3 face graph/contact/normal risk",
        "proxy_status": "PROXY_READY",
        "higher_proxy_risk": "yes",
        "proxy_variation": "yes; elevated on B6 and roof_complex cases",
        "proxy_alignment": "aligned: negative with F/support and positive with h_err/chamfer",
        "proxy_issue": "proxy uses final Stage3 graph, so smoke must verify it maps back to train-time predicted evidence pairs",
        "proxy_revision": "Add train-time valid-pair count and contact-gap proxy before/after smoke.",
        "primary_metric": "roof_wall adjacency support proxy / roof_complex F",
        "secondary_metric": "roof_cov, wall_cov, support_cov, h_err",
        "no_regression_gates": "open_edges, non_manifold_edges, easy/control F, roof_cov, wall_cov",
        "case_behavior": "B3/B123/B126 are target diagnostics; B0/B1/B2 easy cases must not acquire false roof-wall artifacts.",
        "failure_interpretation": "If Lmu7 proxy improves but topology or roof_complex F regresses, pair selection is too broad or Stage3 read-out is not using the local compatibility signal.",
        "decision": "FORMULA_OK_PROCEED_TO_SINGLE_TERM_SMOKE",
    },
    {
        "term": "Lmu8",
        "name": "weak terrain-wall hint",
        "target_labels": "face_graph;shell_diagnostics",
        "final_output_target": "face_graph / wall-ground adjacency and shell closure",
        "target_statement": "Lmu8 targets wall-ground adjacency and shell closure by making wall-bottom evidence compatible with predicted terrain evidence.",
        "precondition": "Stage3 wall-ground closure needs reliable terrain evidence and a well-defined wall-bottom estimate near that terrain reference.",
        "formula": "proposed: G_t=stopgrad(local terrain height/support estimate); Lmu8=mean_i stopgrad(g_i)*p_wall_i*relu(abs(h_wall_bottom_i-G_t)-m_wg)^2",
        "formula_matches": "PARTIAL. The target is valid, but wall bottom and local terrain reference are not yet well-defined for train-time primitives.",
        "formula_risks": "Can reintroduce terrain negative transfer, especially B104 drift; p_wall can escape; current proxy is zero because Stage3 already reports closed wall-ground adjacency.",
        "suggested_correction": "Define wall-bottom from predicted wall primitive lower height quantile and local terrain support. Keep terrain reference and gate stopgrad. Require B104 guard before any smoke.",
        "semantic_gradient": "yes through p_wall if live",
        "normal_gradient": "no unless wall-bottom depends on geometry normal",
        "center_gradient": "yes through wall bottom height",
        "confidence_gate_gradient": "no; terrain reliability gate should be stopgrad",
        "gradient_intended": "partly, but terrain risk is high",
        "gradient_risk": "Can lower wall probability or move wall bottoms toward unreliable terrain; may revive B104 terrain failure.",
        "stopgrad_policy": "Stopgrad local terrain reference, terrain gate, support weights. Prefer stopgrad(p_wall) for first geometry-only diagnostic if revisited.",
        "gate_logic": "stable terrain evidence, high terrain confidence, low entropy, enough local wall support, finite local pair count",
        "expected_gate_on_rate": "unknown; may be zero under strict terrain-safe gate",
        "always_off_failure": "strict terrain reliability gate or missing wall-bottom estimate can disable the term everywhere.",
        "always_on_failure": "loose gate can force walls to wrong terrain clusters.",
        "allowed_inputs_only": "yes if using predicted terrain/wall evidence only",
        "required_logs": "loss/mutual_lmu8_terrain_wall, mutual/lmu8_gate_rate, mutual/lmu8_valid_pair_count, mutual/lmu8_wall_ground_gap, mutual/lmu8_terrain_ref_height, grad_ratio/lmu8_base",
        "gate_status": "GATE_UNVERIFIED_AND_TERRAIN_RISK_HIGH",
        "proxy_definition": "wall-ground gap proxy from Stage3 graph/shell",
        "proxy_status": "PROXY_GATE_BROKEN",
        "higher_proxy_risk": "yes by design, but current proxy is all zero",
        "proxy_variation": "none in FC-S6c proxy audit",
        "proxy_alignment": "not measurable because Stage3 closes wall-ground adjacency in current outputs",
        "proxy_issue": "proxy uses final closed shell and cannot expose train-time terrain-wall risk",
        "proxy_revision": "Use predicted evidence local wall-bottom to terrain reference gaps before Stage3, plus B104 terrain y-drift and gate-on rate.",
        "primary_metric": "ground_support_cov",
        "secondary_metric": "wall_ground adjacency, ground_cov, support_cov",
        "no_regression_gates": "B104 ground_cov/support, terrain y drift, easy/control F, topology",
        "case_behavior": "B104 is the primary guard; B6/B50 terrain-sensitive cases are secondary.",
        "failure_interpretation": "Any B104 regression means the term reintroduced terrain negative transfer and should be stopped.",
        "decision": "GATE_BROKEN",
    },
]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def bullet(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def write_tables() -> None:
    write_csv(
        OUT / "lmu_target_formula_alignment.csv",
        TERMS,
        [
            "term",
            "name",
            "target_labels",
            "final_output_target",
            "target_statement",
            "formula",
            "formula_matches",
            "formula_risks",
            "suggested_correction",
            "decision",
        ],
    )
    write_csv(
        OUT / "lmu_precondition_table.csv",
        TERMS,
        ["term", "name", "final_output_target", "precondition", "target_statement"],
    )
    write_csv(
        OUT / "lmu_gradient_path_table.csv",
        TERMS,
        [
            "term",
            "name",
            "semantic_gradient",
            "normal_gradient",
            "center_gradient",
            "confidence_gate_gradient",
            "gradient_intended",
            "gradient_risk",
            "stopgrad_policy",
        ],
    )
    write_csv(
        OUT / "lmu_gate_validity_table.csv",
        TERMS,
        [
            "term",
            "name",
            "gate_logic",
            "expected_gate_on_rate",
            "always_off_failure",
            "always_on_failure",
            "allowed_inputs_only",
            "required_logs",
            "gate_status",
        ],
    )
    write_csv(
        OUT / "lmu_proxy_readiness_table.csv",
        TERMS,
        [
            "term",
            "name",
            "proxy_definition",
            "proxy_status",
            "higher_proxy_risk",
            "proxy_variation",
            "proxy_alignment",
            "proxy_issue",
            "proxy_revision",
            "decision",
        ],
    )
    write_csv(
        OUT / "lmu_expected_metric_table.csv",
        TERMS,
        [
            "term",
            "name",
            "primary_metric",
            "secondary_metric",
            "no_regression_gates",
            "case_behavior",
            "failure_interpretation",
        ],
    )


def write_main_report() -> None:
    lines = [
        "# FC-S6c-0 Lmu Design-to-Formula Audit",
        "",
        "Status: inspection-only and analysis-only.",
        "",
        "No training, smoke jobs, L_structure, G2, Stage3 modification, or Metric-v1 modification was performed.",
        "",
        "Core rule used here:",
        "",
        "`final-output target -> evidence-level precondition -> formula -> gradient path -> gate policy -> proxy readiness -> expected Stage3Algo-v1 + Metric-v1 result`",
        "",
        "Terminology: Stage2 uses terrain evidence / terrain primitive class. `GroundSurface` is only the Stage3 final semantic face.",
        "",
        "## Summary Decision",
        "",
        "| Term | Formula/gate/proxy decision | Short reason |",
        "|---|---|---|",
    ]
    short = {
        "Lmu1": "Wall normal formula is valid; bidirectional gradient is a known interpretability risk.",
        "Lmu2": "Roof non-wall formula is valid with steep-roof guard.",
        "Lmu3": "Normal formula is valid but terrain path is empirically risky under FC-S6.",
        "Lmu4": "Current terrain height term is not robust compactness and needs revision.",
        "Lmu5": "Height-order idea is plausible, but current proxy is saturated and p_roof escape is unresolved.",
        "Lmu6": "Current formula is not semantic calibration; it is semantic-weighted geometry prior.",
        "Lmu7": "Only term with target/formula/proxy chain strong enough for single-term smoke, after explicit pair/gate implementation.",
        "Lmu8": "Target is valid but terrain-wall gate/proxy are broken or unverified.",
    }
    for term in TERMS:
        lines.append(f"| {term['term']} {term['name']} | `{term['decision']}` | {short[term['term']]} |")
    lines.extend([
        "",
        "## Per-Term Audit",
        "",
    ])
    for term in TERMS:
        lines.extend([
            f"### {term['term']} {term['name']}",
            "",
            f"Decision: `{term['decision']}`",
            "",
            f"Target validity: {term['target_statement']}",
            "",
            f"Evidence precondition: {term['precondition']}",
            "",
            f"Formula: `{term['formula']}`",
            "",
            f"Formula validity: {term['formula_matches']}",
            "",
            f"Formula risks: {term['formula_risks']}",
            "",
            f"Suggested correction: {term['suggested_correction']}",
            "",
            "Gradient path:",
            "",
            bullet([
                f"semantic logits: {term['semantic_gradient']}",
                f"normals: {term['normal_gradient']}",
                f"centers/heights: {term['center_gradient']}",
                f"confidence/gates: {term['confidence_gate_gradient']}",
                f"intended: {term['gradient_intended']}",
                f"risk: {term['gradient_risk']}",
                f"stopgrad: {term['stopgrad_policy']}",
            ]),
            "",
            f"Gate policy: {term['gate_logic']}",
            "",
            f"Gate validity: {term['gate_status']}; expected gate-on rate: {term['expected_gate_on_rate']}.",
            "",
            f"Proxy readiness: `{term['proxy_status']}`. {term['proxy_issue']}",
            "",
            f"Expected Stage3Algo-v1 + Metric-v1 result: primary `{term['primary_metric']}`, secondary `{term['secondary_metric']}`; no-regression gates: {term['no_regression_gates']}.",
            "",
        ])
    lines.extend([
        "## Boundary Record",
        "",
        "```json",
        json.dumps(BOUNDARY, indent=2),
        "```",
        "",
    ])
    (OUT / "LMU_DESIGN_TO_FORMULA_AUDIT.md").write_text("\n".join(lines))


def write_recommendations() -> None:
    text = dedent(
        """
        # Lmu Revision Recommendations

        ## Formula-Valid Terms

        - `Lmu1` and `Lmu2` are formula-valid as primitive normal priors, but their current full-mode bidirectional gradients should be treated as an interpretability risk. They remain acceptable in the current A8 candidate because they have already been exercised by FC-S6 arms.
        - `Lmu3` is formula-valid only for terrain normal stability. It is not a full GroundSurface solution and should not be reintroduced as a standalone terrain term under the current evidence.
        - `Lmu7` is formula-valid only after freezing an explicit predicted-evidence roof-wall pair definition, contact-gap residual, and support/confidence gates.

        ## Terms Needing Revision

        - `Lmu4` needs a robust local terrain compactness formula. The current one-sided threshold/quantile height term can compact the wrong terrain cluster.
        - `Lmu5` needs proxy and gradient-path revision. Use `stopgrad(p_roof)` for a geometry-prior smoke, and replace the saturated hard violation proxy with continuous signed roof-terrain margin statistics.
        - `Lmu6` needs a target rewrite. If it is semantic calibration, use a teacher-side geometry pseudo-distribution with KL/CE into semantic logits. If it is a geometry prior, detach semantic probabilities and rename the hypothesis.
        - `Lmu8` needs gate and proxy revision before smoke. The current Stage3 graph proxy is zero because Stage3 already closes wall-ground adjacency, and the train-time terrain-wall pair definition is not verified.

        ## Gate Issues

        - `Lmu1`/`Lmu2` are currently soft always-on. This is acceptable for existing A8 continuation but not ideal for a new claim; log class confidence/support if revisited.
        - `Lmu3`/`Lmu4` terrain gates are the main risk path. Terrain terms must have confidence/support/entropy gates plus B104 terrain y-drift logs.
        - `Lmu5` may be effectively always off because the hard roof-terrain margin is already satisfied.
        - `Lmu7` gate is unverified but specifiable; valid pair count is the key first log.
        - `Lmu8` gate is unverified and may be either always off under strict terrain reliability or unsafe if loose.

        ## Proxy Issues

        - `Lmu5`: `PROXY_NEEDS_REVISION`; all-zero proxy means no decision can be made.
        - `Lmu6`: `PROXY_TARGET_MISMATCH`; positive correlation with F/support means the current proxy is likely measuring quality rather than contradiction.
        - `Lmu7`: `PROXY_READY`; it aligned with risk, but smoke must verify the train-time pair signal.
        - `Lmu8`: `PROXY_GATE_BROKEN`; zero proxy and closed Stage3 shells make it unusable.
        """
    ).strip() + "\n"
    (OUT / "lmu_revision_recommendations.md").write_text(text)


def write_next_step() -> None:
    text = dedent(
        """
        # Lmu Next Step Decision

        ## Term Decisions

        | Term | Decision | Next action |
        |---|---|---|
        | Lmu1 | FORMULA_OK_PROCEED_TO_PROXY | Keep as part of A8; no new smoke required now. |
        | Lmu2 | FORMULA_OK_PROCEED_TO_PROXY | Keep as part of A8; no new smoke required now. |
        | Lmu3 | REJECT_TERM_FOR_NOW | Do not reintroduce terrain normal alone; A8 terrain-off remains safer. |
        | Lmu4 | FORMULA_NEEDS_REVISION | Redesign robust local terrain compactness before proxy/smoke. |
        | Lmu5 | PROXY_NEEDS_REVISION | Revise roof-terrain margin proxy and detach policy before smoke. |
        | Lmu6 | TARGET_MISMATCH | Rewrite as true semantic calibration or rename as geometry prior before proxy/smoke. |
        | Lmu7 | FORMULA_OK_PROCEED_TO_SINGLE_TERM_SMOKE | Only term allowed to proceed to single-term smoke, after implementing the explicit predicted-evidence pair/gate formula audited here. |
        | Lmu8 | GATE_BROKEN | Fix terrain-wall gate/pair/proxy before any smoke. |

        ## Required Answers

        1. Formula-valid terms: `Lmu1`, `Lmu2`, `Lmu3` for normal-only terrain precondition, and `Lmu7` with explicit predicted-evidence roof-wall pair/gate definition.
        2. Terms needing revision before proxy/smoke: `Lmu4`, `Lmu5`, `Lmu6`, `Lmu8`.
        3. Broken or unverified gates: `Lmu5` may be effectively off, `Lmu7` valid-pair gate is unverified, and `Lmu8` terrain-wall gate is broken/unverified. `Lmu3`/`Lmu4` terrain gates are empirically risky.
        4. Terms allowed to proceed to single-term smoke: `Lmu7` only.
        5. Yes, `Lmu7` remains the only smoke-ready term after formula audit, but only as a single-term smoke with explicit predicted-evidence pair selection, support/confidence gates, valid-pair logs, and the 5% gradient-ratio guard.
        6. `Lmu5`, `Lmu6`, and `Lmu8` are not scientifically rejected. They are deferred because of formula, proxy, or gate issues.
        7. The current revised `L_mutual` candidate remains `A8`. `A8+Lmu7` is only the next single-term smoke hypothesis, not the accepted candidate yet.
        8. `L_structure` is still blocked because no post-A8 Lmu completion smoke has been run or accepted. Starting `L_structure` now would mix unresolved Mutual completion with structural loss effects.

        ## No-Overclaim Boundary

        This audit does not claim `Lmu7` is useful. It only says `Lmu7` is the only term whose research hypothesis, proposed formula, proxy direction, and expected Stage3 read-out are coherent enough to justify a single-term smoke test.
        """
    ).strip() + "\n"
    (OUT / "lmu_next_step_decision.md").write_text(text)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_tables()
    write_main_report()
    write_recommendations()
    write_next_step()
    (OUT / "audit_boundary.json").write_text(json.dumps(BOUNDARY, indent=2) + "\n")


if __name__ == "__main__":
    main()
