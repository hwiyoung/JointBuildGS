"""Preserve prior stage config revisions only after exact receipt-hash matching."""
import argparse
import hashlib
import json
from pathlib import Path

from .prepare import write_json,sha


def run(config,task):
    if not Path("/.dockerenv").exists():raise RuntimeError("Docker required")
    current=config.read_bytes()
    before_initialization=b"".join(line for line in current.splitlines(keepends=True) if not line.startswith(b'  "initialization":'))
    candidates={hashlib.sha256(value).hexdigest():(value,name) for value,name in
                [(current,"copied_current_exact_bytes"),(before_initialization,"reconstructed_by_removing_initialization_property_line_hash_verified")]}
    rows=[]
    for region in ("P1","P2","P3"):
        root=task/"inputs"/region
        for directory,filename in (("scene","camera_receipt.json"),("surface","surface_receipt.json"),("prior","receipt.json"),("initialization","receipt.json")):
            receipt_path=root/directory/filename
            if not receipt_path.exists():continue
            receipt=json.loads(receipt_path.read_text())
            expected=receipt["config"]["sha256"] if "config" in receipt else receipt["inputs"][0]["sha256"]
            if expected not in candidates:
                raise ValueError(f"No byte-identical config revision for {receipt_path}: {expected}")
            value,method=candidates[expected]
            destination=root/directory/"run_config_snapshot.json"
            if destination.exists():
                if sha(destination)!=expected:raise ValueError("Existing config snapshot differs")
            else:
                with destination.open("xb") as stream:stream.write(value)
            rows.append(dict(receipt=str(receipt_path),config_snapshot=str(destination),sha256=expected,method=method))
        # Active initializers all began after initialization policy was added;
        # snapshot current exact bytes separately, without editing their receipts.
        active=root/"initialization"
        if active.exists() and not (active/"receipt.json").exists() and not (active/"run_config_snapshot.json").exists():
            with (active/"run_config_snapshot.json").open("xb") as stream:stream.write(current)
            rows.append(dict(config_snapshot=str(active/"run_config_snapshot.json"),sha256=hashlib.sha256(current).hexdigest(),
                             method="current_active_run_config_snapshot_receipt_match_pending"))
    receipt=task/"input_logs/config_snapshot_preservation_v1.json"
    write_json(receipt,dict(status="EXACT_COMPLETED_STAGE_CONFIG_REVISIONS_PRESERVED",rows=rows,scientific_verdict=None,
               original_receipts_modified=False,source_sha256=sha(__file__)))
    print(json.dumps({"records":len(rows),"completed_hashes":list(candidates)},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",required=True,type=Path)
    parser.add_argument("--task-root",required=True,type=Path)
    args=parser.parse_args()
    run(args.config,args.task_root)
