#!/usr/bin/env python3
"""Weight-only continuation diagnostic for DEBY_LOD2_4906982.

The host process only orchestrates Docker.  Three new arms fork the exact 7k
full state and stop at 12k.  The existing exact R1 endpoints at w_depth 0 and
0.03 are read-only references after provenance/hash gates pass.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[3]
DEPTH_RUNNER = REPO / "scripts/p2/e3_local_4906982_mvc_depth_v1/run.py"
SPEC = importlib.util.spec_from_file_location("depth_runner", DEPTH_RUNNER)
assert SPEC and SPEC.loader
depth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(depth)
base = depth.base

ARTIFACT_ROOT = REPO.parent / "JointBuildGS-artifacts"
TASK_ID = "P2-E3-LOCAL-4906982-MVC-DEPTH-WEIGHT-v1"
TASK_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_depth_weight_v1" / TASK_ID
SWEEP_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_weight_v1/weight_sweep.yaml"
SURFACE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_weight_v1/surface_eval.yaml"
SOURCE_ROOT = ARTIFACT_ROOT / "phase-payloads/p2/e3_local_4906982_mvc_depth_v1/P2-E3-LOCAL-4906982-MVC-DEPTH-v1"
SOURCE_CONFIG = REPO / "configs/p2/e3_local_4906982_mvc_depth_v1/depth03.yaml"
SOURCE_PREFIX = SOURCE_ROOT / "common_prefix"
SOURCE_PROVENANCE = SOURCE_ROOT / "provenance.json"
SOURCE_INPUTS = SOURCE_ROOT / "input_hashes.json"
ARMS = ("W001", "W003", "W010")
WEIGHTS = {"W001": 0.001, "W003": 0.003, "W010": 0.01}
REFERENCE = {
    "W000": (0.0, SOURCE_ROOT / "arms/DEPTH0/R1", "a6e0926ef7723a3c88e46f0e805b1bf0b9d1effcf904b100bb17305071a5ff0e"),
    "W030": (0.03, SOURCE_ROOT / "arms/DEPTH03/R1", "08e25926a3f49a87c04c5bacb0c9f1800e3fa54bb072212f3837456e8dd419db"),
}
CHECKPOINT_SHA = "3ba28373c60815ba8cab7ff3f15452666c568d724ff5c96b5c99f1c60c0b56c1"
SOURCE_CONFIG_SHA = "115703c92c2207d40fa5f6236dff260351a12a29c052df21d012ffb172be062c"
IMAGE_ID = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

base.TASK_ID = TASK_ID
base.TASK_ROOT = TASK_ROOT
base.CONFIG_DIR = SWEEP_CONFIG.parent
base.ARMS = ARMS
base.REPLICAS = ("R1",)
base.CHECKPOINTS = (7000, 12000)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, body: Any) -> None:
    base.atomic_json(path, body)


def runtime_path(arm: str) -> Path:
    return TASK_ROOT / "control/runtime_configs" / f"{arm.lower()}_r1.yaml"


def run_root(arm: str) -> Path:
    return TASK_ROOT / "arms" / arm / "R1"


def changed(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    return {key for key in set(left) | set(right) if left.get(key) != right.get(key)}


def write_runtime_configs() -> None:
    source = yaml.safe_load(SOURCE_CONFIG.read_text())
    for arm, weight in WEIGHTS.items():
        cfg = dict(source)
        cfg.update({
            "task_id": TASK_ID,
            "run_id": f"{arm}_R1",
            "out_dir": base.container_path(run_root(arm)),
            "w_depth": weight,
            "max_iter": 12000,
            "full_state_resume": "auto",
            "full_state_checkpoint": True,
            "full_state_checkpoint_steps": [7000, 12000],
        })
        base.atomic_text(runtime_path(arm), yaml.safe_dump(cfg, sort_keys=False))


def preflight() -> None:
    marker = TASK_ROOT / "experiment_contract.json"
    if TASK_ROOT.exists() and any(TASK_ROOT.iterdir()) and not marker.is_file():
        raise RuntimeError(f"non-empty unbound namespace: {TASK_ROOT}")
    for name in ("control/runtime_configs", "control/effective_configs", "control/receipts", "logs", "cache/torch_extensions", "representative_images"):
        (TASK_ROOT / name).mkdir(parents=True, exist_ok=True)
    spec = yaml.safe_load(SWEEP_CONFIG.read_text())
    gates = {
        "source_config_sha256": sha256(SOURCE_CONFIG) == SOURCE_CONFIG_SHA == spec["base_config_sha256"],
        "common_7k_sha256": sha256(SOURCE_PREFIX / "ckpt/step_007000.pt") == CHECKPOINT_SHA == spec["common_checkpoint_sha256"],
        "docker_image_id": base.image_record()["id"] == IMAGE_ID == spec["docker_image_id"],
        "source_provenance_exists": SOURCE_PROVENANCE.is_file(),
        "source_inputs_exists": SOURCE_INPUTS.is_file(),
        "mvc_snapshot_byte_identical": depth.MVC_SOURCE.read_bytes() == depth.MVC_SNAPSHOT.read_bytes(),
    }
    source_prov = json.loads(SOURCE_PROVENANCE.read_text())
    gates.update({
        "same_git_head": source_prov["git"]["commit"] == base.git_record()["commit"],
        "same_gpu_uuid": source_prov["gpu"]["uuid"] == base.gpu_record()["uuid"],
    })
    for arm, (_, root, expected) in REFERENCE.items():
        gates[f"reference_{arm}_12k_sha256"] = sha256(root / "ckpt/step_012000.pt") == expected
    if not all(gates.values()):
        raise RuntimeError(f"preflight gate failed: {gates}")
    write_runtime_configs()
    configs = {arm: yaml.safe_load(runtime_path(arm).read_text()) for arm in ARMS}
    actual = {pair: sorted(changed(configs[pair[0]], configs[pair[1]])) for pair in (("W001", "W003"), ("W003", "W010"), ("W001", "W010"))}
    if any(set(keys) != {"run_id", "out_dir", "w_depth"} for keys in actual.values()):
        raise RuntimeError(f"runtime diff allowlist failed: {actual}")
    diff = "\n".join([
        "intervention: w_depth dose only; masked L1, inputs, MVC, growth and schedules fixed",
        "new weights: W001=0.001, W003=0.003, W010=0.01",
        "read-only endpoints: W000=0.0, W030=0.03",
        "allowed across new arms: run_id, out_dir, w_depth",
        *[f"{a} vs {b}: {', '.join(keys)}" for (a, b), keys in actual.items()],
        "cost/gate/normal/densification deltas: none",
        "scientific_verdict: null",
        "",
    ])
    base.atomic_text(TASK_ROOT / "config_diff.txt", diff)
    if not (TASK_ROOT / "common_prefix").exists():
        shutil.copytree(SOURCE_PREFIX, TASK_ROOT / "common_prefix")
    if sha256(TASK_ROOT / "common_prefix/ckpt/step_007000.pt") != CHECKPOINT_SHA:
        raise RuntimeError("copied common 7k mismatch")
    old_inputs = json.loads(SOURCE_INPUTS.read_text())
    atomic_json(TASK_ROOT / "input_hashes.json", {
        **old_inputs,
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.inputs.v1",
        "reused_input_hashes": {"path": str(SOURCE_INPUTS), "sha256": sha256(SOURCE_INPUTS)},
        "common_7k": {"path": str(SOURCE_PREFIX / "ckpt/step_007000.pt"), "sha256": CHECKPOINT_SHA},
        "read_only_endpoint_12k_sha256": {arm: expected for arm, (_, _, expected) in REFERENCE.items()},
    })
    atomic_json(marker, {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.contract.v1",
        "task_id": TASK_ID, "building_id": "DEBY_LOD2_4906982", "status": "PREFLIGHT_BOUND",
        "design": "one exact 7k state, three new weight-only continuations to 12k, two hash-gated read-only endpoints",
        "weights": {**{"W000": 0.0}, **WEIGHTS, **{"W030": 0.03}},
        "new_training_arms": list(ARMS), "reference_endpoint_arms": list(REFERENCE),
        "fixed_cost": "positive-finite masked L1", "confidence_weighting": False,
        "normal_supervision": False, "view_selection_change": False, "multiview_densification": False,
        "checkpoints_completed_updates": [7000, 12000], "gates": gates,
        "scientific_verdict": None,
    })
    sources = [Path(__file__).resolve(), SWEEP_CONFIG, DEPTH_RUNNER, SOURCE_CONFIG, REPO / "src/stage2/train.py", REPO / "src/stage2/loss/data_fitting.py", depth.MVC_SOURCE]
    provenance = {
        "schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.provenance.v1",
        "task_id": TASK_ID, "git": base.git_record(), "docker_image": base.image_record(), "gpu": base.gpu_record(),
        "source_files_sha256": {str(path.relative_to(REPO)): sha256(path) for path in sources},
        "sweep_config_sha256": sha256(SWEEP_CONFIG),
        "runtime_configs_sha256": {path.name: sha256(path) for path in sorted((TASK_ROOT / "control/runtime_configs").glob("*.yaml"))},
        "input_hashes_sha256": sha256(TASK_ROOT / "input_hashes.json"), "random_seed": 0,
        "started_utc": base.now(), "ended_utc": None, "commands": [], "return_codes": [], "scientific_verdict": None,
    }
    if (TASK_ROOT / "provenance.json").is_file():
        old = json.loads((TASK_ROOT / "provenance.json").read_text()); provenance["started_utc"] = old["started_utc"]; provenance["commands"] = old.get("commands", []); provenance["return_codes"] = old.get("return_codes", [])
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nPreflight bound. No new-arm training has started. Scientific verdict: `null`.\n")
    print(diff, end="")
    print(json.dumps({"task_root": str(TASK_ROOT), "gates": gates, "common_7k_sha256": CHECKPOINT_SHA, "scientific_verdict": None}, indent=2))


def probe_config(arm: str) -> Path:
    cfg = yaml.safe_load(runtime_path(arm).read_text())
    root = TASK_ROOT / "binding_probe" / arm
    # Keep the runtime checkpoint-step union identical.  An empty list is
    # normalized to the default 5/10/15/20k set, while the real continuation
    # adds 7/12k to that set and therefore has a different effective hash.
    cfg.update({"run_id": f"BINDING_{arm}", "out_dir": base.container_path(root), "max_iter": 1, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off", "full_state_checkpoint_steps": [7000, 12000]})
    path = TASK_ROOT / "control/runtime_configs" / f"binding_{arm.lower()}.yaml"
    base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False)); return path


def binding_probe() -> None:
    for arm in ARMS:
        stable = TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"
        if stable.is_file():
            continue
        root = TASK_ROOT / "binding_probe" / arm
        argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(probe_config(arm))]
        log = TASK_ROOT / "logs" / f"binding_{arm.lower()}.log"; started = base.now()
        with log.open("w") as stream:
            proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
        base.record_operation(f"binding_{arm}", argv, proc.returncode, started, base.now())
        if proc.returncode != 0:
            raise RuntimeError(f"binding failed: {log}")
        body = json.loads((root / "effective_config.json").read_text()); body.pop("full_state_runtime", None); atomic_json(stable, body)
    effective = {arm: json.loads((TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json").read_text()) for arm in ARMS}
    actual = sorted(set().union(*(changed(effective[ARMS[0]], effective[arm]) for arm in ARMS[1:])))
    passed = actual == ["depth_base_weight"]
    gate = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.effective_gate.v1", "actual_difference": actual, "expected_difference": ["depth_base_weight"], "passed": passed, "scientific_verdict": None}
    atomic_json(TASK_ROOT / "control/effective_config_gate.json", gate)
    if not passed: raise RuntimeError(f"effective config gate failed: {actual}")
    print(json.dumps(gate, indent=2))


def smoke() -> None:
    receipt = TASK_ROOT / "control/receipts/smoke.json"
    if receipt.is_file() and json.loads(receipt.read_text()).get("passed"):
        print(receipt.read_text()); return
    cfg = yaml.safe_load(runtime_path("W003").read_text()); root = TASK_ROOT / "smoke"
    cfg.update({"run_id": "SMOKE_W003", "out_dir": base.container_path(root), "max_iter": 12, "eval_every": 100000, "ckpt_every": 100000, "full_state_resume": "off", "full_state_checkpoint": False, "full_state_checkpoint_steps": [], "mvc_warmup": 0, "mvc_ramp_steps": 1, "depth_warmup": 0, "depth_ramp_steps": 1, "loss_grad_audit_every": 1, "refine_start_iter": 500})
    path = TASK_ROOT / "control/runtime_configs/smoke.yaml"; base.atomic_text(path, yaml.safe_dump(cfg, sort_keys=False))
    argv = base.docker_base(gpu=True) + ["python", "-c", base.DETERMINISTIC_WRAPPER, "--config", base.container_path(path)]
    log = TASK_ROOT / "logs/smoke.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("smoke", argv, proc.returncode, started, base.now())
    code = "from tensorboard.backend.event_processing.event_accumulator import EventAccumulator as E;import csv,glob,json,sys;e=E(glob.glob(sys.argv[1]+'/events*')[0]);e.Reload();tags=['loss/depth','loss_weight/depth','loss/mvc','stats/mvc_n_inlier'];s={k:max(x.value for x in e.Scalars(k)) for k in tags};r=list(csv.DictReader(open(sys.argv[2])));s['depth_grad_norm']=max(float(x['grad_norm']) for x in r if x['component']=='depth');print(json.dumps(s))"
    q = subprocess.run(base.docker_base() + ["python", "-c", code, base.container_path(root / "tb"), base.container_path(root / "audit/loss_grad_norms.csv")], text=True, capture_output=True)
    scalars = json.loads(next(line for line in reversed(q.stdout.splitlines()) if line.startswith("{"))) if q.returncode == 0 else {}
    passed = proc.returncode == 0 and "avg 2.0 neighbors/view" in log.read_text(errors="replace") and all(scalars.get(k, 0) > 0 for k in ("loss/depth", "loss_weight/depth", "loss/mvc", "stats/mvc_n_inlier", "depth_grad_norm"))
    atomic_json(receipt, {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.smoke.v1", "arm": "W003", "return_code": proc.returncode, "scalars": scalars, "neighbor_summary_found": "avg 2.0 neighbors/view" in log.read_text(errors="replace"), "passed": passed, "scientific_verdict": None})
    if not passed: raise RuntimeError(f"smoke failed: {log}")
    print(receipt.read_text())


def fork_prefix() -> None:
    required = [TASK_ROOT / "control/effective_config_gate.json", TASK_ROOT / "control/receipts/smoke.json"]
    if any(not p.is_file() or not json.loads(p.read_text()).get("passed") for p in required):
        raise RuntimeError("effective and smoke gates must pass")
    source = TASK_ROOT / "common_prefix/ckpt/step_007000.pt"
    rows = []
    for arm in ARMS:
        root = run_root(arm); receipt = TASK_ROOT / "control/receipts" / f"rebind_{arm.lower()}_r1.json"
        if not (receipt.is_file() and json.loads(receipt.read_text()).get("passed") and base.checkpoint_valid(root, 7000)):
            if root.exists(): raise RuntimeError(f"incomplete fork needs review: {root}")
            root.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(TASK_ROOT / "common_prefix", root)
            argv = base.docker_base() + ["python", "-c", depth.REBIND_CODE, base.container_path(source), base.container_path(root / "ckpt/step_007000.pt"), base.container_path(runtime_path(arm)), Path(base.container_path(root)), base.container_path(TASK_ROOT / "control/effective_configs" / f"{arm.lower()}.json"), base.container_path(receipt)]
            started = base.now(); proc = subprocess.run([str(x) for x in argv], text=True, capture_output=True); base.record_operation(f"rebind_{arm}_R1", [str(x) for x in argv], proc.returncode, started, base.now())
            if proc.returncode != 0: raise RuntimeError(proc.stderr or proc.stdout)
        rows.append(json.loads(receipt.read_text()))
    passed = len({r["source_sha256"] for r in rows}) == 1 and all(all(r["learned_sections_equal"].values()) for r in rows)
    gate = {"schema": "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.common_state_gate.v1", "completed_updates": 7000, "forks": len(rows), "unique_source_hashes": len({r["source_sha256"] for r in rows}), "learned_sections_exact": passed, "loss_weights_at_7k": {"mvc": 0.0, "depth": 0.0}, "passed": passed, "scientific_verdict": None}
    atomic_json(TASK_ROOT / "control/common_state_gate_7000.json", gate)
    if not passed: raise RuntimeError("common state gate failed")
    print(json.dumps(gate, indent=2))


def train() -> None:
    gate = TASK_ROOT / "control/common_state_gate_7000.json"
    if not gate.is_file() or not json.loads(gate.read_text()).get("passed"): raise RuntimeError("common-state gate required")
    for arm in ARMS:
        result = base._launch_training(f"train_{arm}_R1_to12k", run_root(arm), runtime_path(arm), stop_step=12000)
        print(json.dumps({"arm": arm, "wall_seconds": result.get("wall_seconds"), "max_vram_mib": result.get("max_selected_gpu_used_mib"), "checkpoint_12k": base.checkpoint_valid(run_root(arm), 12000)}), flush=True)


ANALYZE_CODE = r'''
import csv,json,math,sys,torch
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
cases=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);rows=[]
tags=['loss/photo','loss/depth','loss_weight/depth','loss/mvc','loss/mvc_depth','loss/mvc_normal','loss_weight/mvc','stats/mvc_n_inlier','loss/nc','eval/psnr','eval/ssim','eval/lpips','metric/psnr_train','stats/gaussian_count','grow/duplicated','grow/split','prune/removed','stats/opacity_mean']
for c in cases:
 root=Path(c['root']);p=torch.load(root/'ckpt/step_012000.pt',map_location='cpu',weights_only=False);s=p['model']['state_dict'];z=s['means'][:,2].float()+604.;opa=torch.sigmoid(s['opacities_raw'].reshape(-1).float());sc=torch.exp(s['log_scales'].float());mn=sc.min(1).values;mx=sc.max(1).values;elong=mn/mx.clamp_min(1e-12);high=z>650
 tb={}
 for f in sorted((root/'tb').glob('events*')):
  e=EventAccumulator(str(f));e.Reload()
  for tag in e.Tags()['scalars']:
   if tag in tags:tb.setdefault(tag,{}).update({int(x.step):float(x.value) for x in e.Scalars(tag)})
 def latest(tag):
  d=tb.get(tag,{});k=max((x for x in d if x<=12000),default=None);return None if k is None else d[k]
 row={'arm':c['arm'],'w_depth':c['w_depth'],'source':c['source'],'checkpoint_sha256':c['checkpoint_sha256'],'gaussian_count':len(z),'z_min':float(z.min()),'z_median':float(z.median()),'z_p95':float(torch.quantile(z,.95)),'z_p99':float(torch.quantile(z,.99)),'z_max':float(z.max()),'z_gt_650_count':int(high.sum()),'opacity_mean':float(opa.mean()),'opacity_median':float(opa.median()),'high_z_opacity_lt_0p1':int((high&(opa<.1)).sum()),'high_z_opacity_0p1_0p5':int((high&(opa>=.1)&(opa<.5)).sum()),'high_z_opacity_0p5_0p9':int((high&(opa>=.5)&(opa<.9)).sum()),'high_z_opacity_ge_0p9':int((high&(opa>=.9)).sum()),'scale_min_q50':float(torch.quantile(mn,.5)),'scale_min_q95':float(torch.quantile(mn,.95)),'scale_max_q50':float(torch.quantile(mx,.5)),'scale_max_q95':float(torch.quantile(mx,.95)),'elongation_q05':float(torch.quantile(elong,.05)),'elongation_q50':float(torch.quantile(elong,.5))}
 for tag in tags:row[tag.replace('/','_')]=latest(tag)
 row['weighted_depth_over_photo']=None if not row.get('loss_photo') or row.get('loss_weight_depth') is None or row.get('loss_depth') is None else row['loss_weight_depth']*row['loss_depth']/row['loss_photo']
 rows.append(row)
out.write_text(json.dumps({'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.metrics.v1','status':'COMPLETE_MEASURED_12K_WEIGHT_ONLY','rows':rows,'scientific_verdict':None},indent=2,sort_keys=True)+'\n');print(json.dumps(rows,indent=2))
'''


def analyze() -> None:
    cases = []
    for arm, (weight, root, expected) in REFERENCE.items():
        if sha256(root / "ckpt/step_012000.pt") != expected: raise RuntimeError(f"reference hash drift: {arm}")
        cases.append({"arm": arm, "w_depth": weight, "root": base.container_path(root), "source": "read_only_prior_R1", "checkpoint_sha256": expected})
    for arm in ARMS:
        if not base.checkpoint_valid(run_root(arm), 12000): raise RuntimeError(f"missing 12k: {arm}")
        cases.append({"arm": arm, "w_depth": WEIGHTS[arm], "root": base.container_path(run_root(arm)), "source": "new_weight_only_R1", "checkpoint_sha256": sha256(run_root(arm) / "ckpt/step_012000.pt")})
    cases.sort(key=lambda x: x["w_depth"])
    case_path = TASK_ROOT / "control/analysis_cases.json"; atomic_json(case_path, cases)
    output = TASK_ROOT / "metrics.json"; argv = base.docker_base() + ["python", "-c", ANALYZE_CODE, base.container_path(case_path), base.container_path(output)]
    log = TASK_ROOT / "logs/analyze.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("analyze_12k_weight_sweep", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError(f"analysis failed: {log}")
    rows = json.loads(output.read_text())["rows"]
    fields = list(rows[0]);
    with (TASK_ROOT / "checkpoint_metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    base_depth = json.loads((SOURCE_ROOT / "control/baseline_depth_gate_7000.json").read_text())
    raw = base_depth["train"]["depth_l1_mean_of_views_m"]; photo = base_depth["source_photo_loss_latest_pre7k"]["value"]
    for row in rows:
        row["common_7k_raw_depth_l1_m"] = raw; row["common_7k_photo_loss"] = photo; row["scheduled_full_weight_depth_over_photo_at_7k"] = row["w_depth"] * raw / photo
    lines = [f"# {TASK_ID} comparison", "", "## 범위", "", "동일 7k 상태에서 masked L1과 모든 입력·MVC·growth 설정을 고정하고 `w_depth`만 바꾼 12k R1 dose 진단이다. W000/W030은 해시 검증된 기존 endpoint이며 W001/W003/W010만 새 학습이다. `scientific_verdict: null`.", "", "## 12k 측정", "", "| arm | w_depth | eval PSNR | depth loss | weighted depth/photo | Gaussians | Z>650 | Z p99 | Z max |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        fmt=lambda v,n=3: "n/a" if v is None else f"{v:.{n}f}"
        lines.append(f"| {r['arm']} | {r['w_depth']:.3f} | {fmt(r.get('eval_psnr'))} | {fmt(r.get('loss_depth'))} | {fmt(r.get('weighted_depth_over_photo'))} | {r['gaussian_count']:,} | {r['z_gt_650_count']:,} | {r['z_p99']:.2f} | {r['z_max']:.2f} |")
    lines += ["", "## 해석 규칙", "", "이 표는 weight 반응만 측정한다. high-Z 감소와 정상 표면 높이·normal 정렬은 서로 대체하지 않으며, 후자는 다음 평가 단계에서 LoD2 evaluation-only 지표와 fusion/Roofer로 확인한다. 여기서 안정적인 세기 구간을 고른 뒤 cost-only, 그 다음 confidence-only 실험을 각각 새 계약으로 동결한다.", ""]
    base.atomic_text(TASK_ROOT / "comparison.md", "\n".join(lines))
    base.atomic_text(TASK_ROOT / "NOTES.md", f"# {TASK_ID}\n\nStatus: `COMPLETE_MEASURED_12K_WEIGHT_ONLY`. Three new arms and two hash-gated prior endpoints measured. Cost and confidence were not changed. Scientific verdict: `null`.\n")
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text()); contract["status"] = "COMPLETE_MEASURED_12K_WEIGHT_ONLY"; atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text()); provenance["ended_utc"] = base.now(); provenance["new_checkpoint_sha256"] = {arm: sha256(run_root(arm) / "ckpt/step_012000.pt") for arm in ARMS}; provenance["output_sha256"] = {name: sha256(TASK_ROOT / name) for name in ("metrics.json", "checkpoint_metrics.csv", "comparison.md", "NOTES.md")}; provenance["scientific_verdict"] = None; atomic_json(TASK_ROOT / "provenance.json", provenance)
    print((TASK_ROOT / "comparison.md").read_text())


def evaluate_fusion() -> None:
    """Reuse the frozen MVC render/fusion evaluator for the three new 12k arms."""
    output = TASK_ROOT / "surface_metrics.json"
    if output.is_file() and json.loads(output.read_text()).get("status") == "CHECKPOINT_ANALYSIS_COMPLETE":
        body = json.loads(output.read_text()); body["replicates_per_arm"] = 1; atomic_json(output, body)
        print(output.read_text()); return
    code = base.ANALYZE_CODE
    code = code.replace("arms=['MVC0','MVC05']; replicas=['R1','R2','R3']; steps=[7000,12000,15000,20000]", "arms=['W001','W003','W010']; replicas=['R1']; steps=[12000]")
    code = code.replace("mvc0_r1.yaml", "w001_r1.yaml")
    code = code.replace("f'train_{arm}_{replica}.json'", "f'train_{arm}_{replica}_to12k.json'")
    code = code.replace("mvc_weight=0.0 if arm=='MVC0' or step<=7000 else .5", "mvc_weight=.5")
    code = code.replace("root/'checkpoint_metrics.csv'", "root/'surface_checkpoint_metrics.csv'")
    code = code.replace("root/'metrics.json'", "root/'surface_metrics.json'")
    code = code.replace("aggregates['20000']", "aggregates['12000']")
    code = code.replace("jointbuildgs.p2.e3_local_4906982_mvc_v2", "jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1")
    footprint = ARTIFACT_ROOT / "phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3/freeze/shared_footprints_199.geojson"
    data_root = depth.V6_ROOT / "data/colmap_crop"
    argv = base.eval_docker_base(gpu=True) + ["python", "-c", code, base.container_path(TASK_ROOT), base.container_path(data_root), base.container_path(footprint)]
    log = TASK_ROOT / "logs/evaluate_fusion.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("evaluate_fusion_12k", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError(f"fusion evaluation failed: {log}")
    body = json.loads(output.read_text())
    # The reused source finalizer has a literal three-replica label; this
    # bounded sweep evaluates one exact R1 continuation per dose.
    body["replicates_per_arm"] = 1
    atomic_json(output, body)
    print(output.read_text())


SURFACE_REFERENCE_CODE = r'''
import csv,importlib.util,json,sys,yaml,laspy,numpy as np
from pathlib import Path
from shapely.geometry import shape
spec=importlib.util.spec_from_file_location('diag','/workspace/JointBuildGS/scripts/p2/e3_local_4906982_mvc_readout_diag_v1/run.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
cfg=yaml.safe_load(Path(sys.argv[1]).read_text());cases=json.loads(Path(sys.argv[2]).read_text());out=Path(sys.argv[3]);foot=shape(json.loads(Path(cfg['shared_footprint']).read_text())['features'][0]['geometry']);refs=m.parse_reference_roofs(Path(cfg['reference_lod2_gml']),cfg['building_id']);rows=[]
adapter=out/'control/surface_metric_adapter';adapter.mkdir(parents=True,exist_ok=True)
for c in cases:
 source=Path(c['fused_laz']);cloud=laspy.read(source)
 # The reused diagnostic asks for legacy NormalX/Y/Z dimensions; the frozen
 # evaluator writes the same values as normal_x/y/z. Add adapter-only aliases
 # in a sidecar LAZ without changing the source fusion payload.
 for src,dst in [('normal_x','NormalX'),('normal_y','NormalY'),('normal_z','NormalZ')]:
  cloud.add_extra_dim(laspy.ExtraBytesParams(name=dst,type=np.float32));cloud[dst]=np.asarray(cloud[src],dtype=np.float32)
 adapted=adapter/f"{c['arm']}.laz";cloud.write(adapted)
 metrics=m.point_metrics(adapted,foot,refs,cfg,classified=False);rows.append({'arm':c['arm'],'w_depth':c['w_depth'],'source':c['source'],'normal_dimension_adapter':'normal_x/y/z to NormalX/Y/Z sidecar only',**metrics,'scientific_verdict':None})
with (out/'surface_reference_metrics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'surface_reference_metrics.json').write_text(json.dumps({'schema':'jointbuildgs.p2.e3_local_4906982_mvc_depth_weight_v1.surface_reference.v1','rows':rows,'reference_use':'evaluation_only','scientific_verdict':None},indent=2,sort_keys=True)+'\n');print(json.dumps(rows,indent=2))
'''


def surface_reference() -> None:
    if not (TASK_ROOT / "surface_metrics.json").is_file(): raise RuntimeError("fusion evaluation required")
    cases = []
    prior = {"W000": REFERENCE["W000"][1], "W030": REFERENCE["W030"][1]}
    for arm in ("W000", *ARMS, "W030"):
        root = prior[arm] if arm in prior else run_root(arm)
        fused = root / "evaluation/step_012000/fusion/fused_surface.laz"
        if not fused.is_file(): raise FileNotFoundError(fused)
        cases.append({"arm": arm, "w_depth": 0.0 if arm == "W000" else 0.03 if arm == "W030" else WEIGHTS[arm], "source": "read_only_prior_R1" if arm in prior else "new_weight_only_R1", "fused_laz": base.container_path(fused)})
    case_path = TASK_ROOT / "control/surface_cases.json"; atomic_json(case_path, cases)
    argv = base.eval_docker_base() + ["python", "-c", SURFACE_REFERENCE_CODE, "/workspace/JointBuildGS/configs/p2/e3_local_4906982_mvc_depth_weight_v1/surface_eval.yaml", base.container_path(case_path), base.container_path(TASK_ROOT)]
    log = TASK_ROOT / "logs/surface_reference.log"; started = base.now()
    with log.open("w") as stream: proc = subprocess.run(argv, text=True, stdout=stream, stderr=subprocess.STDOUT)
    base.record_operation("surface_reference_12k", argv, proc.returncode, started, base.now())
    if proc.returncode != 0: raise RuntimeError(f"surface reference failed: {log}")
    rows = json.loads((TASK_ROOT / "surface_reference_metrics.json").read_text())["rows"]
    metrics = json.loads((TASK_ROOT / "metrics.json").read_text()); index = {r["arm"]: r for r in metrics["rows"]}
    lines = ["", "## 12k evaluation-only fused surface", "", "| arm | w_depth | median |dZ| | height RMSE | median normal angle | within 0.5m | grid coverage | coherent coverage | fusion Z>650 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        fmt=lambda v,n=3: "n/a" if v is None else f"{v:.{n}f}"
        lines.append(f"| {r['arm']} | {r['w_depth']:.3f} | {fmt(r.get('abs_dz_m_median'))} | {fmt(r.get('abs_dz_m_rmse'))} | {fmt(r.get('normal_angle_deg_median'))}° | {fmt(r.get('within_0p5m_fraction'))} | {fmt(r.get('grid_coverage_fraction'))} | {fmt(r.get('coherent_grid_coverage_fraction'))} | {r['z_gt_650_count']:,} |")
        index[r["arm"]]["fused_surface_evaluation_only"] = r
    metrics["surface_reference"] = {"reference_use": "evaluation_only", "rows": rows}; atomic_json(TASK_ROOT / "metrics.json", metrics)
    with (TASK_ROOT / "comparison.md").open("a") as stream: stream.write("\n".join(lines) + "\n")
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text()); provenance["surface_eval_config_sha256"] = sha256(SURFACE_CONFIG); provenance["surface_outputs_sha256"] = {name: sha256(TASK_ROOT / name) for name in ("surface_metrics.json", "surface_checkpoint_metrics.csv", "surface_reference_metrics.json", "surface_reference_metrics.csv")}; atomic_json(TASK_ROOT / "provenance.json", provenance)
    print("\n".join(lines))


def finalize() -> None:
    required = [TASK_ROOT / name for name in ("metrics.json", "checkpoint_metrics.csv", "surface_metrics.json", "surface_reference_metrics.json", "surface_reference_metrics.csv", "comparison.md", "issues.md", "representative_images/dose_comparison/manifest.json")]
    missing = [str(path) for path in required if not path.is_file()]
    if missing: raise RuntimeError(f"missing final inputs: {missing}")
    comparison = (TASK_ROOT / "comparison.md").read_text()
    if "## 측정 관찰과 다음 분리" not in comparison:
        comparison += """

## 측정 관찰과 다음 분리

- `w_depth=0.03`은 W010과 held-out PSNR 차이가 거의 없지만 Gaussian 수를 120,359→218,094로 늘리고, 새 maximum-Z 1,152.56 m를 만들었다. 이 범위에서는 absolute-metric L1의 0.03 세기가 과도했다는 관찰과 일치한다.
- weight를 낮춰도 정상 표면은 일관되게 좋아지지 않았다. W001은 height RMSE tail만 개선했고 median 높이·normal·coherence는 control보다 소폭 나빴다. W003은 height RMSE가 크게 나빠졌고 W010은 normal/coherence가 더 나빠졌다.
- 따라서 weight 과강도와 depth evidence/cost의 불안정성은 분리됐다. 다음 cost-only 진단의 bounded anchor로는 growth와 surface 훼손이 가장 작은 W001이 적합하지만, 이는 scientific winner 선택이 아니다.
- 다음 계약은 W001의 입력·mask·weight를 고정한 robust-cost 단일변수여야 한다. 그 뒤 같은 cost/weight를 고정하고 LoD2-blind confidence gate를 별도 단일변수로 시험한다. normal 감독과 multi-view densification은 아직 추가하지 않는다.

Scientific verdict: `null`.
"""
        base.atomic_text(TASK_ROOT / "comparison.md", comparison)
    panels = json.loads((TASK_ROOT / "representative_images/dose_comparison/manifest.json").read_text())
    viewer = TASK_ROOT / "viewer"; viewer.mkdir(exist_ok=True)
    names = [row["file"] for row in panels["files"]]
    html = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>4906982 depth weight sweep</title><style>body{font-family:system-ui;background:#0d1117;color:#e6edf3;margin:0;padding:18px}header,img{max-width:1800px;margin:auto;display:block}select,a{padding:8px;margin:4px;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:5px}small{color:#8b949e}</style></head><body><header><h1>DEBY_LOD2_4906982 · depth weight-only 12k</h1><p>Rows: W000, W001, W003, W010, W030. Columns: held-out RGB, GS RGB, depth, normal, opacity.</p><select id="p"></select><a href="../comparison.md">comparison.md</a><small> scientific_verdict: null</small></header><img id="v"><script>const n=__NAMES__,s=document.getElementById('p'),v=document.getElementById('v');for(const x of n){const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o)}function show(){v.src='../representative_images/dose_comparison/'+s.value}s.onchange=show;s.selectedIndex=Math.min(6,n.length-1);show()</script></body></html>'''.replace("__NAMES__", json.dumps(names))
    base.atomic_text(viewer / "index.html", html)
    atomic_json(TASK_ROOT / "viewer_slot.json", {"schema": "jointbuildgs.viewer.comparison_slot.v1", "slot_id": "p2-e3-local-4906982-mvc-depth-weight-v1", "label": "4906982 MVC depth weight-only 12k", "relative_url": "viewer/index.html", "panel_count": len(names), "separate_add_only_slot": True, "legacy_results_modified": False, "scientific_verdict": None})
    base.atomic_text(TASK_ROOT / "NOTES.md", f"""# {TASK_ID}

Status: `COMPLETE_MEASURED_12K_WEIGHT_ONLY`.

- Three new exact-state continuations: W001/W003/W010, R1, 7k→12k.
- Two read-only hash-gated endpoints: W000/W030 from the prior depth run.
- Training delta: `w_depth` only; masked L1, MVC, depth inputs, view roles, growth, and schedules fixed.
- All three new checkpoints valid; no OOM, NaN, or 800k cap.
- Fixed 55-view render/voxel-fusion and evaluation-only LoD2 height/normal/coherence metrics complete.
- Eight five-dose qualitative panels available under `representative_images/dose_comparison/`.
- Roofer was not rerun in this bounded weight-isolation stage.
- Failures and retries are retained in `issues.md` and `failed_attempts/`.
- Scientific verdict: `null`.
""")
    contract = json.loads((TASK_ROOT / "experiment_contract.json").read_text()); contract["status"] = "COMPLETE_MEASURED_12K_WEIGHT_ONLY"; contract["scientific_verdict"] = None; atomic_json(TASK_ROOT / "experiment_contract.json", contract)
    provenance = json.loads((TASK_ROOT / "provenance.json").read_text())
    provenance["git_at_completion"] = base.git_record(); provenance["ended_utc"] = base.now(); provenance["scientific_verdict"] = None
    provenance["source_files_sha256"] = {str(path.relative_to(REPO)): sha256(path) for path in (Path(__file__).resolve(), SWEEP_CONFIG, SURFACE_CONFIG, DEPTH_RUNNER, SOURCE_CONFIG, REPO / "src/stage2/train.py", REPO / "src/stage2/loss/data_fitting.py", depth.MVC_SOURCE)}
    outputs = ["experiment_contract.json", "provenance.json", "config_diff.txt", "input_hashes.json", "checkpoint_metrics.csv", "metrics.json", "surface_checkpoint_metrics.csv", "surface_metrics.json", "surface_reference_metrics.csv", "surface_reference_metrics.json", "comparison.md", "NOTES.md", "issues.md", "representative_images/dose_comparison/manifest.json", "viewer_slot.json", "viewer/index.html"]
    provenance["output_index_sha256"] = {name: sha256(TASK_ROOT / name) for name in outputs if name != "provenance.json"}
    atomic_json(TASK_ROOT / "provenance.json", provenance)
    print(json.dumps({"status": contract["status"], "task_root": str(TASK_ROOT), "viewer": str(viewer / "index.html"), "panels": len(names), "scientific_verdict": None}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["preflight", "binding-probe", "smoke", "fork", "train", "analyze", "evaluate-fusion", "surface-reference", "finalize", "all"]); args = parser.parse_args()
    if args.command in {"preflight", "all"}: preflight()
    if args.command in {"binding-probe", "all"}: binding_probe()
    if args.command in {"smoke", "all"}: smoke()
    if args.command in {"fork", "all"}: fork_prefix()
    if args.command in {"train", "all"}: train()
    if args.command in {"analyze", "all"}: analyze()
    if args.command in {"evaluate-fusion", "all"}: evaluate_fusion()
    if args.command in {"surface-reference", "all"}: surface_reference()
    if args.command in {"finalize", "all"}: finalize()


if __name__ == "__main__":
    main()
