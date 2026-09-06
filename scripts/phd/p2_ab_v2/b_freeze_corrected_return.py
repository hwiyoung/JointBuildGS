"""Freeze B-owned source and link immutable corrected results without editing runs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(8<<20),b""):h.update(chunk)
    return h.hexdigest()


def main(config_path):
    cfg=json.loads(Path(config_path).read_text());output=Path("/output")
    if any(output.iterdir()):raise ValueError("empty new return directory required")
    sources=[]
    for pattern in cfg["source_globs"]:sources.extend(Path(".").glob(pattern))
    source_hashes={str(p):sha(p) for p in sorted(set(sources)) if p.is_file()}
    for p in source_hashes:
        destination=output/"source_snapshot"/p;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
    linked={}
    for path in cfg["receipts"]:
        p=Path(path);linked[path]={"sha256":sha(p),"bytes":p.stat().st_size}
    manifest=dict(status="COMPLETED_DEVELOPMENT",created_utc=datetime.now(timezone.utc).isoformat(),
        source_hashes=source_hashes,linked_receipts=linked,scientific_verdict=None,
        scope="B conditional reconstruction, corrected independent plane geometry; old results remain preserved and invalid for method conclusion",
        source_unchanged_during_freeze=all(sha(p)==h for p,h in source_hashes.items()))
    if not manifest["source_unchanged_during_freeze"]:raise ValueError("source changed during freeze")
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"status":manifest["status"],"source_files":len(source_hashes),"linked_receipts":len(linked)}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
