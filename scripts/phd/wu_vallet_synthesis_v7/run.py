"""Host stdlib launcher for an immutable Docker analysis of completed updates."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(run_id):
    repo = Path(__file__).resolve().parents[3]
    artifacts = repo.parent / "JointBuildGS-artifacts"
    base = artifacts / "phase-payloads/phd/wu_vallet_synthesis_v7"
    run = base / run_id
    source = base / (run_id + "_source")
    run.mkdir(parents=True, exist_ok=False)
    source.mkdir(exist_ok=False)
    names = ["scripts/phd/wu_vallet_synthesis_v7/analyze.py", "scripts/phd/wu_vallet_synthesis_v7/run.py", "configs/phd/wu_vallet_synthesis_v7/analysis_v7.json", "AGENTS.md"]
    hashes = {}
    for name in names:
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, dest)
        hashes[name] = sha(dest)
    (source / "SOURCE_MANIFEST.json").write_text(json.dumps(hashes, indent=2) + "\n")
    # Exact established image, no dependency installation.
    image = "sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    command = ["docker", "run", "--rm", "--network", "none", "--cpus", "2", "--memory", "8g", "--entrypoint", "python",
        "--mount", f"type=bind,src={source},dst=/workspace/JointBuildGS,readonly",
        "--mount", f"type=bind,src={artifacts},dst=/artifacts/JointBuildGS,readonly",
        "--mount", f"type=bind,src={run},dst=/output",
        "--workdir", "/workspace/JointBuildGS", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "MPLCONFIGDIR=/tmp/mpl", "--env", "OPENBLAS_NUM_THREADS=1",
        "--env", "JBGS_SOURCE_GIT_HEAD=" + head, "--env", "JBGS_CONTAINER_IMAGE_ID=" + image,
        image, "scripts/phd/wu_vallet_synthesis_v7/analyze.py", "--config", names[2], "--output", "/output/run"]
    invocation = dict(command=command, scientific_verdict=None, container_image=image, source_git_head=head,
        source_hashes=hashes, source_manifest_sha256=sha(source / "SOURCE_MANIFEST.json"), started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (run / "invocation.json").write_text(json.dumps(invocation, indent=2) + "\n")
    with (run / "console.log").open("x") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    invocation.update(exit_code=result.returncode, completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), console_sha256=sha(run / "console.log"))
    (run / "completion.json").write_text(json.dumps(invocation, indent=2) + "\n")
    print((run / "console.log").read_text())
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="PHD-WU-VALLET-SYNTHESIS-v7-r2")
    main(parser.parse_args().run_id)
