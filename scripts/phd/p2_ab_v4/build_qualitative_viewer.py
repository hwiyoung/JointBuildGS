"""Score the same pixels and export exact saved P2 renders for visual inspection."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

import cv2
import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rgb(path):
    value = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if value is None:
        raise ValueError(f"unreadable RGB: {path}")
    return cv2.cvtColor(value, cv2.COLOR_BGR2RGB)


def pixel_metrics(prediction, target, mask, mass):
    if prediction.shape != target.shape or mask.shape != target.shape[:2] or mass.shape != mask.shape:
        raise ValueError("unaligned comparison pixels")
    n = int(mask.sum())
    if not n:
        raise ValueError("empty common comparison support")
    error = (prediction.astype(np.float64) - target.astype(np.float64)) / 255.0
    values = error[mask]
    absolute_sum = float(np.abs(values).sum())
    squared_sum = float(np.square(values).sum())
    mse = squared_sum / (3 * n)
    return dict(mae=absolute_sum / (3 * n), psnr_db=-10 * math.log10(mse) if mse > 0 else None,
                pixels=n, absolute_rgb_sum=absolute_sum, squared_rgb_sum=squared_sum,
                geometry_present_pixels=int((mass[mask] >= .5).sum()),
                geometry_present_fraction=float((mass[mask] >= .5).mean()))


def build(config_path, destination):
    cv2.setNumThreads(1)
    cfg = json.loads(Path(config_path).read_text())
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False)
    inputs = {}

    def bind(path):
        inputs[str(path)] = sha(path)
        return path

    def copy(source, relative):
        source = bind(Path(source))
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha(target) != inputs[str(source)]:
            raise ValueError("copied rendered pixels changed")
        return relative

    mvs, als0, als3 = (Path(cfg[key]) for key in ("mvs_root", "als_sh0_root", "als_sh3_root"))
    results = [json.loads(bind(root / "result.json").read_text()) for root in (mvs, als0, als3)]
    if any(r["status"] != "COMPLETED_DIAGNOSTIC" for r in results):
        raise ValueError("a comparison run did not complete")
    view_ids = [[int(row["image_id"]) for row in r["arms"][0]["initial"]["metrics"]] for r in results]
    if not (view_ids[0] == view_ids[1] == view_ids[2]) or len(set(view_ids[0])) != 11:
        raise ValueError("comparison requires the same 11 unique views")
    specs = [
        ("mvs_initial", "MVS 초기", "MVS", "initial", mvs / "initial"),
        ("mvs_sh0_uniform", "MVS · SH0 균일", "MVS", "final", mvs / "sh0_uniform"),
        ("mvs_sh0_residual_weighted", "MVS · SH0 잔차 가중", "MVS", "final", mvs / "sh0_residual_weighted"),
        ("mvs_sh3_uniform", "MVS · SH3 균일", "MVS", "final", mvs / "sh3_uniform"),
        ("mvs_sh3_residual_weighted", "MVS · SH3 잔차 가중", "MVS", "final", mvs / "sh3_residual_weighted"),
        ("als_initial", "이전 ALS 초기 · A 미적용", "ALS", "initial", als0 / "initial"),
        ("als_sh0_uniform", "이전 ALS · SH0 균일", "ALS", "final", als0 / "uniform"),
        ("als_sh0_residual_weighted", "이전 ALS · SH0 잔차 가중", "ALS", "final", als0 / "residual_weighted"),
        ("als_sh3_uniform", "이전 ALS · SH3 균일", "ALS", "final", als3 / "uniform"),
        ("als_sh3_residual_weighted", "이전 ALS · SH3 잔차 가중", "ALS", "final", als3 / "residual_weighted"),
    ]
    models = [dict(id=i, label=label, source=source, phase=phase) for i, label, source, phase, _ in specs]
    rows = []
    summary = {m["id"]: dict(pixels=0, absolute_rgb_sum=0., squared_rgb_sum=0., geometry_present_pixels=0) for m in models}
    for view_id in view_ids[0]:
        target_path = mvs / "initial" / f"target_{view_id}.png"
        target = read_rgb(bind(target_path))
        for root in (als0, als3):
            other = root / "initial" / target_path.name
            if sha(bind(other)) != sha(target_path):
                raise ValueError("MVS and ALS comparison targets differ")
        masks = []
        for root in (mvs, als0):
            path = bind(root / "initial" / f"support_{view_id}.png")
            mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if mask is None or mask.shape != target.shape[:2]:
                raise ValueError("invalid initial support mask")
            masks.append(mask > 0)
        common = masks[0] | masks[1]
        base = f"images/{view_id}"
        target_url = copy(target_path, f"{base}/target.png")
        support_url = f"{base}/common_support.png"
        cv2.imwrite(str(output / support_url), common.astype(np.uint8) * 255)
        row = dict(image_id=view_id, width=target.shape[1], height=target.shape[0],
            target=target_url, support=support_url, common_pixels=int(common.sum()),
            source_support_pixels=dict(MVS=int(masks[0].sum()), ALS=int(masks[1].sum()),
                                       intersection=int((masks[0] & masks[1]).sum())), images={}, metrics={})
        for model_id, _, _, _, root in specs:
            rgb_path = root / f"rgb_{view_id}.png"
            prediction = read_rgb(bind(rgb_path))
            mass = np.load(bind(root / f"geometry_mass_{view_id}.npy"), allow_pickle=False)
            if not np.isfinite(mass).all():
                raise ValueError("nonfinite geometry mass")
            metric = pixel_metrics(prediction, target, common, mass)
            row["images"][model_id] = copy(rgb_path, f"{base}/{model_id}.png")
            row["metrics"][model_id] = metric
            for key in summary[model_id]:
                summary[model_id][key] += metric[key]
        rows.append(row)
    for value in summary.values():
        n = value["pixels"]
        mse = value["squared_rgb_sum"] / (3 * n)
        value.update(mae=value["absolute_rgb_sum"] / (3 * n), psnr_db=-10 * math.log10(mse) if mse > 0 else None,
                     geometry_present_fraction=value["geometry_present_pixels"] / n)
    data = dict(default_view_id=cfg["default_view_id"], models=models, views=rows, summary=summary,
        scientific_verdict=None, scope=dict(
            A="합성 스칼라 검산만 실행. 실제 P2 소스 판단은 미실행.",
            B="변화 사례 P2에 사용자 지시로 MVS 초기화. 네 조건 모두 기하 고정·외관 갱신.",
            ALS="이전 ALS 초기화는 별도 외관 진단. A가 채택한 결과가 아님.",
            comparison="초기 ALS/MVS 관측 지지 합집합의 같은 픽셀을 모든 조건에서 평가. 누락을 제외하지 않음.",
            display="저장된 gsplat RGB 원본. SH3 전체 시선 색이 반영됨. 색 보정·생성·DC 대체 없음.",
            limitation="A+B 통합 판단/세부 기하 복원/독립 장면 성능 검증은 미완료."))
    (output / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    for name in ("index.html", "app.js", "style.css"):
        copy(Path("src/apps/p2_ab_inspector_v4") / name, name)
    source_paths = [Path(__file__), Path(config_path)]
    source_paths += list(Path("src/apps/p2_ab_inspector_v4").glob("*"))
    receipt = dict(task_id=cfg["task_id"], status="COMPLETED_EXPORT_AND_COMMON_PIXEL_EVALUATION",
        created_utc=datetime.now(timezone.utc).isoformat(), scientific_verdict=None, config=cfg,
        source_sha256={str(p): sha(p) for p in source_paths if p.is_file()}, input_sha256=inputs,
        output_sha256={str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()},
        summary=summary, view_count=len(rows), model_count=len(models),
        pixels_per_model=sum(row["common_pixels"] for row in rows),
        versions=dict(numpy=np.__version__, opencv=cv2.__version__,
                      git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
                      container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID")))
    (output / "technical_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(status=receipt["status"], views=len(rows), models=len(models), summary=summary), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(args.config, args.output)
