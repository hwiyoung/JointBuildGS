#!/usr/bin/env python3
"""Build/deploy the S3 verification static viewers into the shared bundle root.

Pages: viewer_p1 (평면 가설 S1) + viewer_p2 (배열·초기값 S2) + viewer_p3
(공동 최적화 연속 구간 — 3차 내부 단계 3a 렌더-온리부터, 계획 문서 개정 주석
2026-08-27); later pages plug into PAGES. NOT OFFICIAL · scientific_verdict: null.

Reads configs/phd/s3_verify_v1/s1_bundle_v1.json (contract defaults when the
file does not exist yet), then, inside the bundle root
(phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1/), for each page:
  1. viewer_pN/            index.html + app.js copied from the repo,
                           three.module.min.js copied from the existing
                           journal1 phase-B payload (build_arrgs_viewer.py:18-19
                           source path reused) — CDN 금지.
  2. viewer_pN/manifest.json   run list + references only (geometry never
                           inlined — the 243 MB blank-viewer lesson). The
                           `pages` key cross-lists every deployed page.
  3. viewer_pN/web_receipt_v1.json   input sha256 + counts + serve note.

Page 2 reads the S2 additions (s2_cells/s2_faces/s2_seeds) of the same run
directories; page 3 additionally reads the S3a additions (s3_views.json,
s3_steps.jsonl, s3_face_residual.json + s3_tiles/<view_id>/*.png — contract
phd_s3_verify_s3a_v1) and, when present, the S3b additions (contract
phd_s3_verify_s3b_v1 — stage:"3b" rows appended to s3_steps.jsonl,
s3_face_residual_final.json, checkpoint tiles s3_tiles/s<step>/<view_id>/,
manifest stage "s1+s2+s3a+s3b" + s3b_def). Runs without them are listed with
s2_ready/s3_ready/s3b_ready=false and the pages show an empty state instead of
dying. s3_tiles/ is a directory payload: its presence is recorded per run, but
only the declared run files are hashed into the receipt (tiles are regenerable
from the writer).

Usage:
  python scripts/phd/s3_verify_v1/build_verify_pages.py
  python scripts/phd/s3_verify_v1/build_verify_pages.py --config configs/phd/s3_verify_v1/s1_bundle_v1.json

Serve (root = bundle root, the parent of viewer_p*/, so ../runs/ resolves):
  cd <bundle_root> && python3 -m http.server 8885 --bind 0.0.0.0
  -> http://<host>:8885/viewer_p1/  http://<host>:8885/viewer_p2/  http://<host>:8885/viewer_p3/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC_ROOT = Path(__file__).resolve().parent
ART_HOST = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
CONTAINER_PREFIX = "/artifacts/JointBuildGS"
DEFAULT_CONFIG_PATH = REPO / "configs/phd/s3_verify_v1/s1_bundle_v1.json"

# Contract defaults (phd_s3_verify_s1_bundle_v1) — used only for the keys this
# builder needs when the shared config does not exist yet. The writer-owned
# keys (inlier tau, thinning, o_init, seeds, synth_als, prereg values) are not
# invented here; the viewers read them from each run's own manifest.json.
CONTRACT_DEFAULTS = {
    "out_root": CONTAINER_PREFIX + "/phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1",
    "runs": ["B022", "B173", "B036", "SYNTH_GABLE"],
    "viewer": {
        "three_module_src": (CONTAINER_PREFIX
                             + "/phase-payloads/p2/journal1_phase_b_v1/"
                               "P2-JOURNAL1-PHASE-B-v1/viewer/three.module.min.js"),
        "port": 8885,
        "serve_note": ("정적 서빙 루트 = PHD-S3-VERIFY-PAGES-v1/ (viewer_p*의 부모)"
                       " — 뷰어는 ../runs/ 상대경로. 포트 8885."
                       " NOT OFFICIAL · scientific_verdict: null"),
    },
}

S1_RUN_FILES = ["manifest.json", "s1_points.ply", "s1_planes.json",
                "s1_orphans.json", "s1_view.json"]
S2_RUN_FILES = ["s2_cells.json", "s2_faces.json", "s2_seeds.json"]
S3_RUN_FILES = ["s3_views.json", "s3_steps.jsonl", "s3_face_residual.json"]
# S3b 추가분 — 선택적(3a-only 런은 s3b 없이도 s3_ready 유지); s3_steps.jsonl의
# stage:"3b" 행 추가와 체크포인트 타일(s3_tiles/s<step>/)은 파일 목록에 새 항목이 없다.
S3B_RUN_FILES = ["s3_face_residual_final.json"]
S1_SCHEMA = "phd_s3_verify_s1_bundle_v1"

# 페이지 등록부 — page/manifest_schema는 각 페이지 app.js·판독 기록 스키마와 짝.
PAGES = [
    {"dir": "viewer_p1", "page": "p1_plane_hypothesis",
     "title": "페이지 1 — 평면 가설",
     "manifest_schema": "phd_s3_verify_viewer_p1_manifest_v1",
     "run_files": S1_RUN_FILES},
    {"dir": "viewer_p2", "page": "p2_arrangement_init",
     "title": "페이지 2 — 배열·초기값",
     "manifest_schema": "phd_s3_verify_viewer_p2_manifest_v1",
     "run_files": S1_RUN_FILES + S2_RUN_FILES},
    {"dir": "viewer_p3", "page": "p3_joint_opt_continuous",
     "title": "페이지 3 — 공동 최적화(연속 구간)",
     "manifest_schema": "phd_s3_verify_viewer_p3_manifest_v1",
     "run_files": S1_RUN_FILES + S2_RUN_FILES + S3_RUN_FILES + S3B_RUN_FILES},
]


def resolve_path(p: str | Path) -> Path:
    """Map the container artifact prefix to the local sibling checkout when the
    container mount root itself is absent (builder runs on either host); resolve
    bare relative paths against the repo root. The container decision keys off
    the mount ROOT, not the full path — the target dir may legitimately not
    exist yet (first build creates it)."""
    p = str(p)
    if p.startswith(CONTAINER_PREFIX) and not Path(CONTAINER_PREFIX).is_dir():
        return ART_HOST / p[len(CONTAINER_PREFIX):].lstrip("/")
    path = Path(p)
    if not path.is_absolute():
        return REPO / path
    return path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: Path) -> tuple[dict, Path | None]:
    cfg = json.loads(json.dumps(CONTRACT_DEFAULTS))  # deep copy
    if path.is_file():
        user = json.load(open(path))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg, path
    print(f"[build] config 없음: {path} — 계약 기본값 사용")
    return cfg, None


def scan_runs(runs_root: Path, ordered_names: list[str],
              run_files: list[str]) -> list[dict]:
    """Run list + references only. Small scalars from each run manifest are
    copied for dropdown labels; geometry stays behind relative-path fetches."""
    found: dict[str, dict] = {}
    if runs_root.is_dir():
        for run_dir in sorted(runs_root.iterdir()):
            mp = run_dir / "manifest.json"
            if not mp.is_file():
                continue
            try:
                m = json.load(open(mp))
            except Exception as e:
                print(f"[build] skip {run_dir.name}: manifest 파싱 실패 ({e})")
                continue
            if m.get("schema") != S1_SCHEMA:
                print(f"[build] skip {run_dir.name}: schema={m.get('schema')!r}")
                continue
            files = {fn: (run_dir / fn).is_file() for fn in run_files}
            s2_ready = ("s2" in str(m.get("stage") or "")
                        and all((run_dir / fn).is_file() for fn in S2_RUN_FILES))
            s3_ready = ("s3" in str(m.get("stage") or "")
                        and all((run_dir / fn).is_file() for fn in S3_RUN_FILES))
            s3b_ready = ("s3b" in str(m.get("stage") or "")
                         and all((run_dir / fn).is_file() for fn in S3B_RUN_FILES))
            found[run_dir.name] = {
                "name": run_dir.name,
                "dir": f"runs/{run_dir.name}",
                "schema": m.get("schema"),
                "stage": m.get("stage"),
                "s1_mode": m.get("s1_mode"),
                "dataset": m.get("dataset"),
                "crs": m.get("crs"),
                "counts": m.get("counts"),
                "prereg": m.get("prereg"),
                "volumes": m.get("volumes"),
                "o_init_def": m.get("o_init_def"),
                "synthetic_als": m.get("synthetic_als"),
                "s2_ready": s2_ready,
                "s3_ready": s3_ready,
                "s3b_ready": s3b_ready,
                "s3_def": m.get("s3_def"),
                "s3b_def": m.get("s3b_def"),
                "s3_tiles": (run_dir / "s3_tiles").is_dir(),
                "files": files,
            }
    ordered = [found.pop(n) for n in ordered_names if n in found]
    ordered += [found[n] for n in sorted(found)]  # extras beyond the config list
    return ordered


def deploy_page(page: dict, out_root: Path, cfg: dict, cfg_path: Path | None,
                built_at: str, pages_index: list[dict]) -> tuple[int, str]:
    viewer_cfg = cfg.get("viewer", {})
    port = viewer_cfg.get("port", 8885)
    serve_note = viewer_cfg.get("serve_note",
                                CONTRACT_DEFAULTS["viewer"]["serve_note"])
    src_dir = SRC_ROOT / page["dir"]
    viewer_dir = out_root / page["dir"]
    viewer_dir.mkdir(parents=True, exist_ok=True)

    # 1) app files — repo copies + vendored three.js (CDN 금지)
    inputs: dict[str, dict] = {}
    for fn in ("index.html", "app.js"):
        src = src_dir / fn
        shutil.copy2(src, viewer_dir / fn)
        inputs[f"repo:scripts/phd/s3_verify_v1/{page['dir']}/{fn}"] = {
            "sha256": sha256_file(src), "bytes": src.stat().st_size}
    three_src = resolve_path(viewer_cfg.get(
        "three_module_src", CONTRACT_DEFAULTS["viewer"]["three_module_src"]))
    three_dst = viewer_dir / "three.module.min.js"
    if not three_src.is_file():  # 폴백: 이미 배포된 다른 페이지의 vendored 복사본 재사용
        for other in PAGES:
            alt = out_root / other["dir"] / "three.module.min.js"
            if alt.is_file() and alt != three_dst:
                three_src = alt
                break
    if three_src.is_file():
        if not three_dst.is_file():
            shutil.copy2(three_src, three_dst)
        three_dst.chmod(0o644)  # source copy is 0600 — keep it servable
        inputs["three.module.min.js"] = {
            "src": str(three_src), "sha256": sha256_file(three_dst),
            "bytes": three_dst.stat().st_size}
    elif not three_dst.is_file():
        print(f"[build] 경고: three.module.min.js 원본 없음: {three_src} — 뷰어 동작 불가")
    if cfg_path is not None:
        inputs[f"config:{cfg_path.relative_to(REPO) if cfg_path.is_relative_to(REPO) else cfg_path}"] = {
            "sha256": sha256_file(cfg_path), "bytes": cfg_path.stat().st_size}

    # 2) run scan -> viewer manifest (참조만)
    runs = scan_runs(out_root / "runs", list(cfg.get("runs", [])),
                     page["run_files"])
    if not runs:
        print(f"[build] 경고: {out_root / 'runs'} 에 s1 번들 런 0개 — "
              "writer 실행 후 이 스크립트를 재실행하면 manifest가 갱신된다.")
    if page["dir"] == "viewer_p2":
        missing = [r["name"] for r in runs if not r["s2_ready"]]
        if missing:
            print(f"[build] 페이지 2 참고: S2 미생성 런 {missing} — "
                  "빈 상태 안내로 표시된다 (writer 소관).")
    if page["dir"] == "viewer_p3":
        missing = [r["name"] for r in runs if not r.get("s3_ready")]
        if missing:
            print(f"[build] 페이지 3 참고: S3a 미생성 런 {missing} — "
                  "빈 상태 안내로 표시된다 (writer 소관: s3_views/s3_steps/"
                  "s3_face_residual/s3_tiles).")
        with_3b = [r["name"] for r in runs if r.get("s3b_ready")]
        if with_3b:
            print(f"[build] 페이지 3: 3b 보유 런 {with_3b} — "
                  "타임라인 3b 구간·final 히트맵 활성.")
    manifest = {
        "schema": page["manifest_schema"],
        "page": page["page"],
        "note": f"S3 검증 {page['title']} — NOT OFFICIAL · scientific_verdict: null",
        "built_at": built_at,
        "port": port,
        "serve_note": serve_note,
        "pages": pages_index,
        "runs": runs,
        "not_official": True,
        "scientific_verdict": None,
    }
    json.dump(manifest, open(viewer_dir / "manifest.json", "w"),
              ensure_ascii=False, indent=1)

    # 3) web receipt — input sha256 + counts + serve note
    run_hashes: dict[str, dict] = {}
    agg = {"runs": len(runs), "planes": 0, "points_total": 0, "orphans": 0,
           "cells": 0, "faces": 0, "seeds": 0}
    for r in runs:
        rd = out_root / r["dir"]
        entry = {}
        for fn in page["run_files"]:
            fp = rd / fn
            if fp.is_file():
                entry[fn] = {"sha256": sha256_file(fp), "bytes": fp.stat().st_size}
        run_hashes[r["name"]] = entry
        c = r.get("counts") or {}
        for k in ("planes", "points_total", "orphans", "cells", "faces", "seeds"):
            agg[k] += int(c.get(k) or 0)
    serve_cmd = f"cd {out_root} && python3 -m http.server {port} --bind 0.0.0.0"
    receipt = {
        "schema": "phd_s3_verify_web_receipt_v1",
        "task": f"PHD-S3-VERIFY-PAGES-v1 / {page['dir']} ({page['title']})",
        "built_at": built_at,
        "config_used": str(cfg_path) if cfg_path else "contract-defaults(config 파일 없음)",
        "inputs": inputs,
        "runs": run_hashes,
        "counts": agg,
        "serve_note": serve_note,
        "serve_cmd": serve_cmd,
        "url": f"http://<host>:{port}/{page['dir']}/",
        "not_official": True,
        "scientific_verdict": None,
    }
    json.dump(receipt, open(viewer_dir / "web_receipt_v1.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"viewer built: {viewer_dir}  runs={len(runs)}"
          f" ({', '.join(r['name'] for r in runs) or '없음'})")
    return len(runs), serve_cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                    help="공유 config (기본: configs/phd/s3_verify_v1/s1_bundle_v1.json)")
    args = ap.parse_args()

    cfg, cfg_path = load_config(args.config)
    out_root = resolve_path(cfg["out_root"])
    port = cfg.get("viewer", {}).get("port", 8885)
    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pages_index = [{"page": p["page"], "title": p["title"], "url": f"{p['dir']}/"}
                   for p in PAGES]
    serve_cmd = ""
    for page in PAGES:
        _, serve_cmd = deploy_page(page, out_root, cfg, cfg_path,
                                   built_at, pages_index)
    print(f"serve:  {serve_cmd}")
    for p in PAGES:
        print(f"open:   http://<host>:{port}/{p['dir']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
