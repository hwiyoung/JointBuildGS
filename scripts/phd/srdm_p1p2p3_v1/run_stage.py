"""Host-stdlib operational launcher; all scientific work executes in Docker."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
ART = REPO.parent / "JointBuildGS-artifacts"
REL = "phase-payloads/phd/srdm_p1p2p3_v1/PHD-SRDM-P1P2P3-v1"
ROOT = ART / REL
CFG = "configs/phd/srdm_p1p2p3_v1/experiment_v1.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(8 << 20), b""):
            h.update(part)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")


def snapshot(dest):
    dirs = ["src/phd/srdm_p1p2p3_v1", "scripts/phd/srdm_p1p2p3_v1", "configs/phd/srdm_p1p2p3_v1"]
    paths = [p for d in dirs for p in (REPO / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += list((REPO / "tests/phd").glob("test_srdm_*.py"))
    paths += [REPO / name for name in ["AGENTS.md", "configs/phd/geogs_p1p2p3_v1/experiment_v1.json", "configs/phd/wu_vallet_matched_v5/evaluation_v5.json", "configs/phd/mvs_als_source_relation_v1/run_v1.json"]]
    dest.mkdir()
    hashes = {}
    for p in sorted(set(paths)):
        rel = p.relative_to(REPO)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
        hashes[str(rel)] = sha(out)
    save(dest / "SOURCE_MANIFEST.json", {"files": hashes, "git_head": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["init", "prepare", "test", "run", "seal", "evaluate", "paired", "report", "verify"])
    ap.add_argument("--region", choices=["P1", "P2", "P3"])
    args = ap.parse_args()
    cfg = json.loads((REPO / CFG).read_text())
    if args.stage == "init":
        ROOT.mkdir(parents=True, exist_ok=False)
        for d in ["preservation", "contracts", "attempts", "inputs", "run", "sources", "scratch"]:
            (ROOT / d).mkdir()
        state = subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain=v1", "--untracked-files=normal"], text=True)
        (ROOT / "preservation/git_status_before.txt").write_text(state)
        services = subprocess.check_output(["docker", "ps", "--format", "{{.ID}} {{.Names}} {{.Image}}"], text=True)
        (ROOT / "preservation/services_before.txt").write_text(services)
        fixed = ["AGENTS.md", "CLAUDE.md"] + [str(p.relative_to(REPO)) for p in (REPO / "docs/research").glob("0*.md")]
        save(ROOT / "preservation/canonical_hashes_before.json", {p: sha(REPO / p) for p in fixed})
        save(ROOT / "contracts/initial_config.json", cfg)
        print(json.dumps({"task_root": str(ROOT), "scientific_verdict": None}))
        return
    if not ROOT.is_dir():
        raise RuntimeError("Initialize a new task first")
    lock = (ROOT / "runtime.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.stage in ["prepare", "run"] and not args.region:
        ap.error("--region is required")
    available = int(next(x for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")).split()[1]) * 1024
    resources = dict(cfg["resource"])
    if args.stage == "run":
        resources.update(cfg.get("region_resources", {}).get(args.region, {}))
    if available < resources["minimum_host_available_gib"] * (1 << 30):
        raise RuntimeError(f"Insufficient host headroom: {available} bytes; existing work untouched")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    name = f"{args.stage}-{args.region or 'all'}-{stamp}"
    attempt = ROOT / "attempts" / name
    attempt.mkdir()
    source = ROOT / "sources" / name
    snapshot(source)
    geogs = json.loads((source / cfg["source_config"]).read_text())
    mounts = []
    def allow(rel):
        local = ART / rel
        if not local.exists():
            raise FileNotFoundError(local)
        mounts.append((str(local), "/artifacts/JointBuildGS/" + rel))
    if args.stage == "prepare":
        spec = geogs["regions"][args.region]
        allow(spec["acquisition_npz"])
        allow(spec["views_json"])
        allow(geogs["camera_root"] + "/images")
        allow(geogs["camera_root"] + "/sparse")
        allow(cfg["geogs_task_relative"] + "/inputs/" + args.region)
    if args.stage in ["evaluate", "report"]:
        if not (ROOT / "run/CANDIDATE_SEAL.json").is_file():
            raise RuntimeError("Candidates must be sealed before reference mount")
        evaluation = json.loads((source / "configs/phd/wu_vallet_matched_v5/evaluation_v5.json").read_text())
        for spec in evaluation["regions"]:
            ref = spec["frozen_reference_npz"]
            allow(ref.removeprefix("/artifacts/JointBuildGS/"))
    command = ["docker", "run", "--rm", "--name", "jbgs-srdm-" + args.stage + "-" + (args.region or "all") + "-" + stamp.replace(".", "-"),
        "--network", "none", "--cpus", str(resources["cpus"]), "--memory", str(resources["memory_gib"]) + "g", "--memory-swap", str(resources["memory_gib"]) + "g",
        "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", "python", "--workdir", "/workspace",
        "--mount", f"type=bind,src={source},dst=/workspace,readonly", "--mount", f"type=bind,src={ROOT},dst=/task",
        "--env", "PYTHONPATH=/workspace", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "OPENBLAS_NUM_THREADS=1", "--env", "OMP_NUM_THREADS=4", "--env", "MPLCONFIGDIR=/task/scratch/matplotlib"]
    for host, container in sorted(set(mounts)):
        command += ["--mount", f"type=bind,src={host},dst={container},readonly"]
    command += [cfg["image"]]
    base = "scripts.phd.srdm_p1p2p3_v1."
    if args.stage == "prepare":
        command += ["-m", base + "prepare_inputs", "--config", CFG, "--artifact-root", "/artifacts/JointBuildGS", "--output-root", "/task/inputs", "--region", args.region]
    elif args.stage == "test":
        command += ["-m", "unittest", "discover", "-s", "tests/phd", "-p", "test_srdm_*.py", "-v"]
    elif args.stage in ["run", "seal"]:
        command += ["-m", base + "run_regions", args.stage, "--config", CFG, "--task-root", "/task"]
        if args.region:
            command += ["--region", args.region]
    elif args.stage == "evaluate":
        command += ["-m", base + "evaluate", "--run-root", "/task/run", "--config", "configs/phd/srdm_p1p2p3_v1/evaluation_v1.json", "--seal", "/task/run/CANDIDATE_SEAL.json", "--output", "/task/evaluation"]
    elif args.stage == "report":
        command += ["-m", base + "build_report", "--run-root", "/task/run", "--evaluation-root", "/task/evaluation", "--paired-root", "/task/paired", "--output", "/task/report"]
    elif args.stage == "paired":
        command += ["-m", base + "analyze_paired", "--run-root", "/task/run", "--evaluation-root", "/task/evaluation", "--output", "/task/paired"]
    elif args.stage == "verify":
        command += ["-m", base + "verify_outputs", "--task-root", "/task"]
    save(attempt / "launch.json", {"command": command, "source_manifest": str(source / "SOURCE_MANIFEST.json"), "input_mounts": mounts, "reference_mounted": args.stage in ["evaluate", "report"], "host_available_bytes": available, "scientific_verdict": None})
    start = dt.datetime.now(dt.timezone.utc)
    print(json.dumps({"stage": args.stage, "region": args.region, "attempt": str(attempt)}), flush=True)
    with (attempt / "console.log").open("x") as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        code = process.wait()
    end = dt.datetime.now(dt.timezone.utc)
    save(attempt / "receipt.json", {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "wall_seconds": (end-start).total_seconds(), "exit_code": code, "scientific_verdict": None})
    sys.exit(code)


if __name__ == "__main__":
    main()
