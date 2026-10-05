"""Read-only binding and deterministic selection for the one final resource retry."""
import argparse
import hashlib
import json
import math
from pathlib import Path

POLICY_PATH = "contracts/sfm_final_resource_retry_v1.json"
POLICY_SHA = "edf3f4312c622059a3506c6ca1c07d2b1c90e234fb672cc592ea3ea7e28f5a9a"
CONDITION = "SFM_noanchor_D005_Pnative"
PREDECESSORS = {"P1":"no_anchor_sfm_memory_recovery_v2", "P2":"no_anchor_sfm_memory_recovery_P2_v2", "P3":"no_anchor_sfm_memory_recovery_P3_v3"}
RETRIES = {region:"no_anchor_sfm_gradient_memory_v3_"+region for region in PREDECESSORS}
MEMORY_ERRORS = ("CUDA out of memory", "CUDA error: out of memory", "torch.cuda.OutOfMemoryError",
                 "PINNED_HOST_BUDGET_EXCEEDED", "_ArrayMemoryError", "MemoryError:", "std::bad_alloc", "DefaultCPUAllocator: can't allocate memory")


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(8<<20),b""):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def record(task,path):
    path=Path(path);relative=path.relative_to(task)
    if path.resolve()!=task.resolve()/relative or not path.is_file():raise ValueError("Expected direct immutable retry evidence")
    return dict(path=str(relative),bytes=path.stat().st_size,sha256=sha(path))


def policy(task):
    path=task/POLICY_PATH;value=read(path)
    if (sha(path)!=POLICY_SHA or value.get("schema")!="GEOGS_SFM_FINAL_RESOURCE_RETRY_POLICY_v1"
            or value.get("scientific_verdict") is not None or value.get("selected_predecessors")!=PREDECESSORS
            or value.get("retry_attempts")!=RETRIES or value.get("maximum_additional_fresh_training_attempts_per_region")!=1
            or value.get("runtime_identity")!={"resource_recovery_version":3,"storage_version":2}
            or value.get("fresh_initialization_only") is not True or value.get("checkpoint_resume_allowed") is not False
            or value.get("science_parameters_changed") is not False or value.get("quality_or_reference_driven_parameter_selection") is not False):
        raise ValueError("Frozen finite resource-retry policy differs")
    return value


def validate_cgroup_failure(proof, texts, receipt, receipt_sha, region, predecessor):
    """Require observed kernel/cgroup and container identity; SIGKILL alone is insufficient."""
    container = proof.get('container_id', '')
    victim = proof.get('victim_pid')
    kernel, inspect = texts.get('kernel_journal', ''), texts.get('docker_inspect', '')
    inspect_command = texts.get('docker_inspect_command', inspect)
    if (proof.get('schema') != 'GEOGS_NATIVE_RESOURCE_FAILURE_v1'
            or 'scientific_verdict' not in proof or proof['scientific_verdict'] is not None
            or proof.get('region') != region or proof.get('condition_id') != 'SFM_noanchor_D005_Pnative'
            or proof.get('native_exit_code') != -9 or receipt.get('native_exit_code') != -9
            or proof.get('cause') != 'CGROUP_OOM_KILL' or proof.get('kernel_oom_confirmed') is not True
            or proof.get('producer_receipt_sha256') != receipt_sha
            or not isinstance(container, str) or len(container) != 64
            or any(char not in '0123456789abcdef' for char in container)
            or not isinstance(victim, int) or isinstance(victim, bool) or victim <= 0
            or proof.get('limit_bytes') != 32 << 30
            or proof.get('cgroup_path') != '/system.slice/docker-' + container + '.scope'
            or set(texts) not in ({'kernel_journal', 'docker_inspect'},
                                 {'kernel_journal', 'docker_inspect', 'docker_inspect_command'})
            or 'constraint=CONSTRAINT_MEMCG' not in kernel
            or proof['cgroup_path'] not in kernel
            or ('task=python,pid=' + str(victim) + ',') not in kernel
            or ('Memory cgroup out of memory: Killed process ' + str(victim) + ' (python)') not in kernel
            or 'memory: usage 33554432kB, limit 33554432kB' not in kernel
            or container not in inspect
            or ('jbgs-geogs-' + predecessor + '-' + region + '-train') not in inspect_command):
        raise ValueError('SIGKILL lacks bound kernel cgroup OOM and predecessor container proof')
    return True


def bind_retry(task,experiment,region,amendment,bind=None):
    """Return exact evidence records; no current process or quality-based selection."""
    bind=bind or (lambda path:record(task,path))
    selected=Path(experiment)
    row=amendment.get("final_resource_retry")
    if row is None:
        if selected.name in RETRIES.values():raise ValueError("Final retry requires its explicit finite-policy amendment")
        return None
    policy(task)
    if region not in PREDECESSORS or selected!=task/RETRIES[region]:raise ValueError("Final retry is not the policy's fixed regional attempt")
    expected=dict(region=region,attempt_index=1,max_attempts=1,resource_recovery_version=3,storage_version=2,
        fresh_only=True,resume=False,automatic_further_retry=False,predecessor_attempt_id=PREDECESSORS[region])
    if any(key not in row or row[key]!=value for key,value in expected.items()):raise ValueError("Final retry limit, version or predecessor differs")
    if (amendment.get("status")!="SEALED_BEFORE_RETRY" or amendment.get("attempt_id")!=RETRIES[region]
            or amendment.get("resource_recovery_version")!=3 or amendment.get("storage_version")!=2):
        raise ValueError("Final retry amendment is not the sealed fixed runtime attempt")
    required_paths=dict(policy=task/POLICY_PATH,
        predecessor_training_receipt=task/PREDECESSORS[region]/"runs"/region/CONDITION/"receipt.json",
        predecessor_native_log=task/PREDECESSORS[region]/"runs"/region/CONDITION/"native.log",
        predecessor_amendment=task/PREDECESSORS[region]/"amendment.json")
    records={}
    for key,path in required_paths.items():
        actual=bind(path);declared=row[key]
        if any(actual[field]!=declared.get(field) for field in ("path","bytes","sha256")):
            raise ValueError("Final retry evidence identity changed: "+key)
        records[key]=actual
    parent=read(required_paths["predecessor_training_receipt"])
    if (parent.get("status")!="FAIL" or parent.get("phase")!="train" or parent.get("region")!=region
            or parent.get("condition_id")!=CONDITION or parent.get("scientific_verdict") is not None
            or parent.get("attempt_id")!=PREDECESSORS[region] or parent.get("iteration") is not None
            or type(parent.get("native_exit_code")) is not int or parent["native_exit_code"] not in (1,-9)
            or type(parent.get("validated_exit_code")) is not int or parent["validated_exit_code"]!=parent["native_exit_code"]
            or any(type(parent.get(key)) not in (int,float) or not math.isfinite(parent[key]) or parent[key]<0 for key in ("started_unix","finished_unix","wall_seconds"))
            or parent["finished_unix"]<=parent["started_unix"] or parent["wall_seconds"]<=0
            or any(flag in parent.get("command",[]) for flag in ("--jbgs_resume_full","--start_checkpoint"))):
        raise ValueError("Only an actual closed native training failure is eligible for the final retry")
    log=required_paths["predecessor_native_log"].read_text()
    observed=[token for token in MEMORY_ERRORS if token in log]
    cgroup_oom=False
    if row.get("predecessor_resource_failure") is not None:
        proof_record=row["predecessor_resource_failure"]
        proof_path=task/proof_record["path"];proof=read(proof_path);actual=bind(proof_path)
        if any(actual[key]!=proof_record.get(key) for key in ("path","bytes","sha256")):
            raise ValueError("Predecessor cgroup failure proof changed")
        texts={};resource_records=[]
        for item in proof.get("evidence",[]):
            role=item.get("role")
            source=task/item["path"];source_record=bind(source)
            if any(source_record[key]!=item.get(key) for key in ("path","bytes","sha256")):
                raise ValueError("Predecessor cgroup raw evidence changed")
            if role not in ("kernel_journal","docker_inspect","docker_inspect_command"):
                continue
            if role in texts:raise ValueError("Duplicate cgroup resource evidence role")
            texts[role]=source.read_text();resource_records.append(dict(role=role,**source_record))
        declared=row.get("resource_failure_evidence")
        if not isinstance(declared,list) or len(declared)!=len(resource_records) or any(
                any(actual.get(key)!=expected.get(key) for key in ("role","path","bytes","sha256"))
                for actual,expected in zip(resource_records,declared)):
            raise ValueError("Amendment cgroup resource evidence differs from the original proof")
        cgroup_oom=validate_cgroup_failure(proof,texts,parent,records["predecessor_training_receipt"]["sha256"],region,PREDECESSORS[region])
        records.update(predecessor_resource_failure=actual,resource_failure_evidence=resource_records,
            predecessor_resource_failure_classification="CGROUP_OOM_KILL")
    elif row.get("resource_failure_evidence"):
        raise ValueError("Cgroup raw evidence has no structured failure proof")
    if not observed and not cgroup_oom:raise ValueError("Predecessor has no bound resource-failure evidence")
    first_path=required_paths["predecessor_training_receipt"].parent/"model/jbgs_no_anchor/first_step.json"
    first=read(first_path);records["predecessor_first_step"]=bind(first_path)
    if (first.get("status")!="PASS_FIRST_STEP_DIRECT_REFINEMENT" or first.get("iteration")!=1
            or first.get("stage2_active") is not True or first.get("anchor_iterations_executed")!=0
            or first.get("pretrained_optimizer_loaded") is not False or first.get("scientific_verdict") is not None):
        raise ValueError("Predecessor did not pass its fresh-initialization first step")
    if not row.get("predecessor_first_step") or any(records["predecessor_first_step"][key]!=row["predecessor_first_step"].get(key) for key in ("path","bytes","sha256")):
        raise ValueError("Predecessor first-step record changed")
    previous=read(required_paths["predecessor_amendment"])
    if (amendment.get("region")!=region or amendment.get("scientific_verdict") is not None
            or amendment.get("arithmetic_or_scientific_controls_changed") is not False
            or previous.get("status")!="SEALED_BEFORE_RETRY" or previous.get("attempt_id")!=PREDECESSORS[region]
            or previous.get("region")!=region or previous.get("storage_version")!=2
            or previous.get("resource_recovery_version") is not None
            or amendment.get("original_config_sha256")!=previous.get("original_config_sha256")
            or parent.get("config_sha256")!=amendment.get("original_config_sha256")
            or parent.get("memory_recovery_amendment_path")!=str(required_paths["predecessor_amendment"].relative_to(task))
            or parent.get("memory_recovery_amendment_sha256")!=records["predecessor_amendment"]["sha256"]
            or sha(selected/"config.json")!=amendment.get("original_config_sha256")
            or sha(task/PREDECESSORS[region]/"config.json")!=amendment.get("original_config_sha256")):
        raise ValueError("Final retry changed the regional science/configuration contract")
    for key in ("original_failed_run_receipt","prior_resource_attempts","prior_initialization_failure"):
        if amendment.get(key)!=previous.get(key):raise ValueError("Final retry dropped or changed predecessor history: "+key)
    return dict(**expected,**records,classification="FINAL_RESOURCE_ONLY_FRESH_RETRY",
        predecessor_training_status="FAIL",predecessor_native_exit_code=parent["native_exit_code"],
        observed_resource_error_tokens=observed,quality_based_selection=False,
        historical_prefix_replacement_allowed=False,scientific_verdict=None)


def select(task,overrides=None):
    """Choose a sealed attempt even if it later fails; never choose by quality."""
    overrides=overrides or {}
    if set(overrides)-set(PREDECESSORS):raise ValueError("Unknown regional selection")
    has_policy=(task/POLICY_PATH).is_file()
    if has_policy:policy(task)
    result={};reasons={};records=[]
    for region,previous in PREDECESSORS.items():
        if region in overrides:
            selected=Path(overrides[region]);reason="EXPLICIT_REGIONAL_ARGUMENT"
        elif has_policy and (task/RETRIES[region]/"amendment.json").is_file():
            selected=task/RETRIES[region];reason="FIXED_POLICY_SEALED_FINAL_RETRY"
        else:selected=task/previous;reason="FIXED_PREDECESSOR_NO_SEALED_RETRY"
        if not selected.is_absolute() or not selected.resolve().is_relative_to(task.resolve()):raise ValueError("Selection must remain inside the task")
        if selected.name in RETRIES.values():
            amendment=read(selected/"amendment.json")
            bound=bind_retry(task,selected,region,amendment)
            records.append(dict(region=region,amendment=record(task,selected/"amendment.json"),final_resource_retry=bound))
        result[region]=str(selected.relative_to(task));reasons[region]=reason
    return dict(schema="GEOGS_REGIONAL_PRODUCER_SELECTION_v1",scientific_verdict=None,
        selected_experiments=result,selection_reasons=reasons,quality_or_reference_selection=False,
        policy=record(task,task/POLICY_PATH) if has_policy else None,final_retry_evidence=records)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument("--task",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--region-experiment",action="append",default=[])
    a=p.parse_args();overrides={}
    for item in a.region_experiment:
        rid,separator,path=item.partition("=")
        if not separator or rid in overrides:raise ValueError("Unique regional overrides required")
        overrides[rid]=path
    value=select(a.task,overrides)
    with a.out.open("x") as stream:json.dump(value,stream,indent=2,ensure_ascii=False);stream.write("\n")
    with a.out.with_suffix(".args").open("x") as stream:
        for region,relative in value["selected_experiments"].items():stream.write("--region-experiment\n"+region+"=/task/"+relative+"\n")
    print(json.dumps(value["selected_experiments"]))


if __name__=="__main__":main()
