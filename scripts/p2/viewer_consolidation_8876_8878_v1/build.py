#!/usr/bin/env python3
"""Consolidate the live 8876/8878 viewer roles and add ring-ground E3/E4 variants."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import laspy
import numpy as np
import yaml


REPO = Path("/workspace/JointBuildGS")
AR = Path("/artifacts/JointBuildGS")
CONFIG = REPO / "configs/p2/viewer_consolidation_8876_8878_v1/viewer.yaml"
SOURCE = REPO / "scripts/p2/viewer_consolidation_8876_8878_v1/build.py"
TASK = AR / "phase-payloads/p2/viewer_consolidation_8876_8878_v1/P2-VIEWER-CONSOLIDATION-8876-8878-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(body, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded)
    os.replace(temporary, path)


def cityjson_to_obj(source: Path, output: Path, shift: np.ndarray) -> dict:
    docs = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    transform = docs[0]["transform"]
    vertices = np.asarray(docs[1]["vertices"], dtype=np.float64)
    vertices = vertices * np.asarray(transform["scale"], dtype=np.float64) + np.asarray(transform["translate"], dtype=np.float64)
    lines = ["# Ring-ground Roofer CityJSONSeq display adapter"]
    vertex_count = triangle_count = 0
    for city_object in docs[1]["CityObjects"].values():
        for geometry in city_object.get("geometry", []):
            if geometry.get("type") != "Solid":
                continue
            for shell in geometry.get("boundaries", []):
                for surface in shell:
                    if not surface or len(surface[0]) < 3:
                        continue
                    ring = np.asarray(surface[0], dtype=np.int64)
                    local = vertices[ring] - shift
                    start = vertex_count + 1
                    lines.extend(f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in local)
                    for index in range(1, len(local) - 1):
                        lines.append(f"f {start} {start + index} {start + index + 1}")
                        triangle_count += 1
                    vertex_count += len(local)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return {"vertices": vertex_count, "triangles": triangle_count, "bytes": output.stat().st_size, "sha256": sha256(output)}


def laz_to_assets(source: Path, prefix: Path, shift: np.ndarray) -> dict:
    cloud = laspy.read(source)
    xyz = np.column_stack((np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z))).astype(np.float64) - shift
    classes = np.asarray(cloud.classification, dtype=np.uint8)
    records = {}
    for name, code in (("ground", 2), ("building", 6)):
        output = prefix.with_name(prefix.name + f"_roofer_{name}_xyz_f32.bin")
        points = np.ascontiguousarray(xyz[classes == code], dtype="<f4")
        output.write_bytes(points.tobytes())
        records[name] = {"count": int(len(points)), "bytes": output.stat().st_size, "sha256": sha256(output), "path": output}
    return records


def variant(cfg: dict, viewer: Path, key: str, shift: np.ndarray) -> tuple[dict, dict]:
    item = cfg[key]
    case = AR / item["case_root"]
    city = next((case / "roofer/output").glob("*.city.jsonl"))
    classified = AR / item["classified_laz"]
    prefix = viewer / "assets" / item["variant_id"]
    obj = prefix.with_suffix(".obj")
    mesh_record = cityjson_to_obj(city, obj, shift)
    point_records = laz_to_assets(classified, prefix, shift)
    value = {
        "id": item["variant_id"], "label": item["label"], "type": "mesh",
        "asset": f"assets/{obj.name}", "color": "#9ca3af" if key == "e3" else "#f59e0b",
        "condition": item["variant_id"], "step": 20000,
        "roofer_pointcloud": {"assets": {name: f"assets/{record['path'].name}" for name, record in point_records.items()}},
        "ring_ground": True, "scientific_verdict": None,
    }
    return value, {
        "cityjson": {"path": item["case_root"] + "/roofer/output/690897_5336168.city.jsonl", "sha256": sha256(city)},
        "classified_laz": {"path": item["classified_laz"], "sha256": sha256(classified)},
        "obj": mesh_record,
        "pointcloud": {name: {key: val for key, val in record.items() if key != "path"} for name, record in point_records.items()},
    }


def update_manifest(viewer: Path, e3: dict, e4: dict) -> None:
    path = viewer / "viewer_manifest.json"
    manifest = json.loads(path.read_text())
    e3_panel = next(panel for panel in manifest["panels"] if str(panel.get("condition", "")).startswith("E3"))
    e4_panel = next(panel for panel in manifest["panels"] if panel.get("condition") == "E4")
    for panel, value in ((e3_panel, e3), (e4_panel, e4)):
        variants = panel.setdefault("variants", [])
        existing = next((index for index, row in enumerate(variants) if row.get("id") == value["id"]), None)
        if existing is None:
            variants.append(value)
        else:
            variants[existing] = value
    manifest["viewer_roles"] = {"8876": "integrated comparison", "8878": "detailed diagnostics"}
    manifest["ring_ground_variants"] = [e3["id"], e4["id"]]
    manifest["scientific_verdict"] = None
    atomic_json(path, manifest)


def update_8876_html(viewer: Path) -> None:
    path = viewer / "index.html"
    text = path.read_text()
    start = text.index("<style>")
    end = text.index("</style>", start) + len("</style>")
    style = """<style>
html,body{margin:0;height:100%;width:100%;background:#080b10;color:#eef2f7;font:13px system-ui,sans-serif}*{box-sizing:border-box}body{overflow:hidden}#app{height:100dvh;width:100%;min-width:0;display:grid;grid-template-rows:auto minmax(0,1fr)}header{width:100%;min-width:0;padding:8px 12px;background:#111722;border-bottom:1px solid #303a48;display:flex;flex-wrap:wrap;gap:7px 9px;align-items:center;max-height:38vh;overflow:auto}button,select,.navlink{border:1px solid #526174;border-radius:4px;background:#1c2634;color:#eef2f7;padding:5px 8px;cursor:pointer;text-decoration:none;white-space:nowrap;flex:none}button:hover,.navlink:hover{background:#2a394d}label,strong{display:flex;gap:5px;align-items:center;flex:none;white-space:nowrap}#info{color:#9fb0c4;min-width:180px;flex:1}.hint{color:#aebdce}.legend{display:flex;gap:7px;color:#c7d2df;flex-wrap:wrap;flex:none}.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px}.grid{min-width:0;min-height:0;overflow:auto;display:grid;grid-template-columns:repeat(4,minmax(260px,1fr));grid-template-rows:repeat(2,minmax(240px,1fr));gap:2px;background:#000}.panel{position:relative;min-width:0;min-height:0;background:#05070a}.label{position:absolute;z-index:3;top:6px;left:6px;right:6px;padding:4px 7px;border-radius:4px;background:#000b;white-space:normal}.view{position:absolute;inset:0}.view canvas{width:100%;height:100%;display:block}
@media(max-width:1400px),(max-height:720px){.grid{grid-template-columns:repeat(2,minmax(300px,1fr));grid-template-rows:none;grid-auto-rows:minmax(280px,45vh)}header{max-height:42vh}.hint{display:none}}
@media(max-width:720px){body{overflow:auto}#app{height:auto;min-height:100dvh;display:block}header{position:sticky;top:0;z-index:10;max-height:45vh;overflow-x:hidden;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}header>*{min-width:0;max-width:100%}header strong,#info,.navlink{grid-column:1/-1}header button,header label{width:100%;overflow:hidden}label select{flex:1;min-width:0;max-width:100%}.grid{grid-template-columns:1fr;grid-auto-rows:minmax(300px,52vh)}.legend,.hint{display:none}}
@media(max-width:600px){header{grid-template-columns:1fr}header>*{grid-column:1}header button,header label{overflow:visible}}
</style>"""
    text = text[:start] + style + text[end:]
    if 'id="e4VariantWrap"' not in text:
        text = text.replace('<label id="e3VariantWrap" hidden>E3 checkpoint <select id="e3Variant"></select></label>', '<label id="e3VariantWrap" hidden>E3 <select id="e3Variant"></select></label><label id="e4VariantWrap" hidden>E4 <select id="e4Variant"></select></label>')
    if 'id="showRingGround"' not in text:
        text = text.replace('<button id="focus4906982" type="button">4906982 보기</button>', '<button id="focus4906982" type="button">4906982 보기</button><button id="showRingGround" type="button">E3/E4 ring-ground 보기</button>')
    if 'id="toggleRooferWireframe"' not in text:
        text = text.replace(
            '<button id="toggleRooferMeshes" type="button">Roofer ON</button>',
            '<button id="toggleRooferMeshes" type="button">Roofer ON</button><button id="toggleRooferWireframe" type="button">Roofer solid</button>',
        )
    if 'href="http://localhost:8878/catalog.html"' not in text:
        text = text.replace('<span id="info">불러오는 중</span>', '<a class="navlink" href="http://localhost:8878/catalog.html" target="_blank">8878 상세 진단</a><span id="info">불러오는 중</span>')
    text = text.replace('<span>좌: 회전 · 우/Shift: 이동 · wheel: 확대 · click: 상세</span>', '<span class="hint">좌: 회전 · 우/Shift: 이동 · wheel: 확대 · click: 상세</span>')
    text = text.replace('app.js?v=e1e6-20260807o', 'app.js?v=e1e6-20260810-ring-ground-v1')
    text = text.replace('app.js?v=e1e6-20260810-ring-ground-v1', 'app.js?v=e1e6-20260810-wireframe-v1')
    path.write_text(text)


def update_8876_app(viewer: Path) -> None:
    path = viewer / "app.js"
    text = path.read_text()
    if "const initialE4Variant" not in text:
        text = text.replace("const initialE3Variant = initialParameters.get('e3');", "const initialE3Variant = initialParameters.get('e3');\nconst initialE4Variant = initialParameters.get('e4');")
    if "const minOrbitDistance" not in text:
        text = text.replace(
            "const initialE4Variant = initialParameters.get('e4');",
            "const initialE4Variant = initialParameters.get('e4');\nconst minOrbitDistance = 0.75;\nconst maxOrbitDistance = 2000;",
        )
    if "let rooferWireframeVisible" not in text:
        text = text.replace(
            "let rooferMeshesVisible = initialMode !== 'surface';",
            "let rooferMeshesVisible = initialMode !== 'surface';\nlet rooferWireframeVisible = initialMode === 'wire';",
        )
    if "function setRooferWireframe" not in text:
        marker = "async function panelObject(spec) {"
        helper = r'''function setRooferWireframe(object, enabled) {
  object.traverse(child => {
    if (!child.isMesh) return;
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    for (const material of materials) {
      material.wireframe = enabled;
      material.needsUpdate = true;
    }
  });
}

'''
        text = text.replace(marker, helper + marker)
    if "setRooferWireframe(object, rooferWireframeVisible);" not in text:
        text = text.replace(
            "  let object = await panelObject(spec);\n  object.visible = rooferMeshesVisible;",
            "  let object = await panelObject(spec);\n  setRooferWireframe(object, rooferWireframeVisible);\n  object.visible = rooferMeshesVisible;",
        )
    if "setRooferWireframe(variantObject, rooferWireframeVisible);" not in text:
        text = text.replace(
            "    const variantObject = await panelObject(variant);\n    const variantEvidence",
            "    const variantObject = await panelObject(variant);\n    setRooferWireframe(variantObject, rooferWireframeVisible);\n    const variantEvidence",
        )
    text = text.replace(
        "orbit.distance = Math.max(8, Math.min(2000, orbit.distance * Math.exp(event.deltaY * 0.001)));",
        "orbit.distance = Math.max(minOrbitDistance, Math.min(maxOrbitDistance, orbit.distance * Math.exp(event.deltaY * 0.001)));",
    )
    if "toggleRooferWireframe').addEventListener" not in text:
        marker = "document.getElementById('toggleRooferMeshes').textContent = `Roofer ${rooferMeshesVisible ? 'ON' : 'OFF'}`;"
        handler = r'''document.getElementById('toggleRooferWireframe').addEventListener('click', event => {
  rooferWireframeVisible = !rooferWireframeVisible;
  for (const viewer of viewers) {
    for (const state of viewer.variantStates.values()) {
      setRooferWireframe(state.object, rooferWireframeVisible);
    }
  }
  event.currentTarget.textContent = `Roofer ${rooferWireframeVisible ? 'wire' : 'solid'}`;
  info.textContent = rooferWireframeVisible
    ? 'Roofer LoD mesh 삼각형 wireframe 표시'
    : 'Roofer LoD mesh solid 표시';
});
document.getElementById('toggleRooferWireframe').textContent = `Roofer ${rooferWireframeVisible ? 'wire' : 'solid'}`;
'''
        text = text.replace(marker, handler + marker)
    if "async function configureVariantSelector" not in text:
        start = text.index("const e3Viewer = viewers.find")
        end = text.index("\nfunction frame()", start)
        replacement = r'''async function configureVariantSelector(requiredVariant, wrapId, selectId, initialId) {
  const viewer = viewers.find(candidate => candidate.variantStates.has(requiredVariant));
  if (!viewer) return null;
  const wrap = document.getElementById(wrapId);
  const select = document.getElementById(selectId);
  select.innerHTML = [...viewer.variantStates.entries()]
    .map(([id, state]) => `<option value="${id}"${id === viewer.spec.id ? ' selected' : ''}>${state.spec.label}</option>`)
    .join('');
  select.addEventListener('change', () => viewer.setVariant(select.value));
  wrap.hidden = false;
  if (initialId && viewer.variantStates.has(initialId)) {
    select.value = initialId;
    await viewer.setVariant(initialId);
  }
  return {viewer, select};
}

const e3Control = await configureVariantSelector('RING_MVS_NORMAL_CONFIDENCE_20K', 'e3VariantWrap', 'e3Variant', initialE3Variant);
const e4Control = await configureVariantSelector('RING_ALS_DEPTH_NORMAL_20K', 'e4VariantWrap', 'e4Variant', initialE4Variant);
document.getElementById('showRingGround').addEventListener('click', async () => {
  if (e3Control) {
    e3Control.select.value = 'RING_MVS_NORMAL_CONFIDENCE_20K';
    await e3Control.viewer.setVariant(e3Control.select.value);
  }
  if (e4Control) {
    e4Control.select.value = 'RING_ALS_DEPTH_NORMAL_20K';
    await e4Control.viewer.setVariant(e4Control.select.value);
  }
  focusBuilding('DEBY_LOD2_4906982');
  info.textContent = 'E3 MVS confidence-normal + E4 ALS depth-normal · exterior-ring ground Roofer 20k';
});
'''
        text = text[:start] + replacement + text[end:]
    path.write_text(text)


def update_8878_catalog(viewer: Path) -> None:
    slots = [
        ("현재", "e3-ring-ground-roofer-v1/index.html", "Ring-ground Roofer · E3/E4 최종 Stage-3 비교"),
        ("현재", "e3-fused-dn-common-support-v1/index.html", "Fused depth/normal common-support ablation"),
        ("보조", "e3-fused-normal-confidence-v1/index.html", "MVS normal confidence-mask 결과"),
        ("보조", "e4-normal-ablation-roofer-v1/index.html", "ALS depth-only vs depth+normal"),
        ("과거", "e3-fused-surface-normal-v1/index.html", "초기 fused surface-normal 진단"),
        ("과거", "e3-mvs-normal-ablation-v1/index.html", "Raw MVS normal 진단"),
    ]
    rows = "".join(f"<li class='{role}'><span>{role}</span><a href='{href}'>{label}</a></li>" for role, href, label in slots)
    page = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>JointBuildGS 상세 진단</title><style>body{{font:15px system-ui;background:#071018;color:#e8f0f4;max-width:920px;margin:32px auto;padding:0 18px}}a{{color:#7dd3fc}}nav{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px}}nav a{{padding:7px 10px;border:1px solid #456;border-radius:6px;text-decoration:none}}ul{{list-style:none;padding:0}}li{{display:grid;grid-template-columns:54px 1fr;gap:12px;padding:12px;border-bottom:1px solid #29404f}}li span{{color:#a9bdc8}}.과거{{opacity:.68}}p{{color:#b8c8d0;line-height:1.6}}</style></head><body><h1>8878 · E3/E4 상세 진단</h1><nav><a href='http://localhost:8876/'>8876 통합 비교</a><a href='./'>기본 입력 검토</a></nav><p>페이지는 별도 서버가 아니라 이 8878 서버 아래의 보존된 진단 슬롯입니다. 현재 결과를 위에 두고 이전 단일변수 진단은 과거 항목으로 유지합니다.</p><ul>{rows}</ul><p>scientific_verdict=null</p></body></html>"""
    (viewer / "catalog.html").write_text(page)
    index = viewer / "index.html"
    text = index.read_text()
    if 'href="catalog.html"' not in text:
        text = text.replace("<body>", "<body><a href=\"catalog.html\" style=\"position:fixed;z-index:20;right:12px;top:10px;background:#17324d;color:white;padding:7px 10px;border-radius:6px;text-decoration:none\">진단 목록</a>")
    index.write_text(text)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text())
    viewer76 = AR / cfg["viewer_8876"]["root"]
    viewer78 = AR / cfg["viewer_8878"]["root"]
    TASK.mkdir(parents=True, exist_ok=True)
    protected78 = [viewer78 / "app.js", viewer78 / "viewer_manifest.json", viewer78 / "mvs_depth_viewer_receipt.json"]
    before = {
        "8876": {name: sha256(viewer76 / name) for name in ("index.html", "app.js", "viewer_manifest.json")},
        "8878": {path.name: sha256(path) for path in protected78},
    }
    shift = np.asarray(cfg["world_shift_epsg25832"], dtype=np.float64)
    e3, e3_record = variant(cfg, viewer76, "e3", shift)
    e4, e4_record = variant(cfg, viewer76, "e4", shift)
    update_manifest(viewer76, e3, e4)
    update_8876_html(viewer76)
    update_8876_app(viewer76)
    update_8878_catalog(viewer78)
    after = {
        "8876": {name: sha256(viewer76 / name) for name in ("index.html", "app.js", "viewer_manifest.json")},
        "8878": {path.name: sha256(path) for path in protected78},
    }
    if before["8878"] != after["8878"]:
        raise RuntimeError("8878 mvs-seed-color-v3 application state changed")
    receipt = {
        "schema": "jointbuildgs.p2.viewer_consolidation_8876_8878_v1.receipt.v1",
        "task_id": cfg["task_id"], "completed_utc": datetime.now(timezone.utc).isoformat(),
        "viewer_roles": {"8876": cfg["viewer_8876"]["role"], "8878": cfg["viewer_8878"]["role"]},
        "before": before, "after": after, "variants": {"e3": e3_record, "e4": e4_record},
        "viewer_8878_slots_deleted": 0, "viewer_containers_created_or_removed": 0,
        "mvs_seed_color_v3_state_unchanged": True,
        "viewer_8876_interaction": {
            "orbit_distance_local_m": {"minimum": 0.75, "maximum": 2000},
            "roofer_mesh_display_modes": ["solid", "wireframe"],
        },
        "source_sha256": {str(CONFIG.relative_to(REPO)): sha256(CONFIG), str(SOURCE.relative_to(REPO)): sha256(SOURCE)},
        "scientific_verdict": None,
    }
    atomic_json(TASK / "receipt.json", receipt)
    atomic_json(TASK / "viewer_inventory.json", {
        "running_viewers": [{"port": 8876, "role": cfg["viewer_8876"]["role"]}, {"port": 8878, "role": cfg["viewer_8878"]["role"]}],
        "non_viewer_service": {"port": 6006, "role": "TensorBoard"},
        "viewer_8878_slots": [{"role": role, "path": href} for role, href, _ in [("current", "e3-ring-ground-roofer-v1/index.html", ""), ("current", "e3-fused-dn-common-support-v1/index.html", ""), ("support", "e3-fused-normal-confidence-v1/index.html", ""), ("support", "e4-normal-ablation-roofer-v1/index.html", ""), ("historical", "e3-fused-surface-normal-v1/index.html", ""), ("historical", "e3-mvs-normal-ablation-v1/index.html", "")]],
        "deletion_action": "NONE_EVIDENCE_PRESERVED", "scientific_verdict": None,
    })
    (TASK / "NOTES.md").write_text("# Viewer consolidation\n\n- 8876 is the integrated E1-E6 comparison and now contains selectable ring-ground E3/E4 20k variants.\n- 8878 remains the detailed E3/E4 diagnostic server; its slots are catalogued as current, supporting, or historical.\n- No viewer slot, source artifact, or container was deleted. The existing mvs-seed-color-v3 app state is unchanged.\n- Responsive 8876 layout wraps the toolbar and scrolls 2-column/1-column panel grids on smaller viewports.\n- The synchronized orbit camera minimum distance is 0.75 local metres (previously 8), and Roofer outputs can switch between solid and triangle-wireframe display.\n- scientific_verdict=null.\n")
    captures = TASK / "responsive_captures"
    if captures.is_dir():
        atomic_json(TASK / "responsive_verification.json", {
            "viewports": {
                path.stem.removeprefix("viewport_"): {"path": str(path.relative_to(TASK)), "sha256": sha256(path)}
                for path in sorted(captures.glob("viewport_*.png"))
            },
            "layout_checks": ["toolbar wraps", "controls do not shrink", "two-column scroll grid", "single-column narrow grid"],
            "headless_webgl_available": False,
            "headless_webgl_limitation": "Docker Chromium screenshots validate DOM/CSS layout; the live host browser validates WebGL.",
            "scientific_verdict": None,
        })
    print(json.dumps({"status": "COMPLETE", "e3_variant": e3["id"], "e4_variant": e4["id"], "receipt": str(TASK / "receipt.json"), "scientific_verdict": None}, indent=2))


if __name__ == "__main__":
    main()
