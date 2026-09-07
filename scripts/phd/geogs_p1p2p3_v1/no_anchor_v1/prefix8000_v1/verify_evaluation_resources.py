"""Exercise the resource wrapper with a fake Docker command inside Docker only."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--wrapper",type=Path,required=True)
    parser.add_argument("--policy",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args();checks=[]
    if not Path("/.dockerenv").is_file():raise RuntimeError("Docker only")
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    with tempfile.TemporaryDirectory() as temporary:
        base=Path(temporary);repo=base/"repo"
        code=repo/"scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/prefix8000_v1";code.mkdir(parents=True)
        wrapper=code/"evaluate.sh";shutil.copyfile(args.wrapper,wrapper)
        (code/"evaluate.py").write_text("# Synthetic snapshot only\n")
        (code.parent/"evaluate.py").write_text("# Synthetic core only\n")
        artifacts=base/"JointBuildGS-artifacts"
        task=artifacts/"phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
        (task/"contracts").mkdir(parents=True);shutil.copyfile(args.policy,task/"contracts/sfm_prefix8000_diagnostic_v1.json")
        for region in ("P1","P2","P3"):
            for stage in ("validation","export"):
                path=task/"completed_prefix8000_v1"/region/stage/"receipt.json"
                path.parent.mkdir(parents=True);path.write_text('{}')
        binary=base/"bin";binary.mkdir()
        docker=binary/"docker"
        docker.write_text('#!/usr/bin/env python\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["PREFIX_EVAL_FIXTURE_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\nprint("Synthetic Docker command only")\nsys.exit(int(os.environ.get("PREFIX_EVAL_FIXTURE_EXIT","0")))\n')
        docker.chmod(0o755)
        # The host wrapper uses rg for its final file list; the science image
        # lacks that host utility. Supply only this exact listing operation.
        rg=binary/"rg"
        rg.write_text('#!/usr/bin/env python\nimport os,sys\nassert sys.argv[1:]==["--files","-0","-g","!SHA256SUMS"]\nfor root,dirs,files in os.walk("."):\n for name in files:\n  if name!="SHA256SUMS":sys.stdout.buffer.write(os.path.relpath(os.path.join(root,name)).encode()+b"\\0")\n')
        rg.chmod(0o755)
        env=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ["PATH"])
        output=task/"evaluation/no_anchor_sfm_prefix8000_v1/execution"
        for stage,cpus,memory,shm in (("seal",2,3,"256m"),("geometry",8,32,"4g"),("renders",4,8,"256m"),("summary",2,3,"256m")):
            capture=base/(stage+".json");current=dict(env,PREFIX_EVAL_FIXTURE_CAPTURE=str(capture))
            if stage=="geometry":
                lockpath=task/"no_anchor_sfm_v1/locks/heavy_cpu.lock";lockpath.parent.mkdir(parents=True)
                with lockpath.open("a") as stream:
                    fcntl.flock(stream,fcntl.LOCK_EX)
                    process=subprocess.Popen(["bash",str(wrapper),"P1",stage],env=current,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                    status=output/"P1/R8000/geometry/status.txt"
                    for _ in range(100):
                        if status.is_file() and status.read_text().strip()=="WAITING_FOR_SHARED_HEAVY_CPU_LOCK":break
                        time.sleep(.02)
                    check("geometry_waits_on_exact_shared_lock_before_docker",process.poll() is None and not capture.exists() and status.is_file())
                    time.sleep(.1);fcntl.flock(stream,fcntl.LOCK_UN)
                    stdout,stderr=process.communicate(timeout=10);exit_code=process.returncode
            else:
                result=subprocess.run(["bash",str(wrapper),"P1",stage],env=current,capture_output=True,text=True,timeout=10)
                exit_code,stdout,stderr=result.returncode,result.stdout,result.stderr
            if exit_code:print(json.dumps(dict(stage=stage,exit_code=exit_code,stdout=stdout,stderr=stderr)),flush=True)
            check(stage+"_wrapper_succeeds_with_synthetic_command",exit_code==0)
            command=json.loads(capture.read_text());root=output/"P1/R8000"/stage
            plan=json.loads((root/"resource_plan.json").read_text());receipt=json.loads((root/"resource_receipt.json").read_text())
            def option(key):return command[command.index(key)+1]
            check(stage+"_exact_resource_limits",option("--cpus")==str(cpus) and option("--memory")==str(memory)+"g" and option("--memory-swap")==str(memory)+"g" and option("--shm-size")==shm)
            check(stage+"_no_gpu_and_cpu_scoring", "--gpus" not in command and "NVIDIA_VISIBLE_DEVICES=void" in command and option("--device")=="cpu")
            check(stage+"_plan_matches_command",plan["cpus"]==cpus and plan["memory_limit_bytes"]==memory<<30 and plan["metric_device"]=="cpu" and plan["shared_heavy_cpu_lock"]==(stage=="geometry"))
            check(stage+"_receipt_preserves_scope_and_time",receipt["evaluator_exit_code"]==0 and receipt["docker_phase_wall_seconds"]>=0 and receipt["docker_finished_unix"]>=receipt["docker_started_unix"] and receipt["direct_comparison_to_gpu_scoring_time_allowed"] is False and receipt["quality_status_inferred_from_resource_receipt"] is False)
            mounts=[command[i+1] for i,value in enumerate(command) if value=="--mount"]
            check(stage+"_reference_only_for_geometry",any("dst=/reference/" in mount for mount in mounts)==(stage=="geometry"))
            check(stage+"_frozen_policy_snapshot_unchanged",(root/"policy_snapshot.json").read_bytes()==args.policy.read_bytes())
            if stage=="geometry":check("lock_wait_record_is_separate_from_docker_work",receipt["shared_lock_wait_seconds"]>=.09)
        capture=base/"failure.json"
        result=subprocess.run(["bash",str(wrapper),"P2","renders"],env=dict(env,PREFIX_EVAL_FIXTURE_CAPTURE=str(capture),PREFIX_EVAL_FIXTURE_EXIT="17"),capture_output=True,text=True,timeout=10)
        receipt=json.loads((output/"P2/R8000/renders/resource_receipt.json").read_text())
        check("nonzero_evaluator_exit_retained",result.returncode==17 and receipt["evaluator_exit_code"]==17)
        result=subprocess.run(["bash",str(wrapper),"P1","unknown"],env=env,capture_output=True,text=True,timeout=10)
        check("unknown_stage_rejected_before_execution",result.returncode==2)
    result=dict(status="PASS_SYNTHETIC_RESOURCE_WRAPPER",scientific_verdict=None,checks=checks,check_count=len(checks),
        wrapper_sha256=hashlib.sha256(args.wrapper.read_bytes()).hexdigest(),policy_sha256=hashlib.sha256(args.policy.read_bytes()).hexdigest(),
        actual_evaluation_executed=False,actual_exports_read=False,gpu_used=False,
        test_scope="Temporary fixture stubs Docker and rg's exact file-list operation; real bash/flock exercise resource choices and mutex. Outer test uses Docker CPU2/RAM3GiB.")
    with args.out.open("x") as stream:json.dump(result,stream,indent=2);stream.write("\n")
    print(json.dumps(dict(status=result["status"],check_count=len(checks))))


if __name__=="__main__":main()
