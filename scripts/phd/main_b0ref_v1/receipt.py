"""PHD-MAIN-B0REF-v1 receipt: steps and seconds (logs/queue.log), waits for memory / the fix-test post steps (logs/waits.log), config
lock, downloaded files with their Zenodo md5, git commit, image id. Host python (no project dependency).
  python3 -I receipt.py <commit> -> PH/main_b0ref_v1/PHD-MAIN-B0REF-v1/receipt_task.json   scientific_verdict: null"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
B0 = REPO.parent / "JointBuildGS-artifacts/phase-payloads/phd/main_b0ref_v1/PHD-MAIN-B0REF-v1"
ZEN = {  # Zenodo API checksums (records 15282970 = v1.2.0, 14899378 = v1.1.0), read 2026-10-20
    "dl/zenodo_v120_manual/TUM_Downtown_ULS_20241217_manual.laz": "37ce114fb348fb28066cc967cde9771d",
    "dl/zenodo_v120_fillparts/TUM_Downtown_ULS_20241217_manual_5mm_fillparts.laz": "ed46079bee78f4dc939dbfa5dc2c61e8",
    "dl/zenodo_v110_fillparts/TUM_Downtown_ULS_20241217_manual_5mm_fillparts.laz": "afd06a9d74c68cf792b71ca9be57d4fb",
    "dl/zenodo_docu_v120/TUM_Downtown_ULS_Photogrammetry_20241217_docu.pdf": "3427e70196d1db6a126acb6f041da04a",
    "dl/zenodo_docu_v110/TUM_Downtown_ULS_Photogrammetry_20241217_docu.pdf": "3427e70196d1db6a126acb6f041da04a",
}


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main(commit):
    steps = []
    for l in (B0 / "logs/queue.log").read_text().splitlines():
        p = l.split()
        if len(p) >= 5:
            steps.append(dict(when=f"{p[0]} {p[1]}", tag=p[2], rc=p[3], seconds=int(p[4].rstrip("s"))))
    waits = []
    wp = B0 / "logs/waits.log"
    if wp.exists():
        for l in wp.read_text().splitlines():
            p = l.split()
            waits.append(dict(when=f"{p[0]} {p[1]}", tag=p[2], waited_s=int(p[3].split("=")[1].rstrip("s")), reason=p[4].split("=", 1)[1]))
    dl = {}
    for rel, z in ZEN.items():
        f = B0 / rel
        if f.exists():
            m = md5(f)
            dl[rel] = dict(bytes=f.stat().st_size, md5=m, zenodo_md5=z, equal=m == z)
    img = subprocess.run(["docker", "inspect", "--format", "{{.Id}}", "jointbuildgs:dev"], capture_output=True, text=True).stdout.strip()
    rec = dict(task_id="PHD-MAIN-B0REF-v1", commit=commit, image="jointbuildgs:dev", image_id=img,
               config_lock=json.loads((B0 / "config_lock.json").read_text()), steps=steps,
               seconds_total_ok=sum(s["seconds"] for s in steps if s["rc"] == "rc=0"), waits=waits,
               waited_total_s=sum(w["waited_s"] for w in waits), downloads=dl, gpu_used=False, training=False,
               made=time.strftime("%Y-%m-%d %H:%M:%S KST"), scientific_verdict=None)
    (B0 / "receipt_task.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print(json.dumps({k: rec[k] for k in ("commit", "seconds_total_ok", "waited_total_s")}), json.dumps({k: v["equal"] for k, v in dl.items()}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
