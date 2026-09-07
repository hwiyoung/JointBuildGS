"""Publish one verified protocol and all three native comparison receipts."""
import argparse
import json
import os
from pathlib import Path

from scripts.phd.wu_vallet_regions_v4.compose_comparison import sha


def main(config, output):
    cfg = json.loads(config.read_text())
    root = Path(cfg["evaluation_root"])
    receipt_path, gate_path = root / "receipt.json", root / "MATCHED_PROTOCOL.json"
    receipt, gate = json.loads(receipt_path.read_text()), json.loads(gate_path.read_text())
    if receipt["status"] != "REGIONAL_WU_BEFORE_AFTER_REFERENCE_EVALUATION_COMPLETE" or gate["status"] != "PASS_MATCHED_THREE_REGION_PROTOCOL_BEFORE_REFERENCE":
        raise ValueError("Complete evaluation and pre-reference matched protocol required")
    if [r["id"] for r in receipt["regions"]] != cfg["region_order"]:
        raise ValueError("Three matched regions in fixed order required")
    inputs = {str(path): sha(path) for path in (config, receipt_path, gate_path)}
    if sha(root / "PRE_REFERENCE_CANDIDATE_SEAL.json") != receipt["candidate_seal_sha256"]:
        raise ValueError("Candidate-before-reference seal hash mismatch")
    for row, protocol in zip(receipt["regions"], gate["regions"]):
        path = Path(row["evaluation_json"])
        evaluation = json.loads(path.read_text())
        for filename, expected in evaluation["outputs"].items():
            if sha(path.parent / filename) != expected:
                raise ValueError("Frozen evaluation output hash mismatch")
        if sha(row["reference_npz"]) != protocol["reference_sha256"] or sha(row["common_npz"]) != protocol["common_source_sha256"]:
            raise ValueError("Common source or exact reference identity mismatch")
        inputs[str(path)] = sha(path)
        row["note"] = (f"v5 동일 규칙 검증 통과. 고정된 {protocol['frozen_views']}개 시점을 모두 점검하고 "
                       f"영상 자체의 0.5m XY 지원으로 {protocol['image_id']}번 시점을 선택했습니다. "
                       "원점·메시·광선·정제·평가 규칙을 세 구역에 동일하게 적용했습니다. UAS는 후보 봉인 후 평가에만 사용했습니다.")
        row["matched_protocol"] = protocol
    output.mkdir(parents=True, exist_ok=False)
    final = dict(status="MATCHED_COMPARISON_RECEIPTS_COMPOSED", task_id=cfg["task_id"],
                 scientific_verdict=None, full_author_reproduction=False, regions=receipt["regions"],
                 matched_protocol=gate, matched_protocol_path=str(gate_path), input_hashes=inputs,
                 metrics_recomputed=False, candidate_outputs_modified=False,
                 source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                 container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                 source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"))
    with (output / "receipt.json").open("x") as stream:
        json.dump(final, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps({"status": final["status"], "regions": cfg["region_order"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.output)
