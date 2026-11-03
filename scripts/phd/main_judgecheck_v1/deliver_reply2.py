"""Stage-A light/full archives, each under 400MB, with CRC and SHA-256 verification."""
import json,zipfile,hashlib,os
from preflight import C,D,O,R,Path,sha,dump,now
BASE=O/'r2';LIMIT=370000000;DELIVERY=O/'delivery_reply2'

def make(stem,files):
    DELIVERY.mkdir(parents=True,exist_ok=True)
    parts=[];chunk=[];size=0
    for source,name in files:
        n=source.stat().st_size;assert n<LIMIT,(source,n)
        if chunk and size+n>LIMIT:parts.append(chunk);chunk=[];size=0
        chunk.append((source,name));size+=n
    if chunk:parts.append(chunk)
    records=[]
    for i,part in enumerate(parts,1):
        name=stem+('' if len(parts)==1 else f'_part{i:02d}')+'.zip';dest=DELIVERY/name;hashes={arc:sha(src) for src,arc in part}
        manifest=dict(at=now(),task='PHD-MAIN-JUDGECHECK-v1',stage='A_development',part=i,parts=len(parts),config_sha256=sha(C/'judgecheck_v1.json'),source_base_commit=os.environ.get('JUDGECHECK_COMMIT'),files=hashes,scientific_verdict=None)
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for src,arc in part:z.write(src,arc)
            z.writestr('SHA256SUMS',''.join(f'{h}  {name}\n' for name,h in sorted(hashes.items())))
            z.writestr('ARCHIVE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        assert dest.stat().st_size<400000000
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None
            for name,h in hashes.items():
                digest=hashlib.sha256()
                with z.open(name) as f:
                    for b in iter(lambda:f.read(4<<20),b''):digest.update(b)
                assert digest.hexdigest()==h,name
            assert not any('/photo_inputs/' in v or v.startswith('inputs/') or 'image_cache' in v for v in z.namelist())
        rec=dict(path=str(dest),payload_relative_path=str(dest.relative_to(O)),name=dest.name,bytes=dest.stat().st_size,sha256=sha(dest),members=len(hashes)+2,crc='PASS',member_sha256='PASS');records.append(rec);dest.with_suffix('.zip.sha256').write_text(rec['sha256']+'  '+dest.name+'\n');print('ARCHIVE_VERIFIED',dest.name,rec['bytes'],rec['sha256'],flush=True)
    return records

def main():
    v=json.loads((BASE/'validation/full.json').read_text());assert v['status']=='PASS_INDEPENDENT_STAGE_A_OUTPUTS'
    replay=json.loads((D/'replay_delivery_reply2.json').read_text());assert replay['status']=='PASS_ALL_SECTION_6_7_TABLES_REPLAYED_FROM_DELIVERY_VALUES'
    report=D/'판단검증_보고가_v1.md';assert v['report_sha256']==sha(report);export=json.loads((BASE/'canonical_export.json').read_text())
    readme=D/'전달묶음_읽기.md';readme.write_text('''# PHD-MAIN-JUDGECHECK-v1 단계 가 전달 묶음

개발용 결과만 있다. 학습하지 않았고 확인용 값은 열지 않았다. scientific_verdict: null.

- 보고서와 표는 셈한 값이다. 과학적 결론과 단계 나의 값 잠금은 사용자 회신에 따른다.
- light는 보고서, 표, 그림, 설정, 검증 기록이다. full은 핵심점·사진 점 NPZ와 실행 스크립트도 포함한다.
- NPZ의 NaN은 확인 불가다. 0으로 바꾸지 않는다. 번호표와 배열 축은 data_schema.json에 있다.
- 6~7절 표 30개는 전달용 NPZ만 읽어 다시 계산하고 원본의 반올림 전 값과 모두 비교했다. `replay_delivery_reply2.json`에 결과가 있다. 같은 저장소·Docker 환경에서 `replay_delivery_values_reply2.py <묶음을 푼 폴더>`를 실행하면 표를 재계산한다. 출력은 이 작업의 외부 페이로드 안 `r2/replay_delivery/`에만 쓴다.
- 사진 점의 연결 키는 (구역, 사전 정보, 지붕/벽, 점 번호)다. 지붕과 벽은 같은 점 번호 문자열을 가질 수 있다.
- 핵심점과 사진 점 NPZ로 6~7절 표를 다시 셀 수 있다. 사진 점수, 참값의 자리, 영상 배경과 사진 조각을 원자료부터 다시 구하려면 설정이 가리키는 기존 W/P/WP/JN/TG 원자료와 고정된 Docker 실행 환경이 필요하다. 원본 사진·점군·원래 곡선과 중간 이미지 캐시는 묶음에 넣지 않았다.
- 첫 연결의 공유 곡선 22개와 그때의 준비 데이터는 새 결과에 사용하지 않았다. 초기 준비 데이터는 묶음에 없다.
- 파일마다 SHA256SUMS를 검증했다. ZIP CRC/SHA-256은 파일 무결성 검사이며 과학적 타당성의 결론이 아니다.
- 여러 part 파일이 있으면 모두 같은 폴더에 푼다. 각 part의 SHA256SUMS는 해당 part의 파일만 열거한다.
''')
    light=[(report,report.name),(readme,readme.name)]
    for name in ['판단검증_지붕중간보고_v1.md','data_schema.json','validation_full_reply2.json','validation_roofs_reply2.json','replay_delivery_reply2.json','issues.md','progress.md']:
        p=D/name
        if p.exists():light.append((p,name))
    for p in sorted((D/'tables').glob('*')):
        if p.is_file() and (p.name.startswith(('ALS_1_','LoD2_1_','LoD2_2_','reply2_','photo_threshold_','packed_plane_')) or p.name in ['geometry_calibration_interim.json','reply1_verification.json']):light.append((p,'tables/'+p.name))
    for p in sorted((D/'figures').glob('*')):
        if p.is_file():light.append((p,'figures/'+p.name))
    for p in sorted(C.rglob('*')):
        if p.is_file():light.append((p,'settings/'+str(p.relative_to(C))))
    light_records=make('PHD-MAIN-JUDGECHECK-v1_가_light',light)
    full=list(light)
    for row in export['files']:
        p=Path(row['path']);assert sha(p)==row['sha256'];full.append((p,str(p.relative_to(O))))
    code=R/'scripts/phd/main_judgecheck_v1'
    for p in sorted(code.rglob('*')):
        if p.is_file() and p.suffix in ['.py','.sh','.cpp']:full.append((p,'scripts/'+str(p.relative_to(code))))
    for p in [BASE/'target_census.json',BASE/'timing_estimate.json',BASE/'diagnostics.json',BASE/'audit_inputs.json',O/'r1/resumed_lineage_final_hashes.json']:
        full.append((p,'reproduction/'+p.name))
    for p in sorted((BASE/'resources').rglob('*')):
        if p.is_file() and not p.name.endswith('.tmp'):full.append((p,'reproduction/resources/'+str(p.relative_to(BASE/'resources'))))
    full_records=make('PHD-MAIN-JUDGECHECK-v1_가',full)
    receipt=dict(at=now(),status='PASS_STAGE_A_DELIVERY_INTEGRITY',light=light_records,full=full_records,validation_status=v['status'],
        report_sha256=sha(report),config_sha256=sha(C/'judgecheck_v1.json'),initial_preparation_included=False,holdout_included=False,stop_before_stage_b=True,scientific_verdict=None)
    dump(D/'delivery_reply2_receipt.json',receipt);dump(BASE/'delivery_receipt.json',receipt);print('DELIVERY_COMPLETE',len(light_records),len(full_records),flush=True)
if __name__=='__main__':main()
