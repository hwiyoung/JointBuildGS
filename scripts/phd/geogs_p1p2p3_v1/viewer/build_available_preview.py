"""Expose closed actual outputs immediately, without altering final evaluation."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from run_evaluation import export_display


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    task, cfg = args.task, read(args.config)
    destination = task / cfg['manifest']
    if destination.exists():
        raise FileExistsError(destination)
    execution = read(task / 'contracts/execution_v1.json')
    seal = read(task / 'contracts/candidates_sealed_v1.json')
    manifest = dict(schema='geogs_p1p2p3_viewer_v1', scientific_verdict=None,
        title='GeoGS 실제 결과 — 현재 완료된 표시 자료',
        notes=['완료된 실제 평가 산출물을 연결한 현재 시점 화면입니다. 최종 분석 완료 선언이 아닙니다.',
               'P3 미완료 표시 자료는 대기로 표시합니다. 모든 조건에 ALS 초기화·anchor 영향이 남습니다.'],
        default_resolution='512', resolution_modes=[
            dict(id='512', label='Anchor·최종 동일512', mesh_res=512, anchor_variant='anchor_512', final_variant='mesh_512'),
            dict(id='1024', label='최종1024 (anchor1024 자원 부족)', mesh_res=1024, anchor_variant='anchor', final_variant='final')],
        regions=[], downloads=[], created_at=datetime.now(timezone.utc).isoformat(),
        candidate_seal_sha256=sha(task/'contracts/candidates_sealed_v1.json'),
        preview_config_sha256=sha(args.config), preview_script_sha256=sha(Path(__file__)))
    for region, spec in execution['regions'].items():
        geometry, viewer = task/'evaluation/geometry'/region, task/'evaluation/viewer'/region
        index_path = geometry/'viewer_index.json'
        index = read(index_path) if index_path.exists() else None
        view = dict(id=region, label=region, bounds=dict(min=[spec['domain'][a][0] for a in 'xyz'],
            max=[spec['domain'][a][1] for a in 'xyz']), frame='EPSG:25832 local meters',
            notes=['실제 닫힌 산출물의 표시. 참조 없는 위치를 오류로 단정하지 않습니다.'],
            candidates=[], conditions=[], sections=[], renders=[], cases=[],
            panel_candidates=dict(prior='prior_mesh', mvs='mvs_points', anchor='D005_Pnative.anchor_512.raw',
                                  vanilla='D005_Pnative.final.raw', reference='reference'))
        if index:
            rows = index['candidates']
            ref_url, ref_meta = region+'/reference.json', index['reference_display_metadata']
        else:
            rows=[]
            for receipt_path in sorted(geometry.glob('*/run_receipt.json')):
                if read(receipt_path).get('status') != 'EVALUATED':
                    continue
                name=receipt_path.parent.name
                data_path=viewer/(name+'.json')
                data=read(data_path)
                meta={k:v for k,v in data.items() if k not in ('xyz','rgb','distance_m')}
                role=('prior' if name in ('prior_mesh','als_points') else 'mvs' if name=='mvs_points'
                      else 'anchor' if '.anchor_' in name else 'vanilla' if name.startswith('D005_Pnative.') else 'changed')
                mesh_path=viewer/(name+'.mesh.json')
                mesh=read(mesh_path) if mesh_path.exists() else None
                rows.append(dict(id=name, role=role, data_url=data_path.name, surface_kind=data['surface_kind'],
                    display_metadata=meta, source_path=data['source_path'],
                    metrics_relative=str((receipt_path.parent/'sample0.1_reference0.1.json').relative_to(task)),
                    section_url=name+'.sections.png', distance_url=name+'.distance.png',
                    mesh_data=dict(format='json',url=region+'/'+mesh_path.name) if mesh else None,
                    original_mesh=mesh.get('source_mesh') if mesh else None))
            reference_source=geometry/'prior_mesh/sample0.1_reference0.1.npz'
            assert read(reference_source.parent/'run_receipt.json')['status']=='EVALUATED'
            with np.load(reference_source) as arrays:
                reference=arrays['reference_points']
            reference_path=viewer/'reference_preview_v1.json'
            reference_metrics=read(reference_source.with_suffix('.json'))
            ref_meta=export_display(reference_path, dict(prediction_surface_samples=reference,
                prediction_to_reference_distance=np.full(len(reference),np.nan)), [232,235,239],
                'observed_UAS_reference_points', str(reference_source.relative_to(task)),
                evaluation_metadata=dict(reference_voxel_size_m=.1,
                    original_points_in_roi=reference_metrics.get('reference_points_in_roi')))
            ref_url=region+'/'+reference_path.name
            view['reference_preview_source']=dict(path=str(reference_source.relative_to(task)),sha256=sha(reference_source))
        for row in rows:
            name=row['id']
            view['candidates'].append(dict(id=name,label=name,status='available',role=row['role'],
                data=dict(url=region+'/'+row['data_url'],format='json'),surface_kind=row['surface_kind'],
                mesh_data=row.get('mesh_data'),display_metadata=row['display_metadata'],
                provenance=dict(source_path=row['source_path'],full_evaluation=row['metrics_relative'],
                    display=row['display_metadata'],original_mesh=row.get('original_mesh')),
                downloads=[dict(label='실제 평가 JSON',url='/task/'+row['metrics_relative'])]))
            condition=name.split('.')[0] if name.startswith('D') else None
            for key,label in [('section_url','고정 단면'),('distance_url','참조 거리 지도')]:
                view['sections'].append(dict(id=name+'.'+key,label=name+' '+label,url=region+'/'+row[key],
                    condition_id=condition,selection_reason='고정 지역 단면·전체 범위',
                    caption='같은 범위·폭 .5m. 관측 UAS와의 거리이며 참조 부재는 오류 정답이 아닙니다.'))
        view['candidates'].append(dict(id='reference',label='현재 UAS',role='reference',status='available',
            data=dict(url=ref_url,format='json'),surface_kind='original_observed_reference_points',
            display_metadata=ref_meta,provenance=dict(evaluation_only=True,display=ref_meta)))
        for unavailable in seal['extraction_inventory']:
            if unavailable['region']==region and unavailable['variant']=='anchor' and unavailable['status']=='TECHNICAL_RESOURCE_UNAVAILABLE':
                for kind in ('raw','post'):
                    view['candidates'].append(dict(id=unavailable['condition']+'.anchor.'+kind,
                        label='Anchor1024 자원 부족',status='technical_resource_unavailable',role='anchor',
                        reason='확인된 메모리 부족. 같은512 비교를 선택할 수 있습니다.'))
        for condition in execution['conditions']:
            cid=condition['id']
            view['conditions'].append(dict(id=cid,label=cid,candidate_id=cid+'.final.raw'))
            for receipt_path in sorted((task/'evaluation/renders'/region/cid).glob('*/receipt.json')):
                receipt=read(receipt_path)
                if receipt.get('status')!='PASS_RENDER_QUALITY_EVALUATION':
                    continue
                for row in receipt['rows']:
                    if row['status']=='ASSESSED':
                        view['renders'].append(dict(id=cid+'.'+receipt_path.parent.name+'.'+str(row['evaluation_index'])+'.'+row['domain'],
                            label=cid+' '+receipt_path.parent.name+' '+row['name']+' '+row['domain'],
                            url='/task/'+str((receipt_path.parent/row['montage']).relative_to(task)),
                            condition_id=cid,image_name=row['name'],domain=row['domain'],stage=receipt_path.parent.name,
                            caption='실제 평가 사진 / 저장 GeoGS 렌더 / RGB 오차',split='evaluation',
                            selection_reason='모든 완료된 평가 사진 포함'))
        view['notes'].append('지역 기하 평가 완료' if index else '지역 기하 평가 진행 중: 닫힌 표면만 표시')
        manifest['regions'].append(view)
    with destination.open('x') as stream:
        json.dump(manifest,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(status='ACTUAL_AVAILABLE_PREVIEW_READY',manifest=str(destination),
        sha256=sha(destination),scientific_verdict=None,
        regions=[dict(id=r['id'],candidates=len(r['candidates']),renders=len(r['renders'])) for r in manifest['regions']])))


if __name__=='__main__':
    main()
