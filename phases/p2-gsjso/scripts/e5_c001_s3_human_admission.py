#!/usr/bin/env python3
"""Record and enforce the 2026-07-14 S3-A human gate admission.

This adapter deliberately does not modify the mechanically pinned gate
orchestrator.  The historical ``gate_status`` and every other mechanical CSV
cell remain byte-for-value evidence; two appended human fields provide the
separate authorization for the half-weight information-recovery runs.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
REPO = SCRIPT_PATH.parents[3]
MECHANICAL_SCRIPT = SCRIPT_PATH.with_name("e5_c001_s3_semantic_guided.py")
SPEC = importlib.util.spec_from_file_location("e5_c001_s3_mechanical", MECHANICAL_SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import mechanical orchestrator: {MECHANICAL_SCRIPT}")
S3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S3)

HUMAN_VERDICT = "pass_by_kim_20260714"
HUMAN_VERDICT_REASON = "P-I reclassified as measurement"
HUMAN_FIELDS = ["human_verdict", "human_verdict_reason"]
HALF_RUN = f"{S3.GATE_RUN}_half_once"
ADMISSION_MANIFEST = S3.RUN_DIR / "human_admission_20260714.json"
EXPECTED_MECHANICAL_REASON = (
    "P-I nonzero rendered-depth gradient not observed for 8568391"
)


def read_csv_with_fields(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV has no header: {S3.rel(path)}")
        return list(reader.fieldnames), list(reader)


def write_csv_atomic(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def validate_mechanical_half_summary(summary: dict[str, str]) -> None:
    expected = {
        "run_name": HALF_RUN,
        "record_type": "gate_summary",
        "gate_attempt": "2",
        "total_loss_finite_status": "pass",
        "train_return_code": "0",
        "semdepth_status": "pass",
        "boundary_normal_status": "pass",
        "gate_status": "fail",
        "gate_reasons": EXPECTED_MECHANICAL_REASON,
        "pi_all_targets_status": "fail",
        "effective_semdepth_scale": "0.5",
        "effective_nb_scale": "1.0",
        "effective_w_semdepth_smooth": "0.125",
        "effective_w_semdepth_plane": "0.125",
        "effective_w_boundary_normal": "0.01",
        "judgment_scope": "mechanical preregistered gate fields only; human verdict excluded",
    }
    mismatches = {
        key: {"actual": summary.get(key), "expected": value}
        for key, value in expected.items()
        if summary.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            "half-once mechanical evidence is outside the exact human ruling: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    for field in ("semdepth_grad_share_max", "boundary_normal_grad_share_max"):
        try:
            value = float(summary[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid {field} in half-once summary") from exc
        if not math.isfinite(value) or value > S3.GRAD_SHARE_MAX:
            raise RuntimeError(f"{field} does not pass the locked <=0.40 criterion: {value}")


def validate_human_fields(rows: list[dict[str, str]]) -> dict[str, str]:
    summaries = [row for row in rows if row.get("record_type") == "gate_summary"]
    selected = [row for row in summaries if row.get("run_name") == HALF_RUN]
    if len(selected) != 1:
        raise RuntimeError(f"expected one half-once summary, found {len(selected)}")
    row = selected[0]
    if row.get("human_verdict") != HUMAN_VERDICT:
        raise RuntimeError("missing or altered exact human_verdict")
    if row.get("human_verdict_reason") != HUMAN_VERDICT_REASON:
        raise RuntimeError("missing or altered exact human_verdict_reason")
    leaked = [
        other.get("run_name") or f"row:{index + 2}"
        for index, other in enumerate(rows)
        if other is not row
        and (other.get("human_verdict") or other.get("human_verdict_reason"))
    ]
    if leaked:
        raise RuntimeError(f"human verdict fields leaked outside half-once summary: {leaked[:10]}")
    validate_mechanical_half_summary(row)
    return row


def apply_human_fields(
    fields: list[str], rows: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    original = [{key: value for key, value in row.items()} for row in rows]
    output_fields = list(fields)
    for field in HUMAN_FIELDS:
        if field not in output_fields:
            output_fields.append(field)
    selected_count = 0
    for row in rows:
        for field in HUMAN_FIELDS:
            row.setdefault(field, "")
        if row.get("record_type") == "gate_summary" and row.get("run_name") == HALF_RUN:
            row["human_verdict"] = HUMAN_VERDICT
            row["human_verdict_reason"] = HUMAN_VERDICT_REASON
            selected_count += 1
        elif row.get("human_verdict") or row.get("human_verdict_reason"):
            raise RuntimeError("pre-existing human verdict outside the half-once summary")
    if selected_count != 1:
        raise RuntimeError(f"expected one half-once summary, found {selected_count}")
    for before, after in zip(original, rows):
        changed = {
            key: (before.get(key), after.get(key))
            for key in fields
            if before.get(key) != after.get(key)
        }
        if changed:
            raise RuntimeError(f"mechanical CSV cell changed while applying human fields: {changed}")
    validate_human_fields(rows)
    return output_fields, rows


def verify_expected_human_only_diff(
    current_fields: list[str], current_rows: list[dict[str, str]]
) -> dict[str, str]:
    """Prove a resumed record differs from HEAD only by the two human columns."""

    relative = S3.rel(S3.CSV_GATE_AUDIT)
    process = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"cannot read committed mechanical gate CSV: {process.stdout}")
    committed_reader = csv.DictReader(process.stdout.splitlines())
    if committed_reader.fieldnames is None:
        raise RuntimeError("committed mechanical gate CSV has no header")
    committed_fields = list(committed_reader.fieldnames)
    committed_rows = list(committed_reader)
    if current_fields != committed_fields + HUMAN_FIELDS:
        raise RuntimeError("dirty gate CSV is not the exact mechanical header plus human fields")
    if len(current_rows) != len(committed_rows):
        raise RuntimeError("dirty gate CSV row count differs from committed mechanical evidence")
    for index, (before, after) in enumerate(zip(committed_rows, current_rows), start=2):
        changed = {
            key: (before.get(key), after.get(key))
            for key in committed_fields
            if before.get(key) != after.get(key)
        }
        if changed:
            raise RuntimeError(f"mechanical cell changed at CSV line {index}: {changed}")
    return validate_human_fields(current_rows)


def canonical_half_summary() -> dict[str, str]:
    selection = S3.canonical_gate_selection()
    if selection["errors"]:
        raise RuntimeError(f"mechanical gate provenance invalid: {selection['errors']}")
    selected = selection["selected"]
    validate_mechanical_half_summary(selected)
    return selected


def generate_half_weight_full_configs() -> list[dict[str, Any]]:
    base = S3.locked_base()
    cache = S3.cache_status()
    rows: list[dict[str, Any]] = []
    for replicate, run_name in zip(("r1", "r2"), S3.FULL_RUNS):
        state = S3.launch_artifact_state(
            run_name, {"out_dir": S3.ws(S3.CKPT_ROOT / run_name)}
        )
        if state["collision"]:
            raise RuntimeError(f"cannot rewrite config after run artifact exists: {state}")
        path, config, metadata = S3.make_config(
            base=base,
            run_name=run_name,
            max_iter=S3.FULL_MAX_ITER,
            generic_audit_every=S3.FULL_GENERIC_AUDIT_EVERY,
            semantic_audit_every=S3.FULL_SEMANTIC_AUDIT_EVERY,
            semdepth_scale=0.5,
            nb_scale=1.0,
            gate_attempt=0,
        )
        row = S3.config_inventory_row(
            phase="full_human_authorized",
            replicate=replicate,
            run_name=run_name,
            path=path,
            config=config,
            metadata=metadata,
            cache=cache,
        )
        row.update(
            {
                "human_verdict": HUMAN_VERDICT,
                "human_verdict_reason": HUMAN_VERDICT_REASON,
            }
        )
        rows.append(row)
    S3.update_inventory(rows, set(S3.FULL_RUNS))
    S3.write_manifest_and_versions()
    return rows


def write_admission_manifest(summary: dict[str, str]) -> None:
    payload = {
        "schema": "jointbuildgs.s3a.human_admission.v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_before_admission_commit": S3.capture(["git", "rev-parse", "HEAD"]),
        "git_branch": S3.capture(["git", "branch", "--show-current"]),
        "mechanical_gate_status_preserved": summary["gate_status"],
        "mechanical_gate_reason_preserved": summary["gate_reasons"],
        "human_verdict": HUMAN_VERDICT,
        "human_verdict_reason": HUMAN_VERDICT_REASON,
        "post_result_ruling_disclosure": [
            "이 재판정은 게이트 결과를 본 뒤에 내려졌다.",
            "근거 = ① 신호 도달을 당락으로 잠근 문면이 없음.",
            "② \"3채 전부 신호 통과\" 요구는 씨앗 부재 갈래의 사전 등록과 논리 충돌(무반응이 예측인 건물의 무반응이 게이트를 죽이는 구조) ③ 비중 기준은 통과.",
        ],
        "selected_weights": {
            "w_semdepth_smooth": 0.125,
            "w_semdepth_plane": 0.125,
            "w_boundary_normal": 0.01,
            "semantic_geometry_warmup": 1500,
        },
        "claim_boundary": (
            "S3-A oracle class+instance-address mechanism upper-bound information-recovery runs; "
            "not a battlefield win; S3-B forbids the oracle ID map"
        ),
        "mechanical_orchestrator": S3.rel(MECHANICAL_SCRIPT),
        "mechanical_orchestrator_sha256": S3.sha256_file(MECHANICAL_SCRIPT),
        "human_admission_adapter": S3.rel(SCRIPT_PATH),
        "human_admission_adapter_sha256": S3.sha256_file(SCRIPT_PATH),
        "gate_audit": S3.rel(S3.CSV_GATE_AUDIT),
        "gate_audit_sha256": S3.sha256_file(S3.CSV_GATE_AUDIT),
        "full_configs": {
            run_name: {
                "path": S3.rel(S3.run_name_config_path(run_name)),
                "sha256": S3.sha256_file(S3.run_name_config_path(run_name)),
            }
            for run_name in S3.FULL_RUNS
        },
    }
    ADMISSION_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    ADMISSION_MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def record(_args: argparse.Namespace) -> None:
    gate_commit = S3.committed_unchanged(S3.CSV_GATE_AUDIT)
    fields, rows = read_csv_with_fields(S3.CSV_GATE_AUDIT)
    if gate_commit["committed_unchanged"]:
        summary = canonical_half_summary()
        fields, rows = apply_human_fields(fields, rows)
        write_csv_atomic(S3.CSV_GATE_AUDIT, fields, rows)
        validate_human_fields(S3.read_csv(S3.CSV_GATE_AUDIT))
    else:
        # A prior record process may have stopped after the atomic ledger write
        # but before config generation.  Resume only after proving that every
        # committed mechanical cell is identical and only the exact two human
        # fields were appended.
        summary = verify_expected_human_only_diff(fields, rows)
    generated = generate_half_weight_full_configs()
    write_admission_manifest(summary)
    print(
        json.dumps(
            {
                "mechanical_gate_status": summary["gate_status"],
                "human_verdict": HUMAN_VERDICT,
                "human_verdict_reason": HUMAN_VERDICT_REASON,
                "full_configs": [row["config"] for row in generated],
                "training_started": False,
            },
            ensure_ascii=False,
        )
    )


def validate_admission_manifest() -> dict[str, Any]:
    payload = json.loads(ADMISSION_MANIFEST.read_text(encoding="utf-8"))
    expected = {
        "human_verdict": HUMAN_VERDICT,
        "human_verdict_reason": HUMAN_VERDICT_REASON,
        "mechanical_gate_status_preserved": "fail",
        "mechanical_orchestrator_sha256": S3.sha256_file(MECHANICAL_SCRIPT),
        "human_admission_adapter_sha256": S3.sha256_file(SCRIPT_PATH),
        "gate_audit_sha256": S3.sha256_file(S3.CSV_GATE_AUDIT),
    }
    mismatches = {
        key: {"actual": payload.get(key), "expected": value}
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"human admission manifest mismatch: {mismatches}")
    return payload


def committed_training_inputs(run_name: str) -> dict[str, dict[str, Any]]:
    paths = {
        "config": S3.run_name_config_path(run_name),
        "human_admission_adapter": SCRIPT_PATH,
        "human_admission_manifest": ADMISSION_MANIFEST,
        "mechanical_orchestrator": MECHANICAL_SCRIPT,
        "gate_audit": S3.CSV_GATE_AUDIT,
        "seed_inventory": S3.CSV_SEED_INVENTORY,
        "experiment_inventory": S3.CSV_INVENTORY,
        "base_config": S3.BASE_CONFIG,
        "train": REPO / "src/stage2/train.py",
        "densification": REPO / "src/stage2/densification.py",
        "semantic_loss": REPO / "src/stage2/loss/semantic_guided.py",
        "cache_producer": S3.CACHE_PRODUCER,
        "cache_manifest": S3.CACHE_MANIFEST,
        "cache_inventory": S3.CACHE_INVENTORY,
    }
    return {key: S3.committed_unchanged(path) for key, path in paths.items()}


def validate_track_a(run_name: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    if run_name not in S3.FULL_RUNS:
        raise RuntimeError(f"human admission only authorizes the locked full runs: {run_name}")
    selection = S3.canonical_gate_selection()
    if selection["errors"]:
        raise RuntimeError(f"mechanical provenance invalid: {selection['errors']}")
    validate_mechanical_half_summary(selection["selected"])
    validate_human_fields(S3.read_csv(S3.CSV_GATE_AUDIT))
    validate_admission_manifest()
    seed_errors = S3.validate_seed_inventory(S3.read_csv(S3.CSV_SEED_INVENTORY))
    if seed_errors:
        raise RuntimeError(f"T0-2 seed inventory invalid: {seed_errors}")
    config_path = S3.run_name_config_path(run_name)
    config = S3.load_yaml(config_path)
    S3.verify_exact_base(config, S3.locked_base())
    S3.validate_s3_config(config, run_name)
    if not S3.same_value(config.get("s3_semdepth_scale"), 0.5) or not S3.same_value(
        config.get("s3_nb_scale"), 1.0
    ):
        raise RuntimeError("full config does not carry the exact half-once scales")
    if not S3.cache_status()["ready"]:
        raise RuntimeError("semantic-region cache is not ready")
    inputs = committed_training_inputs(run_name)
    dirty = [key for key, state in inputs.items() if not state["committed_unchanged"]]
    if dirty:
        raise RuntimeError(f"training inputs must be committed and unchanged: {dirty}")
    artifacts = S3.launch_artifact_state(run_name, config)
    if artifacts["collision"]:
        raise RuntimeError(f"immutable run artifact collision: {artifacts}")
    return config_path, config, {"inputs": inputs, "artifacts": artifacts}


def write_launch_versions(
    run_name: str,
    gpu: str,
    config_path: Path,
    command: list[str],
    preflight_log: Path,
) -> Path:
    cache = S3.cache_inventory_contract(require_complete=True)
    path = S3.RUN_DIR / "versions" / f"{run_name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"run_id: {S3.RUN_ID}",
        f"run_name: {run_name}",
        f"launch_utc: {datetime.now(timezone.utc).isoformat()}",
        f"git_head: {S3.capture(['git', 'rev-parse', 'HEAD'])}",
        f"git_branch: {S3.capture(['git', 'branch', '--show-current'])}",
        f"docker_image: {S3.DEV_IMAGE}",
        f"docker_image_id: {S3.docker_image_id()}",
        f"host_gpu_selector: {gpu}",
        f"human_verdict: {HUMAN_VERDICT}",
        f"human_verdict_reason: {HUMAN_VERDICT_REASON}",
        "mechanical_gate_status_preserved: fail",
        f"human_admission_adapter: {S3.rel(SCRIPT_PATH)}",
        f"human_admission_adapter_sha256: {S3.sha256_file(SCRIPT_PATH)}",
        f"mechanical_orchestrator: {S3.rel(MECHANICAL_SCRIPT)}",
        f"mechanical_orchestrator_sha256: {S3.sha256_file(MECHANICAL_SCRIPT)}",
        f"human_admission_manifest: {S3.rel(ADMISSION_MANIFEST)}",
        f"human_admission_manifest_sha256: {S3.sha256_file(ADMISSION_MANIFEST)}",
        f"gate_audit_sha256: {S3.sha256_file(S3.CSV_GATE_AUDIT)}",
        f"config: {S3.rel(config_path)}",
        f"config_sha256: {S3.sha256_file(config_path)}",
        f"base_config_sha256: {S3.sha256_file(S3.BASE_CONFIG)}",
        f"train_py_sha256: {S3.sha256_file(REPO / 'src/stage2/train.py')}",
        f"densification_py_sha256: {S3.sha256_file(REPO / 'src/stage2/densification.py')}",
        f"semantic_loss_py_sha256: {S3.sha256_file(REPO / 'src/stage2/loss/semantic_guided.py')}",
        f"cache_inventory_sha256: {cache['inventory_sha256']}",
        f"cache_aggregate_sha256: {cache['aggregate_sha256']}",
        f"cache_loader_preflight_log: {S3.rel(preflight_log)}",
        f"cache_loader_preflight_sha256: {S3.sha256_file(preflight_log)}",
        f"command: {shlex.join(command)}",
    ]
    with path.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def train_one(args: argparse.Namespace) -> None:
    config_path, config, state = validate_track_a(args.run_name)
    command = S3.docker_base(args.gpu) + [
        "python",
        "-m",
        "src.stage2.train",
        "--config",
        S3.ws(config_path),
    ]
    preflight_command = S3.docker_base(args.gpu) + [
        "python",
        S3.ws(MECHANICAL_SCRIPT),
        "check-cache",
        "--loader-preflight",
    ]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "run_name": args.run_name,
                    "human_verdict": HUMAN_VERDICT,
                    "config": S3.rel(config_path),
                    "config_sha256": S3.sha256_file(config_path),
                    "weights": {
                        "smooth": config["w_semdepth_smooth"],
                        "plane": config["w_semdepth_plane"],
                        "boundary_normal": config["w_boundary_normal"],
                    },
                    "committed_training_inputs": state["inputs"],
                    "launch_artifact_state": state["artifacts"],
                    "cache_loader_preflight_command": shlex.join(preflight_command),
                    "command": shlex.join(command),
                    "training_started": False,
                },
                ensure_ascii=False,
            )
        )
        return
    if S3.HOST_REPO != REPO:
        raise RuntimeError(
            f"non-dry launch forbids alternate mounts: HOST_REPO={S3.HOST_REPO}, REPO={REPO}"
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    preflight_log = S3.RUN_DIR / "cache_preflight" / f"{args.run_name}_{stamp}.log"
    preflight_log.parent.mkdir(parents=True, exist_ok=True)
    preflight = subprocess.run(
        preflight_command,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    with preflight_log.open("x", encoding="utf-8") as handle:
        handle.write(
            f"COMMAND={shlex.join(preflight_command)}\nRETURN_CODE={preflight.returncode}\n"
            + (preflight.stdout or "")
        )
    if preflight.stdout:
        print(preflight.stdout, end="", flush=True)
    if preflight.returncode != 0:
        raise RuntimeError(f"428-view cache preflight failed: {S3.rel(preflight_log)}")
    # Recheck after the preflight so concurrent launch attempts cannot overwrite evidence.
    if S3.launch_artifact_state(args.run_name, config)["collision"]:
        raise RuntimeError("run artifact appeared during cache preflight")
    versions = write_launch_versions(
        args.run_name, args.gpu, config_path, command, preflight_log
    )
    log_path = S3.TRAIN_LOG_ROOT / f"{args.run_name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("x", encoding="utf-8") as log:
        log.write(
            f"START_UTC={datetime.now(timezone.utc).isoformat()}\n"
            f"HOST_GPU={args.gpu}\nCONFIG={S3.rel(config_path)}\n"
            f"CONFIG_SHA256={S3.sha256_file(config_path)}\n"
            f"VERSIONS={S3.rel(versions)}\nCOMMAND={shlex.join(command)}\n"
        )
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return_code = int(process.wait())
        log.write(
            f"\nEND_UTC={datetime.now(timezone.utc).isoformat()}\nRETURN_CODE={return_code}\n"
        )
    print(
        json.dumps(
            {
                "run_name": args.run_name,
                "gpu": args.gpu,
                "return_code": return_code,
                "log": S3.rel(log_path),
            },
            ensure_ascii=False,
        )
    )
    if return_code != 0:
        raise SystemExit(return_code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("record")
    train = commands.add_parser("train-one")
    train.add_argument("--run-name", required=True)
    train.add_argument("--gpu", default="0")
    train.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "record":
        record(args)
    elif args.command == "train-one":
        train_one(args)
    else:  # pragma: no cover
        raise RuntimeError(args.command)


if __name__ == "__main__":
    main()
