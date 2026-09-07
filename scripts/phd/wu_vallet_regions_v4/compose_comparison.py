"""Compose verified evaluation receipts without recomputing or changing metrics."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(config, output):
    cfg = json.loads(config.read_text())
    artifact_root = Path(cfg["artifact_root"])
    rows, inputs = {}, {str(config): sha(config), str(Path(__file__)): sha(__file__)}
    for relative in cfg["evaluations"]:
        path = artifact_root / relative
        receipt = json.loads(path.read_text())
        assert receipt["status"] == "REGIONAL_WU_BEFORE_AFTER_REFERENCE_EVALUATION_COMPLETE"
        assert receipt["scientific_verdict"] is None
        inputs[str(path)] = sha(path)
        for row in receipt["regions"]:
            assert row["id"] not in rows
            evaluation_path = Path(row["evaluation_json"])
            evaluation = json.loads(evaluation_path.read_text())
            assert evaluation["scientific_verdict"] is None
            for filename, expected in evaluation["outputs"].items():
                assert sha(evaluation_path.parent / filename) == expected
            inputs[str(evaluation_path)] = sha(evaluation_path)
            row["note"] = cfg["notes"][row["id"]]
            if row["id"] in cfg["support_figures"]:
                figure = artifact_root / cfg["support_figures"][row["id"]]
                inputs[str(figure)] = sha(figure)
                row["figures"].insert(0, dict(id="image_support", label="실제 사진과 관측 지원", path=str(figure),
                                             caption="현재 영상 기하의 지원·가림 진단. UAS를 사용하지 않았으며 갱신 결과로 시점을 선택하지 않았습니다."))
            rows[row["id"]] = row
    assert set(rows) == set(cfg["region_order"])
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="REGIONAL_COMPARISON_RECEIPTS_COMPOSED", task_id=cfg["task_id"],
                   scientific_verdict=None, full_author_reproduction=False,
                   regions=[rows[key] for key in cfg["region_order"]], input_hashes=inputs,
                   metrics_recomputed=False, candidate_outputs_modified=False,
                   comparison_pairs=[["P1", "P1_visible"], ["P2", "P2_visible"]],
                   interpretation="Native before/after/reference diagnostics. View support selection is an input control, not a new judgment method. All cases are non-confirmatory; pointwise change truth and calibrated CRS/epoch alignment are unavailable.",
                   source_git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"), container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"),
                   source_snapshot_manifest=os.environ.get("JBGS_SOURCE_SNAPSHOT_MANIFEST"))
    with (output / "receipt.json").open("x") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(dict(status=receipt["status"], regions=list(rows))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.config, args.output)
