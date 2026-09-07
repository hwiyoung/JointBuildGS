"""Build an isolated fixed-8000 diagnostic profile; preserve full-run outcomes."""
import argparse
import copy
import importlib.util
from pathlib import Path
import re
import time
from urllib.parse import urljoin

SOURCE_SHA = "12ba0d9a54b7313a7ded96fb9ceb255d0489948e1e18f4d3dadfb1ebcfda61d6"


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--task",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--publish-id",required=True)
    p.add_argument("--core-evaluator",type=Path,default=Path(__file__).resolve().parents[1]/"evaluate.py")
    p.add_argument("--core-builder",type=Path,default=Path(__file__).resolve().parents[1]/"build_viewer.py")
    a=p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+",a.publish_id):raise ValueError("Fresh simple profile identifier required")
    ev=module("prefix_evaluation",Path(__file__).with_name("evaluate.py"))
    base=module("prefix_viewer_helpers",a.core_builder)
    c=ev.core(a)
    policy=c.read_json(a.task/ev.POLICY_PATH)
    a.region="P1";a.experiment=a.task/policy["selected_attempts"]["P1"];a.public_root=ev.PUBLIC_ROOT;a.iteration=8000
    ev.policy(a)
    source=a.task/"evaluation/viewer/manifest_v2.json"
    if c.sha(source)!=SOURCE_SHA:raise ValueError("Original GeoGS viewer manifest differs")
    manifest=base.absolute_urls(copy.deepcopy(c.read_json(source)),"/task/evaluation/viewer/manifest_v2.json")
    original_lineage={key:manifest.pop(key) for key in list(manifest) if key.startswith(("runtime_layout_","repeat_contract_","completion_contract_","resource_contract_")) or key in ("evaluation_scope","runs_directory","resource_revision","supplemental_repeat_id")}
    destination=a.out/"profiles"/a.publish_id
    destination.mkdir(parents=True,exist_ok=False)
    def public(path):return ev.PUBLIC_ROOT+"/"+str(path.relative_to(a.out))
    manifest.update(title="GeoGS — 조건부 8,000회 보조 진단",scientific_verdict=None,
        default_resolution="512",source_experiment_lineage=original_lineage,
        resolution_modes=[dict(id="512",label="모든 결과 동일 TSDF 512",mesh_res=512,anchor_variant="anchor_512",final_variant="mesh_512")],
        comparison_profile=dict(experiment="no_anchor_sfm_prefix8000_v1",analysis_role=ev.ROLE,
            optimizer_updates=8000,planned_total_updates=30000,main_experiment_replaced=False,
            source_manifest="/task/evaluation/viewer/manifest_v2.json",source_manifest_sha256=SOURCE_SHA,
            policy=dict(url="/task/"+ev.POLICY_PATH,sha256=ev.POLICY_SHA),scientific_verdict=None),
        notes=["③ 기존 ALS Anchor8000과 ⑤ SfM refinement8000이 같은 업데이트 수의 주 비교입니다.",
            "④ 기존 final30000은 학습량이 다른 참고 결과입니다. 8k 중간 진단은 22k/30k 실험을 대체하지 않습니다.",
            "전체 학습 실패/미완료와 검증된 8k 중간 결과의 제공 여부를 따로 기록합니다.",
            "세 지역 모두 고정 8000 checkpoint를 사용합니다. 없는 결과를 다른 시점이나 기존 표면으로 대체하지 않습니다.",
            "초기화·감독·보호 membership이 함께 다르므로 Anchor 단독 효과 검증이나 image-only 실험이 아닙니다.",
            "raw/post, Gaussian RGB와 TSDF 표면을 구분합니다. 관측된 UAS 근접성은 시간적 유효성의 완전한 정답이 아닙니다."])
    availability=[];retained=[];indexes=[]
    for region in manifest["regions"]:
        rid=region["id"];a.region=rid;a.experiment=a.task/policy["selected_attempts"][rid]
        run=a.experiment/"runs"/rid/c.RUN_CONDITION
        parent_path=run/"receipt.json"
        parent=c.read_json(parent_path) if parent_path.is_file() else None
        if parent is not None and (parent.get("status") not in ("PASS","FAIL") or parent.get("region")!=rid or parent.get("phase")!="train"):
            raise ValueError("Parent training receipt identity differs")
        parent_record=base.task_record(a.task,parent_path) if parent else None
        parent_status=parent["status"] if parent else "NOT_CLOSED"
        producer_root=a.task/policy["producer_root"]/rid
        validation_path=producer_root/"validation/receipt.json"
        export_path=producer_root/"export/receipt.json"
        evidence=[parent_record] if parent_record else []
        reason="조건부 8k 진단의 발동·완전 상태 검증·공식 추출을 기다립니다."
        status="pending";failure_phase=None
        for phase,path in (("prefix_validation",validation_path),("export",export_path)):
            if not path.is_file():break
            record=base.task_record(a.task,path);value=c.read_json(path);evidence.append(record)
            allowed=("PREFIX_8000_VALIDATED","FAIL_PREFIX_VALIDATION","NOT_READY") if phase=="prefix_validation" else ("PASS","FAIL")
            if value.get("region")!=rid or value.get("scientific_verdict") is not None or value.get("status") not in allowed:
                raise ValueError("Prefix producer identity or status differs")
            if value.get("status") in ("FAIL", "FAIL_PREFIX_VALIDATION"):
                status="failed";failure_phase=phase
                reason=("8k 중간 상태 검증" if phase=="prefix_validation" else "8k 공식 표면·RGB 추출")+" 실패. 다른 결과로 대체하지 않습니다."
                break
            if value.get("status")=="NOT_READY":break
        region["default_condition"]=ev.CONDITION
        region["panel_candidates"].update(anchor="D005_Pnative.anchor_512.raw",vanilla="D005_Pnative.mesh_512.raw")
        region["notes"]=["③ ALS Anchor8000 ↔ ⑤ SfM refinement8000: 주 비교. ④ final30000: 다른 학습량의 참고 결과.",
            "선택한 전체 학습 상태: "+parent_status+". 8k 제공 여부와 별개이며 22k/30k 완료를 의미하지 않습니다."]
        for candidate in region["candidates"]:
            descriptor=candidate.get("mesh_data")
            if not descriptor:continue
            original=a.task/descriptor["url"].removeprefix("/task/")
            if not descriptor["url"].startswith("/task/") or (descriptor.get("sha256") and c.sha(original)!=descriptor["sha256"]):
                raise ValueError("Existing mesh descriptor differs")
            target=destination/"baseline_mesh_metadata"/rid/(candidate["id"]+".json")
            c.write_json(target,base.absolute_urls(c.read_json(original),"/task/evaluation/viewer/manifest_v2.json"))
            candidate["mesh_data"]=dict(format="json",url=public(target),sha256=c.sha(target),bytes=target.stat().st_size)
            retained.append(dict(source=str(original.relative_to(a.task)),source_sha256=c.sha(original),new_metadata=public(target),binary_geometry_modified=False))
        region["sections"]=[r for r in region.get("sections",[]) if r["id"].split(".")[0] in ("als_points","mvs_points","prior_mesh") or ".anchor_512." in r["id"] or ".mesh_512." in r["id"] or r["id"].endswith(".anchor_refinement_512")]
        for collection in ("sections","renders"):
            for row in region.get(collection,[]):
                if row.get("condition_id"):
                    row["source_condition_id"]=row["condition_id"];row["condition_id"]=None
                    row["label"]=row["source_condition_id"]+" · 기존 비교 자료 · "+(row.get("label") or row["id"])
        attempt=dict(experiment_source_relative=str(a.experiment.relative_to(a.task)),execution_attempt_id=a.experiment.name,
            analysis_role=ev.ROLE,parent_training_status=parent_status,parent_training_receipt=parent_record,
            target_optimizer_updates=8000,optimizer_updates=None,planned_total_updates=30000,
            full_experiment_completion_inferred=False,scientific_verdict=None,evidence=evidence)
        label="SfM·Anchor 생략 · 8,000회 중간 진단"
        entry=dict(id=ev.CONDITION,label=label,candidate_id=ev.CONDITION+".mesh_512.raw",anchor_executed=False,
            optimizer_updates=None,target_optimizer_updates=8000,planned_total_updates=30000,analysis_role=ev.ROLE,execution_attempt=attempt)
        region["conditions"].append(entry)
        index_path=a.out/"geometry"/rid/"R8000_viewer_index.json"
        if index_path.is_file():
            if status=="failed":raise ValueError("Failed prefix validation/export cannot provide geometry")
            seal,digest=ev.load_seal(a)
            if seal["parent_training_status"]!=parent_status:raise ValueError("Parent state differs from sealed prefix")
            index=c.read_json(index_path)
            if (index.get("status")!="GEOMETRY_EVALUATED" or index.get("analysis_role")!=ev.ROLE or index.get("condition")!=ev.CONDITION
                    or index.get("region")!=rid or index.get("optimizer_updates")!=8000 or index.get("new_condition_seal_sha256")!=digest
                    or {r["id"] for r in index["candidates"]}!={ev.CONDITION+".mesh_512."+k for k in ("raw","post")}):
                raise ValueError("Prefix geometry identity differs")
            attempt.update(a.execution_metadata)
            attempt.update(optimizer_updates=8000,prefix_snapshot_available=True)
            # Retain URL-bearing parent receipt for display, and both prefix/parent status.
            attempt["parent_training_receipt"]=parent_record
            entry["optimizer_updates"]=8000
            for candidate in copy.deepcopy(index["candidates"]):
                candidate["label"]=label+" · "+candidate["id"].rsplit(".",1)[1]
                candidate.setdefault("provenance",{})["execution_attempt"]=attempt
                candidate["optimizer_updates"]=8000;candidate["analysis_role"]=ev.ROLE
                candidate.setdefault("downloads",[]).extend([dict(label="전체 학습 원 상태",url=parent_record["url"]),
                    dict(label="8k 상태 검증",url="/task/"+seal["prefix_validation_receipt"]["path"]),dict(label="8k 평가 봉인",url=public(c.seal_path(a)))])
                if attempt.get("memory_recovery_amendment_path"):
                    candidate["downloads"].append(dict(label="실행 메모리 배치 계보",url="/task/"+attempt["memory_recovery_amendment_path"]))
                if attempt.get("original_failed_run_receipt"):
                    candidate["downloads"].append(dict(label="보존된 원 실패 실행",url="/task/"+attempt["original_failed_run_receipt"]["path"]))
                for history in attempt.get("prior_resource_attempts",[]):
                    candidate["downloads"].extend(dict(label="이전 자원 실행 근거",url="/task/"+history[k]["path"]) for k in ("receipt","stop_intent"))
                if attempt.get("prior_initialization_failure"):
                    candidate["downloads"].extend(dict(label="이전 초기화 실패 근거",url="/task/"+attempt["prior_initialization_failure"][k]["path"]) for k in ("receipt","log"))
                region["candidates"].append(candidate)
                availability.append(dict(region=rid,condition=ev.CONDITION,candidate=candidate["id"],status=candidate["status"],optimizer_updates=8000,
                    planned_total_updates=30000,parent_training_status=parent_status,analysis_role=ev.ROLE,execution_attempt=attempt))
                for key,title in (("section_url","고정 단면"),("distance_url","참조 거리 지도")):
                    region["sections"].append(dict(id=candidate["id"]+"."+key,label=label+" · "+title,url=candidate[key],condition_id=ev.CONDITION,
                        comparison_family="동일8k·512 보조 진단",selection_reason="Frozen regional sections; no result-based selection"))
            indexes.append(dict(path=public(index_path),sha256=c.sha(index_path)))
        else:
            entry["label"]+= " · 실행 실패" if status=="failed" else " · 제공 대기"
            for kind in ("raw","post"):
                candidate=dict(id=ev.CONDITION+".mesh_512."+kind,label=label+" · "+kind,role="changed",status=status,
                    reason=reason,failure_phase=failure_phase,quality_status="NOT_ASSESSED_PREFIX_"+("FAILURE" if status=="failed" else "PENDING"),
                    optimizer_updates=None,target_optimizer_updates=8000,planned_total_updates=30000,analysis_role=ev.ROLE,
                    data=None,mesh_data=None,surface_kind="triangle_surface",provenance=dict(execution_attempt=attempt),
                    downloads=[dict(label="원 상태·8k 실행 근거 "+str(i+1),url=r["url"]) for i,r in enumerate(evidence)])
                region["candidates"].append(candidate)
                availability.append(dict(region=rid,condition=ev.CONDITION,candidate=candidate["id"],status=status,optimizer_updates=None,
                    planned_total_updates=30000,parent_training_status=parent_status,analysis_role=ev.ROLE,execution_attempt=attempt))
        render_root=a.out/"renders"/rid/ev.CONDITION/"refinement_only"
        if (render_root/"receipt.json").is_file():
            seal,digest=ev.load_seal(a);receipt=c.read_json(render_root/"receipt.json")
            if receipt.get("status") not in ("PASS_RENDER_QUALITY_EVALUATION","COMPLETE_WITH_RECORDED_FAILURES") or receipt.get("condition")!=ev.CONDITION or receipt.get("region")!=rid or receipt.get("sealed_render_manifest_sha256")!=digest:
                raise ValueError("Actual prefix RGB evidence differs")
            for row in receipt["rows"]:
                montage=row.get("montage")
                if not montage:continue
                path=Path(montage)
                if not path.is_absolute():path=render_root/path
                if not path.is_file() or not path.is_relative_to(a.out):raise ValueError("Missing actual prefix RGB montage")
                region["renders"].append(dict(id=ev.CONDITION+"."+row["domain"]+"."+str(row["evaluation_index"]),label=label+" · "+row["name"]+" · "+row["domain"],
                    condition_id=ev.CONDITION,url=public(path),image_name=row["name"],domain=row["domain"],split="evaluation",
                    stage="refinement_only",optimizer_updates=8000,analysis_role=ev.ROLE,
                    caption="왼쪽 고정 평가 사진 / 가운데 8k Gaussian RGB / 오른쪽 오차. 기존 Anchor8000이 주 비교이며 final30000은 참고입니다."))
        for name in ("geometry_comparison.csv","render_comparison.csv","new_render_per_image.csv"):
            path=a.out/"summary"/rid/"R8000"/name
            if path.is_file():manifest.setdefault("downloads",[]).append(dict(label=rid+" · 8k · "+name,url=public(path)))
    manifest["condition_availability"]=availability
    state="COMPLETE_PREFIX_GEOMETRY_MATRIX" if all(r["optimizer_updates"]==8000 for r in availability) else "PARTIAL_PREFIX_GEOMETRY_MATRIX"
    manifest["comparison_profile"].update(availability_status=state,selected_experiments=policy["selected_attempts"])
    c.write_json(destination/"availability.json",dict(schema="GEOGS_PREFIX8000_AVAILABILITY_v1",status=state,analysis_role=ev.ROLE,scientific_verdict=None,entries=availability))
    manifest.setdefault("downloads",[]).extend([dict(label="조건부 8k 진단 계약",url="/task/"+ev.POLICY_PATH),dict(label="8k 제공 여부와 전체 학습 상태",url=public(destination/"availability.json"))])
    c.write_json(destination/"manifest.json",manifest)
    if c.sha(source)!=SOURCE_SHA:raise ValueError("Original manifest changed during profile construction")
    c.write_json(destination/"receipt.json",dict(schema="GEOGS_PREFIX8000_VIEWER_PROFILE_v1",status="ADDITIVE_PREFIX_PROFILE_CREATED",scientific_verdict=None,
        analysis_role=ev.ROLE,source_manifest_sha256=SOURCE_SHA,policy_sha256=ev.POLICY_SHA,manifest_sha256=c.sha(destination/"manifest.json"),
        script_sha256=c.sha(__file__),core_evaluator_sha256=c.sha(a.core_evaluator),core_builder_sha256=c.sha(a.core_builder),
        source_mesh_metadata=retained,new_evaluation_indexes=indexes,original_files_modified=False,created_unix=time.time()))
    print(public(destination/"manifest.json"))


if __name__=="__main__":main()
