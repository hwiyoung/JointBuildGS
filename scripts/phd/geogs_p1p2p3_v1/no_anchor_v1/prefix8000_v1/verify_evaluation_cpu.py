"""Small synthetic provenance/seal/summary/viewer checks; never score a real scene."""
import argparse
import ast
import copy
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--previous-core",type=Path,required=True)
    p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--evaluation-lib",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();checks=[]
    sys.path.insert(0,str(a.evaluation_lib));sys.path.insert(0,str(a.evaluation_lib.parent))
    ev=module("prefix_test_evaluate",a.source/"evaluate.py")
    builder=module("prefix_test_builder",a.source/"build_viewer.py")
    core_path=a.source.parent/"evaluate.py";core=module("prefix_test_core",core_path)
    from PIL import Image
    import numpy as np
    from parse_extraction import parse_extraction_log
    def check(name,value):
        checks.append(dict(name=name,pass_=bool(value)))
        if not value:raise AssertionError(name)
    def reject(name,fn):
        try:fn()
        except (ValueError,FileNotFoundError,KeyError):check(name,True);return
        check(name,False)
    def put(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def blob(path,value=b"synthetic fixture"):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    def normalized_function(path,name):
        function=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name==name)
        function.args.kwonlyargs=[];function.args.kw_defaults=[]
        class Normalize(ast.NodeTransformer):
            def visit_Name(self,node):
                return ast.copy_location(ast.Constant("sfm_no_anchor_final512"),node) if node.id=="comparison_family" else node
        return ast.dump(Normalize().visit(function),include_attributes=False)
    for name in ("geometry_stage","renders_stage"):
        check("unchanged_main_scoring_body_"+name,normalized_function(core_path,name)==normalized_function(a.previous_core,name))
    with tempfile.TemporaryDirectory() as temporary:
        task=Path(temporary)/"task";task.mkdir();put(task/ev.POLICY_PATH,json.loads(a.policy.read_text()))
        # Preserve the exact policy bytes, including formatting.
        shutil.copyfile(a.policy,task/ev.POLICY_PATH)
        contract=core.read_json(task/ev.POLICY_PATH)
        output=task/contract["evaluation_root"];output.mkdir(parents=True)
        selected=contract["selected_attempts"]
        parents={}
        for rid,attempt in selected.items():
            run=task/attempt/"runs"/rid/core.RUN_CONDITION
            parent=dict(status="FAIL",phase="train",iteration=None,region=rid,condition_id=core.RUN_CONDITION,
                native_exit_code=1,validated_exit_code=1,started_unix=1.,finished_unix=2.,scientific_verdict=None,
                source_sha256={"train.py":"synthetic_source_sha"},runtime_image_id="synthetic_runtime")
            put(run/"receipt.json",parent);parents[rid]=(run,parent)
        rid="P1";run,parent=parents[rid];experiment=task/selected[rid]
        args=SimpleNamespace(task=task,experiment=experiment,out=output,region=rid,iteration=8000,public_root=ev.PUBLIC_ROOT,
            core_evaluator=core_path,evaluation_lib=a.evaluation_lib)
        check("isolated_policy_output_accepted",ev.policy(args)["prefix_iteration"]==8000)
        bad=copy.copy(args);bad.out=task;reject("main_or_foreign_output_root_rejected",lambda:ev.policy(bad))
        reject("no_22k_selected_as_prefix",lambda:ev.condition(22000))
        check("prefix_identity_has_no_duplicate_geometry_iteration_keyword",dict(**ev.binding(args),iteration=8000)["iteration"]==8000)
        rec=lambda path:core.source_file(task,path)
        activation_path=task/"completed_prefix8000_v1/activation/receipt.json"
        activation=dict(status="PREFIX_DIAGNOSTIC_ACTIVATED",all_selected_producer_jobs_closed=True,
            selected_attempts=selected,scientific_verdict=None,quality_or_reference_selection=False,
            failure_evidence=[dict(region=r,receipt=rec(rn/"receipt.json")) for r,(rn,_) in parents.items()],
            files=[rec(rn/"receipt.json") for rn,_ in parents.values()])
        put(activation_path,activation)
        cfg=dict(regions={r:dict(expected_test=1,domain=[0,0,0,1,1,1]) for r in selected},seed=0)
        put(task/"contracts/execution_v1.json",cfg)
        cfg_snapshot=run/"config_snapshot.json";put(cfg_snapshot,{"synthetic":"same frozen controls"})
        original=task/"no_anchor_sfm_v1/runs/P1"/core.RUN_CONDITION/"receipt.json";put(original,parent)
        amendment=dict(scientific_verdict=None,arithmetic_or_scientific_controls_changed=False,
            original_config_sha256=core.sha(cfg_snapshot),memory_placement_changes=["same placement"],original_failed_run_receipt=rec(original))
        put(experiment/"amendment.json",amendment)
        parent.update(memory_recovery_amendment_path=str((experiment/"amendment.json").relative_to(task)),
            memory_recovery_amendment_sha256=core.sha(experiment/"amendment.json"))
        put(run/"receipt.json",parent)
        activation["files"]=[rec(rn/"receipt.json") for rn,_ in parents.values()]
        activation["failure_evidence"]=[dict(region=r,receipt=rec(rn/"receipt.json")) for r,(rn,_) in parents.items()]
        put(activation_path,activation)
        snapshot=run/"model/jbgs_complete/iteration_8000"
        blob(snapshot/"point_cloud.ply",b"synthetic valid PLY identity supplied by validator fixture")
        blob(snapshot/"checkpoint.pth",b"synthetic checkpoint identity")
        capture=dict(schema="JBGS_GEOGS_COMPLETE_STATE_v1",iteration=8000,after_protection_registration=True,
            scientific_verdict=None,gaussians=1,ply_sha256=core.sha(snapshot/"point_cloud.ply"),checkpoint_sha256=core.sha(snapshot/"checkpoint.pth"))
        put(snapshot/"receipt.json",capture)
        initialization=dict(status="PASS_PREOPTIMIZATION_PROTECTION",protected_gaussians=1,protected_fraction=1.)
        put(run/"model/jbgs_no_anchor/initialization.json",initialization)
        put(run/"model/jbgs_no_anchor/first_step.json",dict(status="PASS_FIRST_STEP_DIRECT_REFINEMENT",anchor_iterations_executed=0))
        blob(run/"model/cfg_args",b"synthetic renderer configuration")
        scene=task/"inputs/P1/scene";photo=scene/"images/photo.png";photo.parent.mkdir(parents=True)
        rgb=np.full((6,8,3),120,dtype=np.uint8);Image.fromarray(rgb).save(photo)
        view=dict(name="photo.png",sha256=core.sha(photo),width=8,height=6,image_id=1,camera_id=1)
        put(scene/"split_manifest_da3_v2.json",dict(evaluation=[view],train=[]))
        put(scene/"jbgs_calibration.json",{});put(scene/"scene_reference_frame.json",{})
        put(task/"inputs/P1/input_manifest.json",{})
        sfm_root=experiment/"inputs/P1";put(sfm_root/"initialization_manifest.json",dict(original_input_manifest=rec(task/"inputs/P1/input_manifest.json")))
        records=dict(parent_training_receipt=rec(run/"receipt.json"),snapshot_ply=rec(snapshot/"point_cloud.ply"),
            snapshot_checkpoint=rec(snapshot/"checkpoint.pth"),snapshot_capture_receipt=rec(snapshot/"receipt.json"),activation_receipt=rec(activation_path))
        proof=dict(schema="GEOGS_SFM_PREFIX_VALIDATION_v1",status="PREFIX_8000_VALIDATED",validation_pass=True,
            analysis_role=ev.ROLE,iteration=8000,actual_optimizer_updates=8000,planned_total_updates=30000,
            scientific_verdict=None,region="P1",selected_experiment=selected["P1"],parent_training_status="FAIL",
            policy_sha256=ev.POLICY_SHA,reference_accessed=False,establishes_22000_or_30000_completion=False,files=list(records.values()),**records)
        root=task/contract["producer_root"]/"P1";proof_path=root/"validation/receipt.json";put(proof_path,proof)
        check("closed_parent_FAIL_can_validate_its_fixed_prefix",ev.validate_proof(args,rec)[-1]["status"]=="FAIL")
        original_proof=copy.deepcopy(proof);proof["actual_optimizer_updates"]=22000;put(proof_path,proof)
        reject("wrong_prefix_budget_rejected",lambda:ev.validate_proof(args,rec));put(proof_path,original_proof)
        p3path=parents["P3"][0]/"receipt.json";saved=p3path.read_bytes();p3path.unlink()
        reject("any_unclosed_selected_parent_blocks_activation",lambda:ev.validate_proof(args,rec));p3path.write_bytes(saved)
        export=root/"export";model=export/"model"
        blob(model/"point_cloud/iteration_8000/point_cloud.ply",(snapshot/"point_cloud.ply").read_bytes())
        blob(model/"cfg_args",(run/"model/cfg_args").read_bytes());blob(export/"config_snapshot.json",cfg_snapshot.read_bytes())
        for name in ("fuse.ply","fuse_post.ply"):blob(model/"train/ours_8000"/name)
        for category in ("renders","gt"):
            path=model/"test/ours_8000"/category/"00000.png";path.parent.mkdir(parents=True);Image.fromarray(rgb).save(path)
        blob(export/"native.log",b"The estimated bounding radius is 1.00\nRunning tsdf volume integration ...\nvoxel_size: 0.00390625\nsdf_trunc: 0.01953125\ndepth_truc: 2.0\npost processing the mesh to have 50 clusterscluster_to_kep\n")
        exported_paths=[model/"train/ours_8000"/n for n in ("fuse.ply","fuse_post.ply")]+[model/"test/ours_8000"/s/"00000.png" for s in ("renders","gt")]
        producer=dict(parent,status="PASS",phase="export",iteration=8000,native_exit_code=0,validated_exit_code=0,
            reference_accessed=False,config_sha256=core.sha(cfg_snapshot),sfm_manifest_sha256=core.sha(sfm_root/"initialization_manifest.json"),
            original_input_manifest_sha256=core.sha(task/"inputs/P1/input_manifest.json"),prefix_validation_receipt=rec(proof_path),
            command=["render.py","-s","/sfm_input/scene","--iteration","8000","--mesh_res","512","--num_cluster","50"],
            validation=[dict(realized_extraction=parse_extraction_log(export/"native.log",512,50))],
            outputs=[dict(path=str(p.relative_to(export)),bytes=p.stat().st_size,sha256=core.sha(p)) for p in exported_paths])
        put(export/"receipt.json",producer);put(export/"invocation.json",producer)
        ev.seal_stage(args);seal,digest=ev.load_seal(args)
        check("prefix_seal_preserves_parent_FAIL_and_8k_available",seal["parent_training_status"]=="FAIL" and seal["optimizer_updates"]==8000 and not seal["full_experiment_completion_inferred"])
        check("seal_renderer_PLY_record_does_not_become_last_PNG",seal["rendered_ply"]["path"].endswith("point_cloud.ply"))
        bad=copy.copy(args);bad.core_evaluator=a.previous_core;reject("changed_scoring_core_rejected",lambda:ev.load_seal(bad))
        before=(snapshot/"point_cloud.ply").read_bytes();(snapshot/"point_cloud.ply").write_bytes(b"changed")
        reject("sealed_prefix_PLY_mutation_rejected",lambda:ev.load_seal(args));(snapshot/"point_cloud.ply").write_bytes(before)
        oldgeom=[]
        for stage in ("anchor_512","mesh_512"):
            for kind in ("raw","post"):oldgeom.append(dict(region="P1",candidate="D005_Pnative."+stage+"."+kind,mesh_res=512))
        (task/"evaluation/summary").mkdir(parents=True,exist_ok=True)
        core.write_csv(task/"evaluation/summary/geometry_anchor_refinement_512.csv",oldgeom)
        new=[dict(candidate=ev.CONDITION+".mesh_512."+kind,mesh_res=512,new_condition_seal_sha256=digest) for kind in ("raw","post")]
        (output/"geometry/P1").mkdir(parents=True);core.write_csv(output/"geometry/P1/R8000_metrics.csv",new)
        oldrgb=[dict(region="P1",condition="D005_Pnative",stage=s,domain=d) for s in ("anchor_512","final") for d in ("full_frame","fixed_prism_projected_bbox")]
        core.write_csv(task/"evaluation/summary/render_summary.csv",oldrgb)
        render_root=output/"renders/P1"/ev.CONDITION/"refinement_only"
        rows=[dict(status="ASSESSED",pixel_count=48,domain=d,psnr_native_db=20.,psnr_positive_infinity=False,ssim_native=.5,lpips_vgg_native_01=.4,lpips_vgg_signed_11=.4,lpips_status="FINITE",montage=None) for d in ("full_frame","fixed_prism_projected_bbox")]
        put(render_root/"receipt.json",dict(status="PASS_RENDER_QUALITY_EVALUATION",scientific_verdict=None,condition=ev.CONDITION,region="P1",stage="refinement_only",sealed_render_manifest_sha256=digest,rows=rows))
        ev.summary_stage(args)
        summary=list(csv.DictReader((output/"summary/P1/R8000/render_comparison.csv").open()))
        check("Anchor8000_RGB_primary_and_final30000_context_separate",all(r["comparison_role"]==("CONTEXT_DIFFERENT_30000_BUDGET" if r["stage"]=="final" else "PRIMARY_EQUAL_UPDATES") for r in summary))
        source=task/"evaluation/viewer/manifest_v2.json"
        put(source,dict(scientific_verdict=None,regions=[dict(id=r,conditions=[dict(id="D005_Pnative")]+[dict(id="old"+str(i)) for i in range(5)],candidates=[],panel_candidates={},renders=[],sections=[]) for r in selected]))
        builder.SOURCE_SHA=core.sha(source)  # Fixture-only replacement; production constant is untouched.
        index=dict(status="GEOMETRY_EVALUATED",analysis_role=ev.ROLE,condition=ev.CONDITION,region="P1",optimizer_updates=8000,new_condition_seal_sha256=digest,
            candidates=[dict(id=ev.CONDITION+".mesh_512."+k,status="available",section_url="/fixture.png",distance_url="/fixture.png") for k in ("raw","post")])
        put(output/"geometry/P1/R8000_viewer_index.json",index)
        put(task/contract["producer_root"]/"P2/validation/receipt.json",dict(status="FAIL_PREFIX_VALIDATION",region="P2",scientific_verdict=None))
        saved_argv=sys.argv
        try:
            sys.argv=[str(a.source/"build_viewer.py"),"--task",str(task),"--out",str(output),"--publish-id","synthetic_fixture","--core-evaluator",str(core_path),"--core-builder",str(a.source.parent/"build_viewer.py")]
            builder.main()
        finally:sys.argv=saved_argv
        manifest=core.read_json(output/"profiles/synthetic_fixture/manifest.json")
        available=[r for r in manifest["condition_availability"] if r["optimizer_updates"]==8000]
        check("viewer_has_six_prefix_states",len(manifest["condition_availability"])==6)
        check("viewer_parent_FAIL_does_not_mask_valid_prefix",len(available)==2 and all(r["parent_training_status"]=="FAIL" for r in available))
        check("validator_failure_is_not_shown_as_pending",all(r["status"]=="failed" for r in manifest["condition_availability"] if r["region"]=="P2"))
        check("unproduced_other_regions_have_no_fallback",all(c["data"] is None and c["mesh_data"] is None for r in manifest["regions"][1:] for c in r["candidates"]))
        check("viewer_defaults_to_fixed_prefix_and_retains_main_context",all(r["default_condition"]==ev.CONDITION and "final30000" in r["notes"][0] for r in manifest["regions"]))
    result=dict(status="PASS_SYNTHETIC_PREFIX_EVALUATION_VALIDATION",scientific_verdict=None,checks=checks,check_count=len(checks),created_unix=time.time(),
        scope="Synthetic temporary files only; no scene training/export/scoring/browser execution",source_sha256={p.name:core.sha(p) for p in a.source.iterdir() if p.is_file()})
    a.out.mkdir(parents=True,exist_ok=True);core.write_json(a.out/"receipt.json",result)
    print(json.dumps(dict(status=result["status"],checks=len(checks))))


if __name__=="__main__":main()
