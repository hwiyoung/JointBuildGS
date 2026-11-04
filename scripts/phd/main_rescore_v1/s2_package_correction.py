"""Fix a report interpolation typo and seal a revised package, reusing passed checks."""
from common import *
import zipfile

previous=json.loads((D/'delivery.json').read_text())
assert previous['status']=='PASS_STAGE2'
report=D/'단계2_보고.md';text=report.read_text()
initial=json.loads((C/'addendum3_stage2.initial.lock.json').read_text())
validation=json.loads((D/'validation.json').read_text())
elapsed=(dt.datetime.fromisoformat(validation['at'])-dt.datetime.fromisoformat(initial['at'])).total_seconds()
assert text.count('{elapsed/60:.1f}')==1
report.write_text(text.replace('{elapsed/60:.1f}',f'{elapsed/60:.1f}'))
progress('최종 문서 확인에서 경과 시간의 미치환 문자열 1곳을 발견해 471.6분으로 수정. 통과한 검증과 메시·점수·그림은 재실행하지 않고 수정 전달 묶음만 별도 봉인.')
with (D/'issues.md').open('a') as f:
    f.write('- 최종 보고서의 경과 시간 미치환 문자열 1곳 수정; 검증 시각과 초기 잠금 시각의 차이 471.6분. 메시·점수·그림·검증 재실행 없음. 최초 최종 ZIP 보존, 수정 전달 ZIP 별도 생성.\n')
correction=dict(at=now(),reason='elapsed-time string interpolation; no numerical result changes',previous_delivery=previous,validation_reused_sha256=sha(D/'validation.json'),scientific_verdict=None)
dump(D/'package_correction.json',correction)
original=json.loads((C/'addendum3_stage2.final.lock.json').read_text())
scripts={p:sha(p) for p in original['scripts']}
scripts[str(Path(__file__))]=sha(__file__)
dump(C/'addendum3_stage2.packaging.lock.json',dict(at=now(),previous_final_lock_sha256=sha(C/'addendum3_stage2.final.lock.json'),scripts=scripts,correction_sha256=sha(D/'package_correction.json'),scientific_verdict=None))
info=json.loads((O/'package_manifest.json').read_text())['files']
package={}
for name in info:
    if name.startswith('docs/'):p=Path('/docs')/name.removeprefix('docs/')
    elif name.startswith('configs/'):p=C/name.removeprefix('configs/')
    elif name.startswith('scripts/'):p=R/'scripts/phd/main_rescore_v1'/name.removeprefix('scripts/')
    elif name.startswith('receipts/scores/'):p=O/'scores'/Path(name).stem/'values.json'
    elif name.startswith('receipts/meshes/'):p=O/'meshes'/Path(name).stem/'primary.json'
    elif name.startswith('receipts/ch6_impl_check/'):p=Path('/out/ch6_impl_check')/Path(name).name
    else:p=O/name
    assert p.is_file(), (name,str(p))
    package[name]=p
package['scripts/'+Path(__file__).name]=Path(__file__)
package['configs/addendum3_stage2.packaging.lock.json']=C/'addendum3_stage2.packaging.lock.json'
package['docs/addendum3_stage2/package_correction.json']=D/'package_correction.json'
info={n:dict(sha256=sha(p),bytes=p.stat().st_size) for n,p in package.items()}
dump(O/'package_manifest_final.json',dict(files=info,large_meshes_included=False,scientific_verdict=None))
package['package_manifest.json']=O/'package_manifest_final.json'
out=O/'PHD-MAIN-RESCORE-v1-addendum3-stage2-final.zip';assert not out.exists()
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for n,p in sorted(package.items()):z.write(p,n)
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    for n,r in info.items():assert hashlib.sha256(z.read(n)).hexdigest()==r['sha256']
delivery=dict(at=now(),status=validation['status'],archive=str(out),archive_sha256=sha(out),archive_bytes=out.stat().st_size,members=len(package),CRC='PASS',all_member_sha256='PASS',unavailable_models=0,scientific_verdict=None)
dump(O/'delivery_final.json',delivery);dump(D/'delivery.json',delivery)
print(json.dumps(delivery,ensure_ascii=False),flush=True)
