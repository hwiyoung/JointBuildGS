"""Build a new viewer profile; preserve the original GeoGS viewer and inputs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin

RUN_CONDITION = "SFM_noanchor_D005_Pnative"
DEFAULT_PUBLIC_ROOT = "/task/evaluation/no_anchor_sfm_v1"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def absolute_urls(value, base):
    if isinstance(value, dict):
        return {k: urljoin(base, v) if isinstance(v, str) and (k == "url" or k.endswith("_url"))
                else absolute_urls(v, base) for k, v in value.items()}
    if isinstance(value, list):
        return [absolute_urls(v, base) for v in value]
    return value


def task_record(task, path):
    path = Path(path)
    relative = path.relative_to(task)
    if not path.is_file() or path.resolve() != task.resolve() / relative:
        raise ValueError("Expected a direct task evidence file: " + str(path))
    return dict(path=str(relative), url="/task/" + str(relative), sha256=sha(path), bytes=path.stat().st_size)


def resource_attempt_records(task, rows, region):
    if not isinstance(rows, list):
        raise ValueError("Prior resource attempts must be an explicit list")
    result, seen = [], set()
    for row in rows:
        receipt_path, stop_path = (task / row[key]["path"] for key in ("receipt", "stop_intent"))
        if receipt_path in seen or receipt_path.parent != stop_path.parent:
            raise ValueError("Prior receipt and stop intent must belong to one unique run")
        seen.add(receipt_path)
        receipt_record, stop_record = task_record(task, receipt_path), task_record(task, stop_path)
        receipt, stop = read_json(receipt_path), read_json(stop_path)
        if (receipt_record["sha256"] != row["receipt"]["sha256"] or stop_record["sha256"] != row["stop_intent"]["sha256"]
                or receipt.get("status") != "FAIL" or receipt.get("native_exit_code") != -15
                or receipt.get("phase") != "train" or receipt.get("region") != region
                or receipt.get("condition_id") != RUN_CONDITION or receipt.get("scientific_verdict") is not None
                or stop.get("cause") != "RESOURCE_TRANSFER_OPTIMIZATION" or stop.get("region") != region
                or stop.get("scientific_verdict") is not None):
            raise ValueError("Prior attempt does not match an intentional resource-transfer replacement")
        result.append(dict(receipt=receipt_record, stop_intent=stop_record,
            classification="INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT", cause="RESOURCE_TRANSFER_OPTIMIZATION",
            native_exit_code=-15, counted_as_cuda_oom=False, quality_assessed=False))
    return result


def initialization_failure_record(task, row, region):
    if not isinstance(row, dict) or row.get("cause") != "RESOURCE_SCHEDULING_ERROR":
        raise ValueError("Initialization failure requires a declared scheduling cause")
    receipt_path, log_path = (task / row[key]["path"] for key in ("receipt", "log"))
    if receipt_path.parent != log_path.parent or receipt_path.name != "receipt.json" or log_path.name != "native.log":
        raise ValueError("Initialization failure receipt/log must belong to one original run")
    receipt_record, log_record = task_record(task, receipt_path), task_record(task, log_path)
    if receipt_record["sha256"] != row["receipt"]["sha256"] or log_record["sha256"] != row["log"]["sha256"]:
        raise ValueError("Initialization failure evidence bytes changed")
    receipt = read_json(receipt_path)
    if (receipt.get("status") != "FAIL" or receipt.get("native_exit_code") != 1
            or receipt.get("phase") != "train" or receipt.get("region") != region
            or receipt.get("condition_id") != RUN_CONDITION or receipt.get("scientific_verdict") is not None
            or "CUDA error: out of memory" not in log_path.read_text()):
        raise ValueError("Initialization failure does not match its declared producer evidence")
    first_step = receipt_path.parent / "model/jbgs_no_anchor/first_step.json"
    if first_step.exists() or first_step.is_symlink():
        raise ValueError("Prior initialization failure has a first-step record")
    return dict(receipt=receipt_record, log=log_record, cause="RESOURCE_SCHEDULING_ERROR",
        classification="CUDA_INITIALIZATION_FAILURE", native_exit_code=1,
        first_step_record_path=str(first_step.relative_to(task)), first_step_record_absent=True,
        cuda_oom_observed=True, counted_as_training_cuda_oom=False, quality_assessed=False)


def final_retry_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location("geogs_viewer_final_retry",Path(__file__).with_name("final_retry.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def final_retry_downloads(attempt):
    row=attempt.get("final_resource_retry")
    if not row:return []
    result=[dict(label=label,url="/task/"+row[key]["path"]) for key,label in (
        ("policy","최종 1회 자원 재시도 정책"),("predecessor_training_receipt","직전 실제 학습 실패"),
        ("predecessor_native_log","직전 자원 실패 원본 로그"),("predecessor_amendment","직전 실행 변경 계보"),
        ("predecessor_first_step","직전 초기화 첫 step 검증"))]
    if row.get("predecessor_resource_failure"):
        result.append(dict(label="직전 cgroup 메모리 종료 검증",url="/task/"+row["predecessor_resource_failure"]["path"]))
        result.extend(dict(label="직전 메모리 종료 원본 근거 · "+item["role"],url="/task/"+item["path"]) for item in row["resource_failure_evidence"])
    return result


def inspect_attempt(task, experiment, region, iteration):
    """Read the explicitly selected attempt; an older failure cannot mask it."""
    run = experiment / "runs" / region / RUN_CONDITION
    record = dict(experiment_source_relative=str(experiment.relative_to(task)),
        execution_attempt_id=experiment.name, target_optimizer_updates=iteration,
        optimizer_updates=None, scientific_verdict=None, evidence=[])

    def amendment_metadata(value):
        source = value.get("memory_recovery_amendment_path")
        digest = value.get("memory_recovery_amendment_sha256")
        if bool(source) != bool(digest):
            raise ValueError("Both recovery amendment path and SHA are required")
        if not source:
            if experiment.name.startswith("no_anchor_sfm_gradient_memory_v3_"):
                raise ValueError("Final retry producer lacks its finite-policy amendment")
            return
        bound = task_record(task, task / source)
        amendment = read_json(task / source)
        if (bound["sha256"] != digest or amendment.get("scientific_verdict") is not None
                or amendment.get("arithmetic_or_scientific_controls_changed") is not False):
            raise ValueError("Recovery amendment identity or control declaration differs")
        record.update(memory_recovery_amendment_path=source,
            memory_recovery_amendment_sha256=digest,
            execution_deviations=amendment.get("memory_placement_changes", []))
        if "prior_resource_attempts" in amendment:
            record["prior_resource_attempts"] = resource_attempt_records(task, amendment["prior_resource_attempts"], region)
        if "prior_initialization_failure" in amendment:
            record["prior_initialization_failure"] = initialization_failure_record(task, amendment["prior_initialization_failure"], region)
        if "final_resource_retry" in amendment or experiment.name.startswith("no_anchor_sfm_gradient_memory_v3_"):
            record["final_resource_retry"] = final_retry_module().bind_retry(task,experiment,region,amendment,lambda path:task_record(task,path))
        if not any(row["path"] == bound["path"] for row in record["evidence"]):
            record["evidence"].append(bound)
    original = task / "no_anchor_sfm_v1/runs" / region / RUN_CONDITION / "receipt.json"
    if experiment != task / "no_anchor_sfm_v1" and original.is_file():
        value = read_json(original)
        if value.get("status") == "FAIL":
            record["original_failed_run_receipt"] = task_record(task, original)
    for phase, root in (("train", run), ("export", run / "exports" / ("iteration_" + str(iteration)))):
        path = root / "receipt.json"
        if not path.is_file():
            invocation = root / "invocation.json"
            if invocation.is_file():
                record["evidence"].append(task_record(task, invocation))
                amendment_metadata(read_json(invocation))
            elif phase == "train" and (experiment / "amendment.json").is_file():
                # A queued retry can already bind its preparation/failure lineage.
                declared = task_record(task, experiment / "amendment.json")
                amendment_metadata(dict(memory_recovery_amendment_path=declared["path"],
                    memory_recovery_amendment_sha256=declared["sha256"]))
            record.update(status="pending", failure_phase=None,
                quality_status="NOT_ASSESSED_" + phase.upper() + "_COMPLETION_PENDING",
                reason=("선택한 실행의 학습 완료를 기다립니다." if phase == "train" else "선택한 실행의 실제 표면·렌더 추출 완료를 기다립니다."))
            return record
        value = read_json(path)
        if (value.get("region") != region or value.get("phase") != phase
                or value.get("condition_id") != RUN_CONDITION or value.get("scientific_verdict") is not None):
            raise ValueError("Selected attempt receipt identity differs: " + str(path))
        evidence = task_record(task, path)
        record["evidence"].append(evidence)
        amendment_metadata(value)
        if value.get("status") == "FAIL":
            stop_path = root / "stop_intent.json"
            if value.get("native_exit_code") == -15 and stop_path.is_file():
                stopped = resource_attempt_records(task, [dict(receipt=task_record(task, path),
                    stop_intent=task_record(task, stop_path))], region)[0]
                record["evidence"].append(stopped["stop_intent"])
                record.update(status="failed", failure_phase=phase,
                    failure_kind="INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT", failure_receipt=evidence,
                    stop_intent=stopped["stop_intent"], counted_as_cuda_oom=False,
                    quality_status="NOT_ASSESSED_INTENTIONAL_RESOURCE_REPLACEMENT",
                    reason="메모리 전송 최적화 버전으로 옮기기 위해 학습을 의도적으로 중단했습니다. 목표 " + format(iteration, ",") + "회 표면·RGB 비교는 제공되지 않으며 품질 미평가입니다.")
                return record
            log_path = root / "native.log"
            cuda_oom = False
            host_memory_failure = False
            if log_path.is_file():
                with log_path.open("rb") as stream:
                    stream.seek(max(0, log_path.stat().st_size - (128 << 10)))
                    tail = stream.read()
                    cuda_oom = any(message in tail for message in (b"CUDA out of memory", b"CUDA error: out of memory"))
                    host_memory_failure = any(message in tail for message in (b"PINNED_HOST_BUDGET_EXCEEDED", b"_ArrayMemoryError", b"MemoryError:", b"std::bad_alloc", b"DefaultCPUAllocator: can't allocate memory"))
                record["evidence"].append(task_record(task, log_path))
            why = "CUDA 메모리 부족" if cuda_oom else "호스트 메모리 한도 초과" if host_memory_failure else "실행 오류"
            record.update(status="failed", failure_phase=phase,
                failure_kind="CUDA_OOM" if cuda_oom else "HOST_MEMORY_RESOURCE_FAILURE" if host_memory_failure else "PRODUCER_FAILURE",
                failure_receipt=evidence, quality_status="NOT_ASSESSED_" + phase.upper() + "_FAILURE",
                reason=("학습 " if phase == "train" else "표면·렌더 추출 ") + why + ". 목표 " + format(iteration, ",") + "회 표면·RGB 비교는 제공되지 않으며 품질 미평가입니다.")
            return record
        if value.get("status") != "PASS" or value.get("native_exit_code") != 0 or value.get("validated_exit_code") != 0:
            raise ValueError("Unrecognized selected attempt completion state")
    record.update(status="pending", failure_phase=None,
        quality_status="NOT_ASSESSED_EVALUATION_PENDING", reason="실제 추출은 완료됐으며 봉인·기하·RGB 평가를 기다립니다.")
    return record


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--experiment", type=Path,
                        help="Default selected attempt; defaults to /task/no_anchor_sfm_v1")
    parser.add_argument("--region-experiment", action="append", default=[], metavar="P1=/task/attempt",
                        help="Explicit per-region attempt override; never select attempts by their result")
    parser.add_argument("--source-manifest", default="evaluation/viewer/manifest_v2.json")
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--publish-id", required=True)
    parser.add_argument("--public-root", default=DEFAULT_PUBLIC_ROOT)
    parser.add_argument("--default-iteration", type=int, choices=(22000, 30000), default=22000)
    parser.add_argument("--selection-record", help="Optional task-relative frozen regional selection record")
    args = parser.parse_args()
    args.experiment = args.experiment or args.task / "no_anchor_sfm_v1"
    selected_experiments = {rid: args.experiment for rid in ("P1", "P2", "P3")}
    overrides = set()
    for entry in args.region_experiment:
        rid, separator, value = entry.partition("=")
        if not separator or rid not in selected_experiments or rid in overrides:
            raise ValueError("Expected a unique P1/P2/P3=experiment path override")
        selected_experiments[rid] = Path(value)
        overrides.add(rid)
    for experiment in selected_experiments.values():
        if not experiment.is_absolute() or not experiment.resolve().is_relative_to(args.task.resolve()):
            raise ValueError("Selected attempts must remain inside the original task mount")
    selection_record=None
    if args.selection_record:
        selection_path=args.task/args.selection_record
        selection=read_json(selection_path)
        if (selection.get("schema")!="GEOGS_REGIONAL_PRODUCER_SELECTION_v1" or selection.get("scientific_verdict") is not None
                or selection.get("quality_or_reference_selection") is not False
                or selection.get("selected_experiments")!={rid:str(path.relative_to(args.task)) for rid,path in selected_experiments.items()}):
            raise ValueError("Regional selection record differs from explicit viewer inputs")
        # Revalidate the selected roots without substituting a subsequently prepared attempt.
        verified_selection=final_retry_module().select(args.task,{rid:str(path) for rid,path in selected_experiments.items()})
        if any(selection.get(key)!=verified_selection[key] for key in ("policy","final_retry_evidence")):
            raise ValueError("Frozen regional selection policy or predecessor evidence changed")
        selection_record=task_record(args.task,selection_path)
    if not re.fullmatch("[A-Za-z0-9_-]+", args.publish_id):
        raise ValueError("Publish ID must name a fresh simple directory")
    if not args.public_root.startswith("/task/") or ".." in Path(args.public_root).parts:
        raise ValueError("Public root must be an absolute task URL")
    source = args.task / args.source_manifest
    source.relative_to(args.task)
    if not source.resolve().is_relative_to(args.task.resolve()):
        raise ValueError("Source manifest must remain inside the original task")
    if sha(source) != args.source_manifest_sha256:
        raise ValueError("Original viewer manifest changed")
    original = read_json(source)
    if original["scientific_verdict"] is not None:
        raise ValueError("Scientific verdict must remain null")
    destination = args.out / "profiles" / args.publish_id
    destination.mkdir(parents=True, exist_ok=False)
    profile_url = args.public_root.rstrip("/") + "/profiles/" + args.publish_id
    base_url = "/task/" + args.source_manifest
    manifest = absolute_urls(copy.deepcopy(original), base_url)
    # The old global run identity must not be attributed to new no-anchor rows.
    inherited = {key: manifest.pop(key) for key in list(manifest) if key.startswith(
        ("runtime_layout_", "repeat_contract_", "completion_contract_", "resource_contract_"))
        or key in ("evaluation_scope", "runs_directory", "resource_revision", "supplemental_repeat_id")}
    inherited["original_notes"] = manifest.get("notes", [])
    manifest.update(schema="geogs_p1p2p3_viewer_v1",
        title="GeoGS — 원방법과 SfM 초기화·Anchor 생략 비교",
        default_resolution="512",
        source_experiment_lineage=inherited,
        comparison_profile=dict(experiment="no_anchor_sfm_v1",
            source_manifest=base_url, source_manifest_sha256=args.source_manifest_sha256,
            initialization="frozen_image_SfM_sparse", anchor_executed=False,
            prior_depth_coefficient=0.005, not_image_only=True, scientific_verdict=None),
        resolution_modes=[dict(id="512", label="모든 결과 동일 TSDF 512", mesh_res=512,
                               anchor_variant="anchor_512", final_variant="mesh_512")])
    if selection_record:
        manifest["comparison_profile"]["regional_selection"]=selection_record
        manifest.setdefault("downloads",[]).append(dict(label="지역별 실행 선택 정책·근거",url=selection_record["url"]))
    manifest["notes"] = [
        "⑤ 새 조건: SfM 초기화에서 Anchor 없이 refinement만 수행. ALS 깊이 계수 .005는 유지하므로 image-only가 아닙니다.",
        "③은 기존 ALS 초기화 원방법의 Anchor8000 비교 참조입니다. 새 SfM 조건에 Anchor가 있었다는 뜻이 아닙니다.",
        "R22000은 원방법의 refinement 22000회와 실행 횟수가 같고, R30000은 원방법의 총 30000회와 같습니다. 초기화·학습 일정은 다른 진단입니다.",
        "①②③④⑥은 기존 고정 자료입니다. 기존 원설정/깊이 완화와 새 두 조건을 같은512·raw/post로 비교합니다.",
        "사진 렌더는 Gaussian RGB이며 TSDF 격자 또는 메시 색상과 별개의 출력입니다.",
        "SfM에는 과거 전체 영상으로 계산된 기하·색상 계보가 남습니다. 이번 학습의 평가 영상 분할은 고정하지만 독립 확증 실험은 아닙니다.",
        "사례 카메라는 기존 실험에서 정한 위치를 보존합니다. 새 SfM 결과로 사례를 재선정하지 않았으며 기존 사례의 조건명이 표시됩니다.",
        "아직 생산/평가되지 않은 지역·조건은 pending으로 남깁니다. 다른 예산이나 기존 모델로 대체하지 않습니다.",
        "UAS가 실제 관측한 점/표면과의 부호 없는 거리입니다. 참조 부재와 복원 실패를 구분하며 시간적 최신성의 정답으로 확대하지 않습니다.",
        "조건별 1회 실행의 개발 진단입니다. 동일 조건 변동은 측정되지 않아 작은 차이와 인과 해석에 한계가 있습니다.",
    ]
    retained_files = []
    inspected_indexes = []
    availability = []

    def public(path):
        return args.public_root.rstrip("/") + "/" + str(path.relative_to(args.out))

    # Older mesh metadata contains URLs relative to the original manifest, not to
    # the metadata file. Copy metadata only and absolutize its binary references.
    for region in manifest["regions"]:
        rid = region["id"]
        region["default_condition"] = RUN_CONDITION + "_R" + str(args.default_iteration)
        region["panel_candidates"]["anchor"] = "D005_Pnative.anchor_512.raw"
        region["panel_candidates"]["vanilla"] = "D005_Pnative.mesh_512.raw"
        region["notes"] = ["③ 기존 ALS Anchor8000 / ④ 기존 원설정 final30000 / ⑤ 선택한 기존 또는 새 SfM 조건."] + region.get("notes", [])
        for candidate in region["candidates"]:
            descriptor = candidate.get("mesh_data")
            if not descriptor:
                continue
            source_url = descriptor["url"]
            if not source_url.startswith("/task/"):
                raise ValueError("Existing mesh descriptor must have a task URL")
            source_path = args.task / source_url.removeprefix("/task/")
            if descriptor.get("sha256") and sha(source_path) != descriptor["sha256"]:
                raise ValueError("Original mesh descriptor bytes changed")
            value = absolute_urls(read_json(source_path), base_url)
            target = destination / "baseline_mesh_metadata" / rid / (candidate["id"] + ".json")
            write_json(target, value)
            candidate["mesh_data"] = dict(format="json", url=public(target),
                sha256=sha(target), bytes=target.stat().st_size)
            retained_files.append(dict(source=source_url, source_sha256=sha(source_path),
                new_metadata=public(target), new_metadata_sha256=sha(target),
                operation="METADATA_URL_ABSOLUTIZATION_ONLY", binary_geometry_modified=False))
        # Keep fixed512/baseline evidence and make existing native/weak comparison
        # evidence available while a new condition is selected.
        region["sections"] = [item for item in region.get("sections", [])
            if (item["id"].split(".")[0] in ("als_points", "mvs_points", "prior_mesh")
                or ".anchor_512." in item["id"] or ".mesh_512." in item["id"]
                or item["id"].endswith(".anchor_refinement_512"))]
        for collection in ("sections", "renders"):
            for item in region.get(collection, []):
                if item.get("condition_id") in ("D005_Pnative", "D0005_Pnative"):
                    item["source_condition_id"] = item["condition_id"]
                    item["condition_id"] = None
                    item["label"] = item["source_condition_id"] + " · " + (item.get("label") or item.get("id", "evidence"))
        for iteration in (22000, 30000):
            cid = RUN_CONDITION + "_R" + str(iteration)
            label = "SfM·Anchor 생략 · .005/native · " + format(iteration, ",") + "회"
            selected_attempt = inspect_attempt(args.task, selected_experiments[rid], rid, iteration)
            condition_record = dict(id=cid, label=label,
                candidate_id=cid + ".mesh_512.raw", anchor_executed=False,
                target_optimizer_updates=iteration, optimizer_updates=None,
                prior_depth_coefficient=0.005, execution_attempt=selected_attempt)
            region["conditions"].append(condition_record)
            index_path = args.out / "geometry" / rid / ("R%d_viewer_index.json" % iteration)
            if index_path.is_file():
                index = read_json(index_path)
                if index["status"] != "GEOMETRY_EVALUATED" or index["scientific_verdict"] is not None:
                    raise ValueError("Incomplete new geometry index")
                if index["region"] != rid or index["condition"] != cid or index["optimizer_updates"] != iteration:
                    raise ValueError("Wrong new geometry index identity")
                expected_candidates = {cid + ".mesh_512." + kind for kind in ("raw", "post")}
                if {row["id"] for row in index["candidates"]} != expected_candidates or len(index["candidates"]) != 2:
                    raise ValueError("New index must contain exactly raw and post for this snapshot")
                seal_path = args.out / "seals" / rid / ("R%d.json" % iteration)
                if sha(seal_path) != index["new_condition_seal_sha256"]:
                    raise ValueError("New geometry index seal changed")
                seal = read_json(seal_path)
                expected_experiment = str(selected_experiments[rid].relative_to(args.task))
                if seal.get("experiment_source_relative", "no_anchor_sfm_v1") != expected_experiment:
                    raise ValueError("Geometry belongs to a different execution attempt than the selected one")
                if selected_experiments[rid].name.startswith("no_anchor_sfm_gradient_memory_v3_") and "final_resource_retry" not in seal:
                    raise ValueError("Final retry geometry lacks its finite-policy provenance")
                if selected_attempt["status"] == "failed":
                    raise ValueError("A failed selected attempt cannot supply a completed geometry index")
                condition_record["optimizer_updates"] = iteration
                condition_record["execution_attempt"] = {key: seal[key] for key in (
                    "experiment_source_relative", "execution_attempt_id", "resource_recovery_applied",
                    "memory_recovery_amendment_path", "memory_recovery_amendment_sha256",
                    "original_failed_run_receipt", "prior_resource_attempts", "prior_initialization_failure", "final_resource_retry", "execution_deviations") if key in seal}
                if "prior_initialization_failure" in condition_record["execution_attempt"]:
                    prior = condition_record["execution_attempt"]["prior_initialization_failure"]
                    condition_record["execution_attempt"]["prior_initialization_failure"] = initialization_failure_record(args.task, prior, rid)
                if "final_resource_retry" in condition_record["execution_attempt"]:
                    amendment=read_json(args.task/condition_record["execution_attempt"]["memory_recovery_amendment_path"])
                    verified_retry=final_retry_module().bind_retry(args.task,selected_experiments[rid],rid,amendment)
                    if verified_retry!=condition_record["execution_attempt"]["final_resource_retry"]:
                        raise ValueError("Geometry seal final-retry provenance changed")
                    condition_record["execution_attempt"]["final_resource_retry"]=final_retry_module().bind_retry(
                        args.task,selected_experiments[rid],rid,amendment,lambda path:task_record(args.task,path))
                inspected_indexes.append(dict(path=public(index_path), sha256=sha(index_path)))
                for candidate in copy.deepcopy(index["candidates"]):
                    candidate["label"] = label + " · " + candidate["id"].rsplit(".", 1)[1]
                    candidate.setdefault("provenance", {})["execution_attempt"] = condition_record["execution_attempt"]
                    attempt = condition_record["execution_attempt"]
                    candidate.setdefault("downloads",[]).extend(final_retry_downloads(attempt))
                    if attempt.get("memory_recovery_amendment_path"):
                        candidate.setdefault("downloads", []).append(dict(label="메모리 배치 변경 감사",
                            url="/task/" + attempt["memory_recovery_amendment_path"]))
                    if attempt.get("original_failed_run_receipt"):
                        candidate.setdefault("downloads", []).append(dict(label="보존된 원 실패 실행",
                            url="/task/" + attempt["original_failed_run_receipt"]["path"]))
                    for prior_index, prior_attempt in enumerate(attempt.get("prior_resource_attempts", []), 1):
                        candidate.setdefault("downloads", []).extend([
                            dict(label="이전 자원 실행 " + str(prior_index), url="/task/" + prior_attempt["receipt"]["path"]),
                            dict(label="의도적 전환 중단 근거 " + str(prior_index), url="/task/" + prior_attempt["stop_intent"]["path"])])
                    if attempt.get("prior_initialization_failure"):
                        prior = attempt["prior_initialization_failure"]
                        candidate.setdefault("downloads", []).extend([
                            dict(label="보존된 초기화 실패 실행", url=prior["receipt"]["url"]),
                            dict(label="초기화 실패 원본 로그", url=prior["log"]["url"])])
                    region["candidates"].append(candidate)
                    availability.append(dict(region=rid, condition=cid, candidate=candidate["id"],
                        target_optimizer_updates=iteration, optimizer_updates=iteration,
                        status=candidate["status"], quality_status=candidate.get("evaluation_status"),
                        execution_attempt=condition_record["execution_attempt"],
                        geometry_index=dict(url=public(index_path), sha256=sha(index_path))))
                    for key, kind in (("section_url", "고정 단면"), ("distance_url", "양방향 참조 거리 지도")):
                        region["sections"].append(dict(id=candidate["id"] + "." + key,
                            label=label + " · " + candidate["id"].rsplit(".", 1)[1] + " · " + kind,
                            url=candidate[key], condition_id=cid,
                            comparison_family="SfM 초기화·Anchor 생략 / 기존 원방법 · 동일512",
                            caption="새 SfM 조건의 기존 고정 영역·표본 띠/참조 거리. 새 정합 없음. 검정 UAS·거리0…2m.",
                            selection_reason="Fixed original regional sections and whole ROI; no outcome selection"))
            else:
                suffix = " · 의도적 실행 중단" if selected_attempt.get("failure_kind") == "INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT" else " · 실행 실패" if selected_attempt["status"] == "failed" else " · 완료 대기"
                condition_record["label"] = label + suffix
                for kind in ("raw", "post"):
                    identifier = cid + ".mesh_512." + kind
                    candidate = dict(id=identifier, label=label + " · " + kind,
                        role="changed", status=selected_attempt["status"],
                        reason=selected_attempt["reason"], failure_phase=selected_attempt.get("failure_phase"),
                        failure_kind=selected_attempt.get("failure_kind"),
                        quality_status=selected_attempt["quality_status"],
                        target_optimizer_updates=iteration, optimizer_updates=None,
                        provenance=dict(execution_attempt=selected_attempt),
                        downloads=[dict(label="실행 근거 " + str(i + 1), url=item["url"])
                                   for i, item in enumerate(selected_attempt["evidence"])],
                        surface_kind="triangle_surface", data=None, mesh_data=None)
                    if selected_attempt.get("original_failed_run_receipt"):
                        candidate["downloads"].append(dict(label="보존된 원 실패 실행", url=selected_attempt["original_failed_run_receipt"]["url"]))
                    candidate["downloads"].extend(final_retry_downloads(selected_attempt))
                    for prior_index, prior_attempt in enumerate(selected_attempt.get("prior_resource_attempts", []), 1):
                        candidate["downloads"].extend([
                            dict(label="이전 자원 실행 " + str(prior_index), url=prior_attempt["receipt"]["url"]),
                            dict(label="의도적 전환 중단 근거 " + str(prior_index), url=prior_attempt["stop_intent"]["url"])])
                    if selected_attempt.get("prior_initialization_failure"):
                        prior = selected_attempt["prior_initialization_failure"]
                        candidate["downloads"].extend([
                            dict(label="보존된 초기화 실패 실행", url=prior["receipt"]["url"]),
                            dict(label="초기화 실패 원본 로그", url=prior["log"]["url"])])
                    region["candidates"].append(candidate)
                    availability.append(dict(region=rid, condition=cid, candidate=identifier,
                        target_optimizer_updates=iteration, optimizer_updates=None,
                        status=candidate["status"], quality_status=candidate["quality_status"],
                        failure_phase=candidate["failure_phase"], failure_kind=candidate["failure_kind"],
                        execution_attempt=selected_attempt))
            render_root = args.out / "renders" / rid / cid / "refinement_only"
            receipt_path = render_root / "receipt.json"
            if receipt_path.is_file():
                receipt = read_json(receipt_path)
                if (receipt["scientific_verdict"] is not None or receipt["region"] != rid
                        or receipt["condition"] != cid or receipt["stage"] != "refinement_only"
                        or receipt["status"] not in ("PASS_RENDER_QUALITY_EVALUATION", "COMPLETE_WITH_RECORDED_FAILURES")):
                    raise ValueError("Render receipt identity or completion differs")
                seal_path = args.out / "seals" / rid / ("R%d.json" % iteration)
                if sha(seal_path) != receipt["sealed_render_manifest_sha256"]:
                    raise ValueError("Render receipt seal changed")
                if (read_json(seal_path).get("experiment_source_relative", "no_anchor_sfm_v1")
                        != str(selected_experiments[rid].relative_to(args.task))
                        or selected_attempt["status"] == "failed"):
                    raise ValueError("RGB belongs to a different or failed selected execution attempt")
                inspected_indexes.append(dict(path=public(receipt_path), sha256=sha(receipt_path)))
                for row in receipt["rows"]:
                    if not row.get("montage"):
                        continue
                    path = Path(row["montage"])
                    if not path.is_absolute():
                        path = render_root / path
                    if not path.is_file() or not path.is_relative_to(args.out):
                        raise ValueError("Missing or foreign actual RGB montage")
                    region["renders"].append(dict(id=cid + "." + row["domain"] + "." + str(row["evaluation_index"]),
                        label=label + " · " + row["name"] + " · " + row["domain"],
                        url=public(path), condition_id=cid, stage="refinement_only",
                        evaluation_index=row["evaluation_index"], source_photo=row["name"],
                        image_name=row["name"], domain=row["domain"], split="evaluation",
                        caption="왼쪽 실제 평가 사진 / 가운데 동일 카메라 Gaussian RGB / 오른쪽 고정 스케일 오차. TSDF 렌더 아님.",
                        selection_reason="All frozen evaluation photographs, no output-based ranking"))
            summary = args.out / "summary" / rid / ("R" + str(iteration))
            for name in ("geometry_comparison.csv", "render_comparison.csv", "new_render_per_image.csv"):
                path = summary / name
                if path.is_file():
                    manifest.setdefault("downloads", []).append(dict(
                        label=rid + " · " + label + " · " + name, url=public(path)))
        ids = [candidate["id"] for candidate in region["candidates"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate candidate IDs")
    manifest.setdefault("downloads", []).insert(0, dict(label="기존 Anchor512 비교 화면",
        url="/app/index.html?manifest=/task/evaluation/anchor_review_v1/manifest.json&color=height"))
    availability_status = "COMPLETE_GEOMETRY_MATRIX" if all(row["optimizer_updates"] is not None for row in availability) else "PARTIAL_GEOMETRY_MATRIX"
    manifest["condition_availability"] = availability
    manifest["comparison_profile"].update(availability_status=availability_status,
        selected_experiments={rid: str(path.relative_to(args.task)) for rid, path in selected_experiments.items()})
    write_json(destination / "availability.json", dict(schema="GEOGS_NO_ANCHOR_AVAILABILITY_v1",
        status=availability_status, scientific_verdict=None, entries=availability,
        selected_experiments=manifest["comparison_profile"]["selected_experiments"]))
    manifest.setdefault("downloads", []).append(dict(label="지역·조건별 실제 제공 상태", url=public(destination / "availability.json")))
    write_json(destination / "manifest.json", manifest)
    if sha(source) != args.source_manifest_sha256:
        raise ValueError("Original viewer changed during profile construction")
    write_json(destination / "receipt.json", dict(schema="GEOGS_SFM_NO_ANCHOR_VIEWER_PROFILE_v1",
        status="ADDITIVE_PROFILE_CREATED", scientific_verdict=None, created_unix=time.time(),
        source_manifest=base_url, source_manifest_sha256=args.source_manifest_sha256,
        manifest_sha256=sha(destination / "manifest.json"), script_sha256=sha(__file__),
        geometry_data_modified=False, original_files_modified=False,
        availability_status=availability_status, availability_sha256=sha(destination / "availability.json"),
        source_mesh_metadata=retained_files, new_evaluation_indexes=inspected_indexes,
        default_iteration=args.default_iteration,
        note="Producer availability is not browser QA. Pending candidates are explicit."))
    print(json.dumps(dict(status="ADDITIVE_PROFILE_CREATED",
        url=profile_url + "/manifest.json", scientific_verdict=None)))


if __name__ == "__main__":
    main()
