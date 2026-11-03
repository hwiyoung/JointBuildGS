from common import *
rows=[]
for site in cfg()['sites']:
    score=json.loads((O/'photo_scores'/site/'complete.json').read_text())
    assert score['height_sweep'] is False and score['trimmed_only'] and score['raw_jpeg']
    assert score['numeric_precision']=='float64 projection interpolation NCC'
    row=dict(site=site,points=score['points'],seconds=score['total_seconds'],read_seconds=score['decode_seconds'],image_decodes=score['original_image_decodes'],files={})
    for prior in cfg()['priors']:
        p=O/'photo_points'/f'{site}__{prior}.npz';row['files'][str(p)]=sha(p)
    rows.append(row)
dump(D/'tables/photo_stage.json',dict(at=now(),rows=rows,points=sum(x['points'] for x in rows),gpu_wait_seconds=0,scientific_verdict=None))
progress('세 지역 최종 사진 점수·판정 파일 완료: 88,343 사진 점. 원본 JPEG 지역별 1회 디코딩, float64 GPU, 단일 높이·자른 조각만. 사진 단계 커밋 준비. photo_receipt 추가; 실행 중인 다른 파일 변경 없음.')
