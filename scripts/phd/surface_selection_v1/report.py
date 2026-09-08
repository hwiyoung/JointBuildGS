"""Durable Korean stage report from sealed methods and verified evaluation files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from scripts.phd.surface_selection_v1.common import verify_seal, sha, write
from scripts.phd.surface_selection_v1.evaluate import write_csv


def number(value, digits=3):
    return "—" if value is None else f"{value:,.{digits}f}"


def percent(value):
    return "—" if value is None else f"{100 * value:.2f}%"


def verify_evaluation(run):
    config, _, digest = verify_seal(run)
    root = Path(run) / "evaluation"
    receipt = json.loads((root / "evaluation_receipt.json").read_text())
    if receipt.get("method_seal_sha256") != digest or receipt.get("scientific_verdict") is not None:
        raise ValueError("Evaluation receipt does not bind the current method seal")
    if receipt.get("reference_accessed_only_after_all_method_verification") is not True:
        raise ValueError("Evaluation has no all-method-before-reference gate")
    for relative, expected in receipt["output_sha256"].items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts or sha(root / name) != expected:
            raise ValueError("Evaluation output changed: " + relative)
    required = {"summary.json", "per_unit.json", "per_tile.json", "per_unit.csv", "per_tile.csv"}
    if not required <= set(receipt["output_sha256"]):
        raise ValueError("Incomplete evaluation receipt")
    return config, digest, receipt


def choose_cases(rows):
    """Posthoc inspection examples include failures; never feed them into method."""
    selected = []
    for region in ("P1", "P2", "P3"):
        local = [row for row in rows if row["region"] == region]
        pools = [
            ("채택 범위의 최대 참조 regret", [r for r in local if r["regret_m"] is not None],
             lambda r:r["regret_m"]),
            ("관측으로 직접 채택된 면적이 큰 단위", [r for r in local if r["accepted_area_m2"] > 0],
             lambda r:r["accepted_area_m2"]),
            ("큰 면적의 보류 단위", [r for r in local if r["action"] == "ABSTAIN"], lambda r:r["area_m2"]),
            ("단일 소스만 분할된 단위", [r for r in local if r["status"] == "SINGLE_SOURCE"], lambda r:r["area_m2"]),
            ("수직 중첩으로 후보가 모호한 단위", [r for r in local if "AMBIGUOUS" in r["status"]], lambda r:r["area_m2"]),
            ("표면 후보에서 제외된 원점이 많은 단위", local,
             lambda r:sum(r["native_counts"].values()) - sum(r["segmented_counts"].values())),
        ]
        seen = set()
        for reason, pool, key in pools:
            if not pool:
                continue
            candidate = max(pool, key=lambda row:(key(row), -row["unit_id"]))
            if candidate["unit_id"] in seen:
                continue
            seen.add(candidate["unit_id"])
            selected.append(dict(region=region, unit_id=candidate["unit_id"], inspection_reason=reason,
                action=candidate["action"], status=candidate["status"], reason=candidate["reason"],
                area_m2=candidate["area_m2"], accepted_area_m2=candidate["accepted_area_m2"],
                selected_error_m=candidate["selected_error_m"], regret_m=candidate["regret_m"],
                posthoc_reference_informed_inspection_only=True))
    return selected


def build_report(run, output, artifact_host_root, viewer_url=None):
    run, output = Path(run), Path(output)
    config, digest, receipt = verify_evaluation(run)
    summary = json.loads((run / "evaluation/summary.json").read_text())
    rows = json.loads((run / "evaluation/per_unit.json").read_text())
    viewer_url = viewer_url or f"http://127.0.0.1:{config.get('viewer', {}).get('port', 8904)}/"
    output.mkdir(parents=True, exist_ok=False)
    host = str(artifact_host_root).rstrip("/")
    link = lambda relative:f"{host}/run/{relative}"
    view = lambda region, unit=None, stage=1: viewer_url + "?" + urlencode(dict(
        region=region, stage=stage, **({"unit":unit} if unit is not None else {})))
    stage_rows = []
    lines = ["# 소스별 표면 분할·인접 그래프·관측 기반 선택: P1/P2/P3 기술 결과", "",
        "이 결과는 높이의 고정 구간 대신 **연결성·normal·평면의 수직 잔차**로 소스별 표면을 나누고, "
        "서로 다른 소스의 경계를 함께 유지한 단위에서 현재 다중뷰 관측을 집계한 개발 실험입니다. "
        "소스 선택은 직접 지지된 표본 타일에만 적용합니다. 지붕면 전체로 선택을 전파한 결과는 별도 가정 실험으로만 표시합니다.", "",
        f"[전체 결과 뷰어]({viewer_url}) · [단위별 CSV]({link('evaluation/per_unit.csv')}) · "
        f"[공통 공간 타일별 CSV]({link('evaluation/per_tile.csv')}) · [전체 평가 JSON]({link('evaluation/summary.json')})", "",
        "`scientific_verdict: null`. 브라우저 표시 검증과 연구 성능 판단은 별개입니다. 아래 거리는 기존 UAS 참조와의 수치적 이격이며, "
        "정합·수직 기준·시점 불확실성이 남아 있어 절대 정확도나 현재성 판정으로 해석하지 않습니다.", "",
        "## 1. 후보 입력: 무엇이 표면으로 나뉘었는가", "",
        "계산용 0.3 m voxel은 원점 소속을 색인합니다. 평면 적합·오차·출력 소속은 원래 좌표를 사용하며, "
        "평균 좌표로 형상을 교체하지 않습니다. -1 소속의 미지지 원점도 따로 보존됩니다. "
        "0.5 m XY 타일은 서로 다른 소스의 경계를 공통 분할하는 색인이며, 그 자체가 선택 대상 지붕면은 아닙니다.", "",
        "| 영역 | MVS 표면 수 | ALS 표면 수 | 공통 경계 단위 수 | MVS 원점 유지 | ALS 원점 유지 | 전체 면적 m² |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for region, result in summary["regions"].items():
        input_summary = json.loads((run / region / "input_summary.json").read_text())
        native, segmented = result["native_counts"], result["segmented_native_counts"]
        fraction = {s:segmented[s] / native[s] if native[s] else None for s in ("mvs", "als")}
        lines.append(f"| [{region}]({view(region)}) | {input_summary['components']['mvs']:,} | "
            f"{input_summary['components']['als']:,} | {result['total_units']:,} | {percent(fraction['mvs'])} | "
            f"{percent(fraction['als'])} | {number(result['total_area_m2'], 2)} |")
        stage_rows.append(dict(region=region, stage="candidate_input", mvs_components=input_summary["components"]["mvs"],
            als_components=input_summary["components"]["als"], units=result["total_units"],
            mvs_native_fraction=fraction["mvs"], als_native_fraction=fraction["als"], total_area_m2=result["total_area_m2"]))
    lines += ["", "표면의 연결 normal이 유사하더라도 떨어진 지붕을 하나로 합치지 않습니다. "
        "표면 인접 그래프의 COPLANAR_CONTINUATION / CREASE_OR_STEP / UNCERTAIN은 실제 유한 경계 접촉의 진단이며, 소스 라벨 전파 규칙이 아닙니다. "
        "이 분할은 기하 표면 가설입니다. 지붕·벽·증축부라는 의미 클래스가 검증되었다는 뜻은 아닙니다.", "",
        "| 영역 | MVS 원점 → 분할 원점 이격 m | ALS 원점 → 분할 원점 이격 m |",
        "|---|---:|---:|"]
    for region, result in summary["regions"].items():
        metrics = result["whole_native_point_weighted_diagnostics"]
        def transition(source):
            return f"{number(metrics[source + '_whole_native']['symmetric_mean_m'])} → {number(metrics[source + '_segmented_native']['symmetric_mean_m'])}"
        lines.append(f"| {region} | {transition('mvs')} | {transition('als')} |")
    lines += ["", "이 표는 선택 전 표현 손실을 확인하는 동일 영역 진단입니다. 점 밀도와 빈 공간도 NN 이격에 영향을 주므로, "
        "분할 후 평균 이격이 줄어든 것만으로 더 좋은 형상을 얻었다고 결론 내리지 않습니다.", "",
        "## 2. 관측 평가: 어디까지 현재 영상이 지지하는가", "",
        "각 단위의 내부와 경계에서 소스별 유한 원점 지지·자기 소스 가시성·여러 영상쌍의 광도 일관성과 깊이 방향 프로파일을 확인합니다. "
        "다른 소스가 없는 단위도 자기 관측 지지를 평가할 수 있습니다. 한 소스가 실패했다는 사실만으로 다른 소스를 채택하지 않습니다.", "",
        "| 영역 | IMAGE / PRIOR / ABSTAIN 단위 | 직접 채택된 면적 m² | 직접 채택 / 전체 | 단위 전체 전파 가정 면적 m² | 기존 2 m 셀 채택 면적 m² |",
        "|---|---:|---:|---:|---:|---:|"]
    for region, result in summary["regions"].items():
        count = result["action_unit_counts"]
        lines.append(f"| [{region}]({view(region, stage=3)}) | {count.get('IMAGE',0)} / {count.get('PRIOR',0)} / {count.get('ABSTAIN',0)} | "
            f"{number(result['directly_sampled_accepted_area_m2'], 2)} | {percent(result['directly_sampled_coverage'])} | "
            f"{number(result['conditional_whole_unit_area_m2'], 2)} | {number(result['legacy_accepted_area_m2'], 2)} |")
        stage_rows.append(dict(region=region, stage="observation_and_scope", accepted_area_m2=result["directly_sampled_accepted_area_m2"],
            actual_coverage=result["directly_sampled_coverage"], conditional_whole_unit_area_m2=result["conditional_whole_unit_area_m2"],
            legacy_area_m2=result["legacy_accepted_area_m2"], abstain_or_unsampled_area_m2=result["abstain_or_unsampled_area_m2"]))
    lines += ["", "직접 채택 면적은 지지된 표본이 속한 타일의 면적 합입니다. 해당 타일의 모든 점이나 모든 픽셀이 관측 검증됐다는 뜻은 아닙니다. "
        "실제 채택 범위 밖의 같은 지붕면과 인접 단위는 자동으로 확장하지 않습니다.", "",
        "## 3. 소스 판단: 같은 공간에서 무엇이 나아졌는가", "",
        "새 결과와 기존 2 m 결과를 동일한 0.5 m 타일로 투영해 비교합니다. 타일의 실제 면적으로 가중하며, "
        "크기가 다른 표면 단위에 같은 한 표를 주지 않습니다. 전체 영역·보류·미관측도 분모에서 유지합니다. "
        "참조 이격 차이가 0.1 m 이하인 소스쌍은 동률이며 정답 개수로 세지 않습니다. 단일 소스에는 상대 소스 oracle이나 regret을 만들지 않습니다.", "",
        "| 영역 | 같은 채택 공간 MVS / ALS / 선택 이격 m | 평균 regret m | 오선택 면적 m² | 새·기존 모두 채택된 공간의 이격 차 m |",
        "|---|---:|---:|---:|---:|"]
    for region, result in summary["regions"].items():
        paired = result["same_accepted_paired_tiles"]
        error = " / ".join(number(paired[key]["mean"]) for key in ("mvs_error_m", "als_error_m", "selected_error_m"))
        delta = result["same_new_and_legacy_accepted_tiles"]["new_minus_legacy_error_m"]["mean"]
        lines.append(f"| [{region}]({view(region, stage=4)}) | {error} | {number(paired['regret_m']['mean'])} | "
            f"{number(result['accepted_incorrect_clear_gap_area_m2'], 2)} | {number(delta)} |")
        stage_rows.append(dict(region=region, stage="source_judgment", paired_accepted_area_m2=result["accepted_paired_reference_area_m2"],
            incorrect_clear_gap_area_m2=result["accepted_incorrect_clear_gap_area_m2"], regret_mean_m=paired["regret_m"]["mean"],
            matched_legacy_delta_m=delta))
    lines += ["", "새·기존 차이가 음수이면 **두 방법이 모두 채택했고 참조가 존재하는 동일 공간에서** 새 결과의 수치적 이격이 더 작다는 뜻입니다. "
        "새로 채택한 쉬운 부분과 기존 전체 영역을 비교하지 않습니다. ‘—’는 비교 근거가 없음을 뜻하며 0 오차가 아닙니다.", "",
        "| 영역 | 0.5 m 이내 참조 회수율: 직접 채택 | 단위 전체 전파 가정 | 기존 2 m 선택 |",
        "|---|---:|---:|---:|"]
    for region, result in summary["regions"].items():
        def recall(name):
            return next(r["recall"] for r in result["tile_constrained_completeness"][name] if r["threshold_m"] == .5)
        lines.append(f"| {region} | {percent(recall('directly_sampled'))} | {percent(recall('conditional_whole_unit'))} | {percent(recall('legacy'))} |")
    lines += ["", "보류·미표본 타일의 참조점은 모두 미복원으로 계산합니다. 인접 타일의 점이 가까워도 이 공간 누락을 메우지 않습니다. "
        "단위 전체 전파 가정은 관측 범위 확대의 잠재 영향과 위험을 확인하는 대조값입니다.", "",
        "## 4. 정성 검수: 성공과 실패를 직접 열어보기", "",
        "아래 사례는 **판단 완료 후 보고서 검수를 위해** 선정했습니다. 참조 regret으로 방법의 임계값이나 소스 선택을 바꾸지 않았습니다. "
        "뷰어에서 모든 영역·표면·단위를 전환할 수 있고, 아래 표는 우선 검수할 사례만 연결합니다.", "",
        "| 영역·단위 | 검수 이유 | 실제 소스 판단 | 전체 / 직접 채택 면적 m² | 직접 범위 regret m |",
        "|---|---|---|---:|---:|"]
    cases = choose_cases(rows)
    for case in cases:
        url = view(case["region"], case["unit_id"], 3)
        case["viewer_url"] = url
        lines.append(f"| [{case['region']} · {case['unit_id']}]({url}) | {case['inspection_reason']} | {case['action']} | "
            f"{number(case['area_m2'],2)} / {number(case['accepted_area_m2'],2)} | {number(case['regret_m'])} |")
    lines += ["", "검수 순서는 ① 같은 지붕면이 불필요하게 쪼개졌거나 다른 높이의 면이 합쳐졌는지, "
        "② 인접 경계를 넘는 집계나 수직 중첩의 숨은 소스 선택이 있는지, ③ 원본 사진의 실제 관측이 채택 근거와 일치하는지, "
        "④ 지지 범위 밖으로 현재성을 확대 해석했는지입니다.", "",
        "## 5. 재현성과 해석 범위", "",
        f"- 방법 봉인 SHA256: `{digest}`",
        f"- 기존 방법 봉인 SHA256: `{summary['legacy_method_seal_sha256']}`",
        f"- [고정 설정]({link('config.json')}) · [방법 봉인]({link('method_seal.json')}) · "
        f"[참조 접근·출력 해시 영수증]({link('evaluation/evaluation_receipt.json')})",
        "- 모든 방법 결과를 P1/P2/P3 전체에 대해 봉인한 후에만 참조를 열었고, 평가 완료 후 방법·기존 결과의 모든 봉인 바이트를 다시 검증했습니다.",
        "- 원래 좌표·소속을 사용하며, 재정합·GT 평면 적합·GT 임계값 선택·GS 학습은 이 실험에서 수행하지 않았습니다.",
        "- 고정 셀에서 구조 단위로 바꾸면서 후보 표현과 관측 규칙도 함께 바뀌었습니다. 개선이나 악화를 셀 크기 하나의 효과로 분리할 수 없습니다.",
        "- 법선·높이 정보는 경사진 지붕과 높이 차를 나누는 데 유용하지만, 저밀도·식생·경계 혼합·정합 오차에서는 잘못된 분리/합침이 생길 수 있습니다. 원점 유지율·표면 개수·모호한 중첩·보류 범위를 함께 검토해야 합니다.",
        "- P1/P2/P3 개발 결과이며 독립 시험·일반화·공식 성능 판정은 아닙니다.", ""]
    with (output / "REPORT_ko.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    write(output / "stage_summary.json", stage_rows)
    write_csv(output / "stage_summary.csv", stage_rows)
    write(output / "qualitative_cases.json", cases)
    write(output / "report_receipt.json", dict(scientific_verdict=None, method_seal_sha256=digest,
        evaluation_receipt_sha256=sha(run / "evaluation/evaluation_receipt.json"), viewer_url=viewer_url,
        output_sha256={p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file()}))
    return output / "REPORT_ko.md"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--artifact-host-root", required=True)
    parser.add_argument("--viewer-url")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Project report generation requires Docker")
    print(build_report(args.run, args.output, args.artifact_host_root, args.viewer_url))


if __name__ == "__main__":
    main()
