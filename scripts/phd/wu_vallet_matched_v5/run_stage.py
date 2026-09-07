"""Host stdlib launcher: immutable sources and Docker-only scientific execution."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


IMAGE = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["update", "evaluation", "comparison", "viewer"])
    parser.add_argument("region", choices=["P1", "P2", "P3", "ALL"])
    parser.add_argument("--run-id")
    parser.add_argument("--config")
    parser.add_argument("--module")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    artifacts = (repo.parent / "JointBuildGS-artifacts").resolve()
    base = artifacts / "phase-payloads/phd/wu_vallet_matched_v5"
    modules = {"update": "update_regions", "evaluation": "evaluate_regions", "comparison": "compose_comparison", "viewer": "build_comparison_viewer"}
    configs = {"update": "regions_v5.json", "evaluation": "evaluation_v5.json", "comparison": "comparison_v5.json", "viewer": "viewer_v5.json"}
    run_id = args.run_id or f"PHD-WU-VALLET-{args.region if args.stage == 'update' else 'MATCHED'}-{args.stage.upper()}-v5"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        raise ValueError("Run ID must be a simple new directory name")
    if args.stage == "update" and args.region == "ALL":
        raise ValueError("Each update has a distinct immutable run")
    config = args.config or f"configs/phd/wu_vallet_matched_v5/{configs[args.stage]}"
    module = args.module or f"scripts.phd.wu_vallet_matched_v5.{modules[args.stage]}"
    cfg = json.loads((repo / config).read_text())
    run = base / run_id
    source = base / (run_id + "_source")
    run.mkdir(parents=True, exist_ok=False)
    source.mkdir(exist_ok=False)
    names = subprocess.check_output(["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z", "src", "scripts", "configs", "tests", "artifacts/manifests", "AGENTS.md", "requirements.txt"]).decode().split("\0")
    manifest = {}
    for name in sorted(set(names) - {""}):
        path = repo / name
        if not path.is_file():
            continue
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        manifest[name] = sha(dest)
    (source / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    mount_rows = []
    def bind(host, target, readonly=True):
        host = Path(host).resolve()
        if not host.exists():
            raise FileNotFoundError(host)
        mount_rows.append(dict(source=str(host), target=str(target), readonly=readonly))
    bind(source, "/workspace/JointBuildGS")
    if args.stage == "update":
        region = cfg["regions"][args.region]
        def resolve(container):
            return artifacts / Path(container).relative_to("/artifacts/JointBuildGS")
        for key in ("common_root", "acquisition_root", "trajectory_root"):
            bind(resolve(region[key]), region[key])
        common = resolve(region["common_root"])
        selected = json.loads((common / "selected_master.json").read_text())
        views = json.loads((common / "views.json").read_text())["views"]
        view = next(row for row in views if row["image_id"] == selected["image_id"])
        depth = view["maps"]["depth"]["path"]
        if sha(resolve(depth)) != view["maps"]["depth"]["sha256"]:
            raise ValueError("Selected depth changed after preparation")
        bind(resolve(depth), depth)
        # No artifact-root mount: neither raw UAS nor any frozen reference crop
        # exists inside this candidate-producing container.
    else:
        bind(artifacts, "/artifacts/JointBuildGS")
    bind(run, "/output", False)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    command = ["docker", "run", "--rm", "--name", "jbgs-" + run_id.lower(), "--network", "none", "--cpus", "4", "--memory", "18g", "--entrypoint", "python"]
    for mount in mount_rows:
        command += ["--mount", f"type=bind,src={mount['source']},dst={mount['target']}" + (",readonly" if mount["readonly"] else "")]
    command += ["--workdir", "/workspace/JointBuildGS"]
    env = dict(PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="1", MPLCONFIGDIR="/tmp/matplotlib", JBGS_SOURCE_GIT_HEAD=head, JBGS_CONTAINER_IMAGE_ID=IMAGE, JBGS_SOURCE_SNAPSHOT_MANIFEST=str(source / "SOURCE_MANIFEST.json"))
    for key, value in env.items():
        command += ["--env", key + "=" + value]
    command += [IMAGE, "-m", module, "--config", config, "--output", "/output/run"]
    if args.stage == "update":
        command += ["--region", args.region]
    receipt = dict(task_id=run_id, stage=args.stage, region=args.region, scientific_verdict=None, source_git_head=head, container_image=IMAGE, source_manifest_sha256=sha(source / "SOURCE_MANIFEST.json"), config_sha256=sha(source / config), mounts=mount_rows, command=command, raw_and_cropped_reference_mounted=args.stage != "update", started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (run / "LAUNCH.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (base / (run_id + ".console.log")).open("x") as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = proc.wait()
    receipt.update(exit_code=code, completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (run / "LAUNCH_COMPLETED.json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
