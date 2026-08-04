#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.p2.c3_roof_texture_bake_v1.bake import VIEWS, _records, _sheet
from scripts.p2.c3_tsdf_roof_diagnostic_v1.contract import canonical_json_bytes, file_record, resolve_artifact, write_new


REPO_ROOT=Path(__file__).resolve().parents[3]
CONFIG_PATH=REPO_ROOT/"configs/p2/c3_roof_texture_reference_extension_v1/compose_v1.json"


def load_config(path: Path=CONFIG_PATH) -> dict[str,Any]: return json.loads(path.read_text(encoding="utf-8"))


def validate_config(config: Mapping[str,Any]) -> None:
    if config.get("schema")!="jointbuildgs.p2.c3_roof_texture_reference_extension.v1": raise RuntimeError("unexpected schema")
    if config.get("status")!="APPROVED_FOR_LOCAL_EXECUTION": raise RuntimeError("not activated")
    if config["presentation"]["row_count"]!=7 or config["presentation"]["column_count"]!=8: raise RuntimeError("layout drifted")
    if config["presentation"]["c1_4907177_status"]!="SEALED_PRE_LOD2_GROUNDSURFACE_Z_RERUN_RESULT": raise RuntimeError("4907177 C1 boundary drifted")
    if any(int(value)!=0 for value in config["execution_counters"].values()): raise RuntimeError("execution counter drifted")
    if config.get("scientific_verdict","missing") is not None: raise RuntimeError("scientific verdict must be null")


def _copy(source: Path, destination: Path, source_root: Path, output_root: Path) -> tuple[Path,dict[str,Any]]:
    write_new(destination,source.read_bytes()); source_record=file_record(source,source_root); copy_record=file_record(destination,output_root)
    if source_record["sha256"]!=copy_record["sha256"]: raise RuntimeError("copy hash mismatch")
    return destination,{"source":source_record,"copy":copy_record}


def _texture_paths(root: Path, stable_id: str, method: str, mode: str) -> list[Path]:
    return [root/f"qualitative/{stable_id}/panels/{method.lower()}_{mode.lower()}_{condition}_{view.lower()}.png" for condition in ("C3_1_SEM","C3_2_SEM_DEPTH") for view in VIEWS]


def run(output_root: Path, artifact_root: Path, source_commit: str) -> dict[str,Any]:
    config=load_config(); validate_config(config)
    texture_root=resolve_artifact(artifact_root,config["source"]["texture_context_hybrid_relative_root"],"texture source"); c1_root=resolve_artifact(artifact_root,config["source"]["c1_c2_matrix_relative_root"],"C1 source"); lod2_root=resolve_artifact(artifact_root,config["source"]["lod2_context_relative_root"],"LoD2 source")
    cases=[]; lineage=[]
    for stable_id in config["scope"]["building_ids"]:
        rows=[]; copied=[]
        specs=[
            ("2024 RGB + 2022 ROOFLINE\nPROJECTION CONTEXT",[texture_root/f"qualitative/{stable_id}/panels/context_current_rgb_2022_roofline_{view.lower()}.png" for view in VIEWS],texture_root,"context"),
            (("C1 CURRENT UAS LIDAR ROOFER\nSEALED PRE-Z-RERUN" if stable_id=="DEBY_LOD2_4907177" else "C1 CURRENT UAS LIDAR\nROOFER OUTPUT"),[c1_root/f"qualitative/{stable_id}/panels/C1_L_upper__LIDAR_ROOFER_OUTPUT__{view}.png" for view in VIEWS],c1_root,"c1_roofer"),
            ("2022 LOD2 REFERENCE\nEVALUATION CONTEXT",[lod2_root/f"qualitative/roof_first/{stable_id}/panels/lod2_context_{view.lower()}.png" for view in VIEWS],lod2_root,"lod2_reference"),
        ]
        for label,sources,source_root,role in specs:
            paths=[]
            for view,source in zip(VIEWS,sources):
                destination=output_root/f"qualitative/{stable_id}/panels/{role}_{view.lower()}.png"; path,record=_copy(source,destination,source_root,output_root); record.update({"stable_id":stable_id,"role":role,"view":view}); lineage.append(record); copied.append(record["copy"]); paths.append(path)
            rows.append((label,paths+paths))
        for method in config["scope"]["mesh_methods"]:
            for mode in ("TEXTURE","SUPPORT"):
                paths=[]
                for source in _texture_paths(texture_root,stable_id,method,mode):
                    destination=output_root/f"qualitative/{stable_id}/panels/{source.name}"; path,record=_copy(source,destination,texture_root,output_root); record.update({"stable_id":stable_id,"role":f"{method}_{mode}"}); lineage.append(record); copied.append(record["copy"]); paths.append(path)
                rows.append((f"{method}\n{mode}",paths))
        sheet=output_root/f"qualitative/{stable_id}/case_sheet_c1_lod2_texture_v1.png"; _sheet(sheet,stable_id,rows,"current RGB/roofline + sealed C1 + 2022 LoD2 + C3 texture | scientific_verdict=null")
        cases.append({"stable_id":stable_id,"row_count":7,"column_count":8,"visible_cell_count":56,"unique_panel_png_count":len(copied),"case_sheet":file_record(sheet,output_root),"panels":copied})
    counters={"gs_training_invocations":0,"texture_bakes":0,"poisson_reconstructions":0,"tsdf_reconstructions":0,"roofer_invocations":0,"metric_recomputations":0,"c4_c5_accesses":0}
    index={"schema":"jointbuildgs.c3_roof_texture_reference_extension_index.v1","status":"COMPLETE_C1_LOD2_REFERENCE_EXTENSION","source_commit":source_commit,"case_count":3,"visible_cell_count":168,"unique_panel_png_count":132,"lineage":lineage,"cases":cases,"execution_counters":counters,"official_G3_G4_PASS_usable":None,"scientific_verdict":None}; write_new(output_root/"qualitative/index_v1.json",canonical_json_bytes(index))
    report="# C3 texture board C1/LoD2 extension\n\n봉인된 v3 texture 판에 C1 current UAS LiDAR Roofer output과 2022 LoD2 evaluation context를 추가했다. 4907177의 C1은 LoD2 GroundSurface Z 보정 재실행 전 결과다. 모든 행은 exact source panel 재배치이며 reconstruction, Roofer, metric 실행은 0회다.\n"; write_new(output_root/"reports/technical_report_ko_v1.md",report.encode("utf-8")); links="".join(f'<section><h2>{html.escape(case["stable_id"])}</h2><img src="../{case["case_sheet"]["path"]}"></section>' for case in cases); write_new(output_root/"reports/case_index.html",("<!doctype html><meta charset=utf-8><style>img{width:100%}</style><h1>C1/LoD2 reference extension</h1>"+links).encode())
    returned={"schema":"jointbuildgs.c3_roof_texture_reference_extension_return.v1","status":"RETURNED_LOCAL_COMPLETE_C1_LOD2_REFERENCE_EXTENSION","source_commit":source_commit,"generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"case_count":3,"visible_cell_count":168,"unique_panel_png_count":132,"execution_counters":counters,"scientific_verdict":None}; write_new(output_root/"control/technical_return_v1.json",canonical_json_bytes(returned)); manifest={"schema":"jointbuildgs.c3_roof_texture_reference_extension_manifest.v1","status":"COMPLETE_HASHED_MATERIAL_PAYLOAD","source_commit":source_commit,"records":_records(output_root),"scientific_verdict":None}; manifest["record_count"]=len(manifest["records"]); write_new(output_root/"control/artifact_manifest_v1.json",canonical_json_bytes(manifest))
    checks={"case_count_3":len(cases)==3,"visible_cells_168":index["visible_cell_count"]==168,"unique_panels_132":index["unique_panel_png_count"]==132,"source_copy_hashes_match":all(row["source"]["sha256"]==row["copy"]["sha256"] for row in lineage),"prohibited_counters_zero":all(value==0 for value in counters.values()),"scientific_verdict_null":index["scientific_verdict"] is None}; verified={"schema":"jointbuildgs.local_technical_200_verified.v1","status":"200-VERIFIED_LOCAL_SELF_CHECK","checks":checks,"manifest":file_record(output_root/"control/artifact_manifest_v1.json",output_root),"scientific_verdict":None}
    if not all(checks.values()): raise RuntimeError("reference extension verification failed")
    write_new(output_root/"control/200-verified.local_v1.json",canonical_json_bytes(verified)); closed={"schema":"jointbuildgs.local_technical_300_closed.v1","status":"300-CLOSED_LOCAL_C1_LOD2_REFERENCE_EXTENSION","technical_return":file_record(output_root/"control/technical_return_v1.json",output_root),"verified":file_record(output_root/"control/200-verified.local_v1.json",output_root),"manifest":file_record(output_root/"control/artifact_manifest_v1.json",output_root),"scientific_verdict":None}; write_new(output_root/"control/300-closed.local_v1.json",canonical_json_bytes(closed)); return closed


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--output-root",type=Path,required=True); parser.add_argument("--artifact-root",type=Path,required=True); parser.add_argument("--source-commit",required=True); args=parser.parse_args(); print(json.dumps(run(args.output_root,args.artifact_root,args.source_commit),ensure_ascii=False,sort_keys=True))


if __name__=="__main__": main()
