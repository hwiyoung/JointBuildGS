"""PHD-MAIN-PHOTOFIG-v1 receipt: steps and seconds (logs/queue.log), waits (logs/waits.log), config lock, git commit, image id.
Host python (json only).   python3 -I receipt.py <commit>   scientific_verdict: null"""
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PF = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"


def main(commit):
    steps = []
    for l in (PF / "logs/queue.log").read_text().splitlines():
        p = l.split()
        if len(p) >= 5:
            steps.append(dict(when=f"{p[0]} {p[1]}", tag=p[2], rc=p[3], seconds=int(p[4].rstrip("s"))))
    waits = []
    for l in (PF / "logs/waits.log").read_text().splitlines():
        p = l.split()
        waits.append(dict(when=f"{p[0]} {p[1]}", tag=p[2], waited_s=int(p[3].split("=")[1].rstrip("s")), reason=p[4].split("=", 1)[1]))
    img = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", "jointbuildgs:dev"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id="PHD-MAIN-PHOTOFIG-v1", commit=commit, image="jointbuildgs:dev", image_id=img, config_lock=json.loads((PF / "config_lock.json").read_text()),
               config_lock_more=(json.loads((PF / "config_lock_more.json").read_text()) if (PF / "config_lock_more.json").exists() else None),
               steps=steps, seconds_total_ok=sum(s["seconds"] for s in steps if s["rc"] == "rc=0"), waits=waits, waited_total_s=sum(w["waited_s"] for w in waits),
               gpu_used=False, training=False, made=time.strftime("%Y-%m-%d %H:%M:%S KST"), scientific_verdict=None)
    (PF / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print(json.dumps({k: rec[k] for k in ("commit", "seconds_total_ok", "waited_total_s")}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
