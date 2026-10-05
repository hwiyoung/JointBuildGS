"""Add an immutable cross-file provenance receipt after the CUDA audit."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(8<<20),b""):h.update(block)
    return h.hexdigest()


def main(config_path):
    config=json.loads(Path(config_path).read_text())
    audit_config=Path(config["audit_config"])
    cfg=json.loads(audit_config.read_text())
    audit_path=Path(config["audit_result"])
    result=json.loads(audit_path.read_text())
    arm=Path(cfg["baseline_arm"])
    paths=[audit_config,audit_path,Path(config["adapter_manifest"]),arm/"gaussians_initial.npz",arm.parent/"views.json",
        Path(cfg["audit_root"])/"baseline/rgb_reference.npz",Path("scripts/phd/p2_ab_v2/b_adapter_audit.py"),
        Path("scripts/phd/p2_ab_v2/b_adapter_audit_docker.sh"),Path(__file__),Path(config_path)]
    hashes={str(p):sha(p) for p in paths}
    audit_script=Path("scripts/phd/p2_ab_v2/b_adapter_audit.py").resolve()
    if hashes["scripts/phd/p2_ab_v2/b_adapter_audit.py"]!=result["source_hashes"][str(audit_script)]:
        raise ValueError("audit source changed since execution")
    output=Path("/output")
    for p in paths:
        if p.suffix in {".py",".sh",".json"}:
            dest=output/"snapshot"/str(p).lstrip("/");dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    receipt=dict(status="PASS",audit_status=result["status"],input_and_source_hashes=hashes,
        cuda_source_hashes={p:h for p,h in result["source_hashes"].items() if p.endswith(".cu")},
        timing="Post-audit binding of preserved inputs and unchanged audit source; not a claim of pre-run hash timing",
        scientific_verdict=None)
    (output/"audit_provenance_binding.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({"status":"PASS","hash_count":len(hashes)}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
