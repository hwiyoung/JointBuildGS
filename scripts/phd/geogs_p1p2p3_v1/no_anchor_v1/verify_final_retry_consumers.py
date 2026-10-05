"""Small synthetic consumer tests; no scene quality, native training or GPU use."""
import argparse
import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,allow_nan=False))


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--policy",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--previous-core",type=Path)
    parser.add_argument("--sealer",type=Path)
    parser.add_argument("--actual-task",type=Path)
    parser.add_argument("--actual-region",action="append",default=[])
    args=parser.parse_args();checks=[]
    if not Path("/.dockerenv").is_file():raise RuntimeError("Docker only")
    retry=module("final_retry_test",args.source/"final_retry.py")
    evaluate=module("final_retry_evaluate_test",args.source/"evaluate.py")
    viewer=module("final_retry_viewer_test",args.source/"build_viewer.py")
    resources=module("final_retry_resources_test",args.source/"summarize_resources.py")
    def check(name,result):
        checks.append(dict(name=name,passed=bool(result)))
        if not result:raise AssertionError(name)
    def reject(name,callback):
        try:callback()
        except (ValueError,KeyError,FileNotFoundError):check(name,True);return
        check(name,False)
    def fixture(base):
        task=base/"task";task.mkdir()
        path=task/retry.POLICY_PATH;path.parent.mkdir();shutil.copyfile(args.policy,path)
        original=task/"no_anchor_sfm_v1";previous=task/retry.PREDECESSORS["P1"]
        selected=task/retry.RETRIES["P1"];replaced=task/"no_anchor_sfm_memory_recovery_v1"
        cfg=dict(task_id="synthetic_only",condition_id=retry.CONDITION,regions=["P1"],runtime_image_id="synthetic",
            training=dict(lambda_lod_anchor=.005,export_iterations=[22000,30000]))
        for root in (original,previous,selected,replaced):put(root/"config.json",cfg)
        def receipt(root,native,seconds):
            run=root/"runs/P1"/retry.CONDITION
            row=dict(status="FAIL",region="P1",condition_id=retry.CONDITION,phase="train",scientific_verdict=None,
                attempt_id=root.name,iteration=None,
                native_exit_code=native,validated_exit_code=native,started_unix=1.,finished_unix=seconds+1.,wall_seconds=seconds,
                child_peak_rss_bytes=1024,config_sha256=retry.sha(original/"config.json"),runtime_image_id="synthetic")
            put(run/"receipt.json",row);(run/"native.log").write_text("CUDA error: out of memory\n")
            return run,row
        oldrun,old=receipt(original,1,100.)
        stoppedrun,stopped=receipt(replaced,-15,50.)
        stop=dict(region="P1",cause="RESOURCE_TRANSFER_OPTIMIZATION",scientific_verdict=None)
        put(stoppedrun/"stop_intent.json",stop)
        previous_amendment=dict(region="P1",scientific_verdict=None,arithmetic_or_scientific_controls_changed=False,
            status="SEALED_BEFORE_RETRY",attempt_id=previous.name,storage_version=2,
            original_config_sha256=retry.sha(original/"config.json"),memory_placement_changes=["placement only"],
            original_failed_run_receipt=retry.record(task,oldrun/"receipt.json"),
            prior_resource_attempts=[dict(receipt=retry.record(task,stoppedrun/"receipt.json"),
                stop_intent=retry.record(task,stoppedrun/"stop_intent.json"))])
        put(previous/"amendment.json",previous_amendment)
        parentrun,parent=receipt(previous,1,1200.)
        parent.update(memory_recovery_amendment_path=str((previous/"amendment.json").relative_to(task)),
            memory_recovery_amendment_sha256=retry.sha(previous/"amendment.json"))
        put(parentrun/"receipt.json",parent)
        firstpath=parentrun/"model/jbgs_no_anchor/first_step.json"
        put(firstpath,dict(status="PASS_FIRST_STEP_DIRECT_REFINEMENT",iteration=1,stage2_active=True,
            anchor_iterations_executed=0,pretrained_optimizer_loaded=False,scientific_verdict=None))
        paths=dict(policy=task/retry.POLICY_PATH,predecessor_training_receipt=parentrun/"receipt.json",
            predecessor_native_log=parentrun/"native.log",predecessor_amendment=previous/"amendment.json",
            predecessor_first_step=firstpath)
        amendment=dict(copy.deepcopy(previous_amendment),attempt_id=selected.name,resource_recovery_version=3,storage_version=2)
        amendment["final_resource_retry"]=dict(region="P1",predecessor_attempt_id=previous.name,
            attempt_index=1,max_attempts=1,resource_recovery_version=3,storage_version=2,fresh_only=True,
            resume=False,automatic_further_retry=False,**{key:retry.record(task,path) for key,path in paths.items()})
        put(selected/"amendment.json",amendment)
        return SimpleNamespace(task=task,original=original,previous=previous,selected=selected,replaced=replaced,
            cfg=cfg,parentrun=parentrun,parent=parent,firstpath=firstpath,paths=paths,amendment=amendment)
    def bound(f):return retry.bind_retry(f.task,f.selected,"P1",f.amendment)
    def write_amendment(f):put(f.selected/"amendment.json",f.amendment)
    def cgroup_fixture(f):
        f.parent.update(native_exit_code=-9,validated_exit_code=-9)
        put(f.paths["predecessor_training_receipt"],f.parent)
        f.paths["predecessor_native_log"].write_text("native child ended without Python exception")
        for key in ("predecessor_training_receipt","predecessor_native_log"):
            f.amendment["final_resource_retry"][key]=retry.record(f.task,f.paths[key])
        container="a"*64;victim=123
        directory=f.task/"resource_observations/P1";directory.mkdir(parents=True)
        texts=dict(kernel_journal="constraint=CONSTRAINT_MEMCG /system.slice/docker-"+container+".scope task=python,pid=123,\nMemory cgroup out of memory: Killed process 123 (python)\nmemory: usage 33554432kB, limit 33554432kB",
            docker_inspect=container,docker_inspect_command="docker inspect jbgs-geogs-"+f.previous.name+"-P1-train",
            unavailable_observation="process already gone")
        records=[]
        for role,text in texts.items():
            path=directory/(role+".txt");path.write_text(text);records.append(dict(role=role,**retry.record(f.task,path)))
        proof=dict(schema="GEOGS_NATIVE_RESOURCE_FAILURE_v1",scientific_verdict=None,region="P1",condition_id=retry.CONDITION,
            native_exit_code=-9,cause="CGROUP_OOM_KILL",kernel_oom_confirmed=True,container_id=container,victim_pid=victim,
            cgroup_path="/system.slice/docker-"+container+".scope",limit_bytes=32<<30,
            producer_receipt_sha256=retry.sha(f.paths["predecessor_training_receipt"]),evidence=records)
        proofpath=directory/"resource_failure_receipt.json";put(proofpath,proof)
        f.amendment["final_resource_retry"].update(predecessor_resource_failure=retry.record(f.task,proofpath),
            resource_failure_evidence=records[:3])
        write_amendment(f);return proofpath,proof,texts
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        count=0
        def fresh():
            nonlocal count
            count+=1;base=root/str(count);base.mkdir();return fixture(base)
        f=fresh();baseline=bound(f)
        check("finite_retry_valid_original_native_failure",baseline["predecessor_native_exit_code"]==1)
        check("fixed_selector_chooses_sealed_retry",retry.select(f.task)["selected_experiments"]["P1"]==f.selected.name)
        check("explicit_predecessor_is_preserved",retry.select(f.task,{"P1":str(f.previous)})["selected_experiments"]["P1"]==f.previous.name)
        (f.selected/"amendment.json").unlink()
        check("empty_retry_directory_never_masks_predecessor",retry.select(f.task)["selected_experiments"]["P1"]==f.previous.name)
        write_amendment(f)
        for field,value in (("max_attempts",2),("attempt_index",2),("resume",True),("fresh_only",False),
                ("automatic_further_retry",True),("resource_recovery_version",2),("region","P2"),("predecessor_attempt_id","foreign")):
            g=fresh();g.amendment["final_resource_retry"][field]=value
            reject("reject_final_"+field,lambda:bound(g))
        g=fresh();del g.amendment["final_resource_retry"]["predecessor_first_step"]
        reject("reject_missing_first_step_record",lambda:bound(g))
        g=fresh();g.amendment.pop("prior_resource_attempts")
        reject("reject_dropped_prior_history",lambda:bound(g))
        g=fresh();g.amendment["final_resource_retry"]["predecessor_native_log"]["sha256"]="0"*64
        write_amendment(g);reject("corrupt_retry_never_silently_falls_back",lambda:retry.select(g.task))
        g=fresh();(g.task/retry.POLICY_PATH).write_text("{}")
        reject("reject_unpinned_policy",lambda:bound(g))
        for name,patch in (("native_success",dict(status="PASS",native_exit_code=0,validated_exit_code=0)),
                ("intentional_sigterm",dict(native_exit_code=-15,validated_exit_code=-15)),
                ("validated_mismatch",dict(validated_exit_code=0)),("unclosed",dict(finished_unix=None)),
                ("negative_wall",dict(wall_seconds=-1.)),("wrong_region",dict(region="P2"))):
            g=fresh();g.parent.update(patch);put(g.paths["predecessor_training_receipt"],g.parent)
            g.amendment["final_resource_retry"]["predecessor_training_receipt"]=retry.record(g.task,g.paths["predecessor_training_receipt"])
            reject("reject_predecessor_"+name,lambda:bound(g))
        g=fresh();g.parent.update(native_exit_code=-9,validated_exit_code=-9)
        put(g.paths["predecessor_training_receipt"],g.parent)
        g.amendment["final_resource_retry"]["predecessor_training_receipt"]=retry.record(g.task,g.paths["predecessor_training_receipt"])
        check("closed_native_minus9_with_resource_log_allowed",bound(g)["predecessor_native_exit_code"]==-9)
        for token in retry.MEMORY_ERRORS:
            g=fresh();g.paths["predecessor_native_log"].write_text(token)
            g.amendment["final_resource_retry"]["predecessor_native_log"]=retry.record(g.task,g.paths["predecessor_native_log"])
            check("recognized_resource_token_"+token,token in bound(g)["observed_resource_error_tokens"])
        g=fresh();g.paths["predecessor_native_log"].write_text("native process exited")
        g.amendment["final_resource_retry"]["predecessor_native_log"]=retry.record(g.task,g.paths["predecessor_native_log"])
        reject("reject_exit_without_resource_cause",lambda:bound(g))
        g=fresh();proofpath,proof,texts=cgroup_fixture(g)
        check("minus9_with_bound_kernel_proof_and_extra_noncausal_observations",bound(g)["predecessor_resource_failure_classification"]=="CGROUP_OOM_KILL")
        for key,value in (("kernel_oom_confirmed",False),("producer_receipt_sha256","wrong"),("victim_pid",999),
                ("limit_bytes",16<<30),("container_id","b"*64),("region","P2")):
            damaged=dict(proof,**{key:value})
            reject("reject_cgroup_"+key,lambda:retry.validate_cgroup_failure(damaged,{key:text for key,text in texts.items() if key!="unavailable_observation"},g.parent,
                retry.sha(g.paths["predecessor_training_receipt"]),"P1",g.previous.name))
        raw=g.task/proof["evidence"][-1]["path"];raw.write_text("changed noncausal observation")
        reject("all_cgroup_evidence_bytes_verified_even_noncausal_observations",lambda:bound(g))
        g=fresh();cgroup_fixture(g)
        evidence=resources.Evidence();cfg=evidence.json(g.original/"config.json")
        attempts=resources.closed_training_attempt_records(evidence,g.task,g.original,cfg,{"P1":g.selected})
        cgroup=[row for row in attempts if row["history_kind"]=="FINAL_RETRY_PREDECESSOR"]
        check("cgroup_cost_separate_from_cuda_oom",len(cgroup)==1 and cgroup[0]["termination_reason"]=="CGROUP_OOM_KILL" and not cgroup[0]["counted_as_training_cuda_oom"])
        g=fresh();first=retry.read(g.firstpath);first["anchor_iterations_executed"]=8000;put(g.firstpath,first)
        g.amendment["final_resource_retry"]["predecessor_first_step"]=retry.record(g.task,g.firstpath)
        reject("reject_predecessor_anchor_execution",lambda:bound(g))
        f=fresh();amendment_record=retry.record(f.task,f.selected/"amendment.json")
        producer=dict(memory_recovery_amendment_path=amendment_record["path"],memory_recovery_amendment_sha256=amendment_record["sha256"])
        evargs=SimpleNamespace(task=f.task,experiment=f.selected,region="P1",iteration=22000,
            out=f.task/"evaluation/no_anchor_sfm_v1",public_root=evaluate.DEFAULT_PUBLIC_ROOT)
        bind=lambda path:evaluate.source_file(f.task,path)
        evargs.execution_metadata=evaluate.recovery_metadata(evargs,producer,producer,bind(f.original/"config.json"),bind)
        check("evaluator_binds_full_final_retry",evargs.execution_metadata["final_resource_retry"]==bound(f))
        seal=dict(status="SNAPSHOT_AND_RENDER_BYTES_SEALED",**evaluate.binding(evargs),files=[])
        put(evaluate.seal_path(evargs),seal)
        check("seal_reloads_exact_policy_chain",evaluate.load_seal(evargs)[0]["final_resource_retry"]==bound(f))
        damaged=copy.deepcopy(seal);damaged.pop("final_resource_retry");put(evaluate.seal_path(evargs),damaged)
        reject("reject_final_snapshot_without_policy",lambda:evaluate.load_seal(evargs))
        put(evaluate.seal_path(evargs),seal)
        attempt=viewer.inspect_attempt(f.task,f.selected,"P1",22000)
        check("pending_retry_not_masked_by_predecessor_failure",attempt["status"]=="pending" and attempt["optimizer_updates"] is None)
        check("pending_downloads_include_all_five_retry_records",len(viewer.final_retry_downloads(attempt))==5)
        run=f.selected/"runs/P1"/retry.CONDITION
        failed=dict(f.parent,**producer,native_exit_code=1,validated_exit_code=1,wall_seconds=30.,finished_unix=31.)
        put(run/"receipt.json",failed);(run/"native.log").write_text("PINNED_HOST_BUDGET_EXCEEDED")
        attempt=viewer.inspect_attempt(f.task,f.selected,"P1",22000)
        check("actual_host_memory_failure_label_is_not_cuda",attempt["failure_kind"]=="HOST_MEMORY_RESOURCE_FAILURE")
        check("final_failure_never_selects_old_trajectory",retry.select(f.task)["selected_experiments"]["P1"]==f.selected.name)
        evidence=resources.Evidence();cfg=evidence.json(f.original/"config.json")
        availability,training,phases=resources.new_records(evidence,f.original,cfg,{"P1":f.selected})
        attempts=resources.closed_training_attempt_records(evidence,f.task,f.original,cfg,{"P1":f.selected})
        check("failed_selected_training_has_no_quality_or_completed_phase",not training and not phases and availability[0]["training_status"]=="FAIL")
        check("predecessor_cost_kept_once_with_initial_and_intentional_attempts",len(attempts)==4 and len({row["source_path"] for row in attempts})==4 and sum(row["wall_seconds"] for row in attempts)==1380.)
        check("intentional_stop_and_host_failure_classifications_distinct",any(row["termination_reason"]=="INTENTIONAL_RESOURCE_TRANSFER_REPLACEMENT" for row in attempts) and any(row["termination_reason"]=="HOST_MEMORY_RESOURCE_FAILURE" for row in attempts))
        check("failed_predecessor_cost_has_separate_history_role",sum(row["history_kind"]=="FINAL_RETRY_PREDECESSOR" for row in attempts)==1)
        check("legacy_attempt_without_final_metadata_unchanged",resources.final_retry_binding(evidence,f.task,f.previous,"P1") is None)
        # Exercise complete builder control flow with synthetic metadata only.
        original=dict(scientific_verdict=None,regions=[dict(id=rid,candidates=[],conditions=[],panel_candidates={},renders=[],sections=[]) for rid in retry.PREDECESSORS])
        source=f.task/"evaluation/viewer/manifest_v2.json";put(source,original)
        selection=retry.select(f.task);selectionpath=evargs.out/"selection.json";put(selectionpath,selection)
        oldargv=sys.argv
        def build(profile):
            sys.argv=["build_viewer.py","--task",str(f.task),"--out",str(evargs.out),"--source-manifest-sha256",retry.sha(source),
                "--publish-id",profile,"--selection-record",str(selectionpath.relative_to(f.task))]
            for rid,relative in selection["selected_experiments"].items():sys.argv.extend(["--region-experiment",rid+"="+str(f.task/relative)])
            try:viewer.main()
            finally:sys.argv=oldargv
            return retry.read(evargs.out/"profiles"/profile/"manifest.json")
        manifest=build("synthetic_failed")
        check("builder_has_no_geometry_fallback_for_failed_or_pending",all(row["optimizer_updates"] is None for row in manifest["condition_availability"]))
        selectedrow=manifest["regions"][0]["candidates"][0]
        check("builder_failed_candidate_links_finite_policy",any("sfm_final_resource_retry_v1.json" in row["url"] for row in selectedrow["downloads"]))
        # Synthetic available snapshot proves new binding does not break completed metadata.
        failed.update(status="PASS",native_exit_code=0,validated_exit_code=0);put(run/"receipt.json",failed)
        for n in (22000,30000):
            put(run/"exports"/("iteration_"+str(n))/"receipt.json",dict(failed,phase="export",iteration=n))
        cid=evaluate.condition(22000)
        candidates=[dict(id=cid+".mesh_512."+kind,status="available",section_url="/task/synthetic/section.png",distance_url="/task/synthetic/distance.png") for kind in ("raw","post")]
        index=dict(status="GEOMETRY_EVALUATED",scientific_verdict=None,region="P1",condition=cid,optimizer_updates=22000,
            new_condition_seal_sha256=retry.sha(evaluate.seal_path(evargs)),candidates=candidates)
        put(evargs.out/"geometry/P1/R22000_viewer_index.json",index)
        manifest=build("synthetic_available")
        check("available_final_candidate_binds_actual_selected_attempt",manifest["regions"][0]["candidates"][0]["provenance"]["execution_attempt"]["final_resource_retry"]["predecessor_attempt_id"]==f.previous.name)
        check("missing_other_budgets_remain_pending",sum(row["optimizer_updates"]==22000 for row in manifest["condition_availability"])==2)
        bad=copy.deepcopy(selection);bad["final_retry_evidence"][0]["final_resource_retry"]["max_attempts"]=2;put(selectionpath,bad)
        reject("builder_rejects_tampered_selection_provenance",lambda:build("must_not_publish"))
    if args.previous_core:
        previous=ast.parse(args.previous_core.read_text());current=ast.parse((args.source/"evaluate.py").read_text())
        for name in ("geometry_stage","renders_stage"):
            def function(tree):
                row=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
                return ast.dump(row,include_attributes=False)
            check("main_scoring_function_unchanged_"+name,function(previous)==function(current))
    if args.sealer:
        def validator(path):
            function=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=="validate_cgroup_failure")
            return ast.dump(function,include_attributes=False)
        check("consumer_cgroup_validator_identical_to_producer",validator(args.sealer)==validator(args.source/"final_retry.py"))
    actual=[]
    for region in args.actual_region:
        if not args.actual_task:raise ValueError("Actual region requires read-only actual task")
        selected=args.actual_task/retry.RETRIES[region]
        result=retry.bind_retry(args.actual_task,selected,region,retry.read(selected/"amendment.json"))
        check("actual_sealed_"+region+"_policy_and_predecessor_chain",result["region"]==region)
        actual.append(dict(region=region,amendment=retry.record(args.actual_task,selected/"amendment.json"),final_resource_retry=result))
    result=dict(status="PASS",scope="SYNTHETIC_CONSUMER_CONTRACTS_ONLY",scientific_verdict=None,
        actual_scene_evaluation_executed=False,gpu_used=False,checks=checks,check_count=len(checks),
        actual_readonly_amendment_bindings=actual,
        source_sha256={name:retry.sha(args.source/name) for name in ("final_retry.py","evaluate.py","build_viewer.py","summarize_resources.py","verify_final_retry_consumers.py")})
    with args.out.open("x") as stream:json.dump(result,stream,indent=2);stream.write("\n")
    print(json.dumps(dict(status="PASS",check_count=len(checks))))


if __name__=="__main__":main()
