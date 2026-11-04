"""Seal config once at completion and package the requested artifacts with hashes."""
from common import *
import zipfile,hashlib
import report,provenance
def main():
    start=time.monotonic();cfg();assert json.loads((D/'tables/verification.json').read_text())['status'].startswith('PASS_')
    assert (D/'figure_review.json').exists(),'Single visual review receipt required'
    final=C/'judgeapply_v1.final.lock.json';assert not final.exists(),'Final lock must be written once'
    provenance.main();report.main()
    configsha=sha(C/'judgeapply_v1.json');dump(final,dict(at=now(),config_sha256=configsha,initial_sha256=json.loads((C/'judgeapply_v1.initial.lock.json').read_text())['config_sha256'],unchanged_since_initial=True,
        scripts={str(p.relative_to(R)):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file()},source_commit=os.environ['JUDGEAPPLY_COMMIT'],scientific_verdict=None))
    # All scientific calculations and the single visual review precede final lock.
    progress('기하·사진·평가·표·한 번 검산·그림과 한 번 육안 확인 완료. 최종 설정 잠금: 초기와 같은 SHA256. 전달 묶음 생성 시작.')
    reportpath=D/'판단적용_보고_v1.md';files=[]
    for root,prefix in [(D,'docs'),(C,'config'),(HERE,'scripts')]:
      for p in sorted(root.rglob('*')):
        if p.is_file() and p!=reportpath and p.name not in ['delivery_receipt.json','PHD-MAIN-JUDGEAPPLY-v1.zip'] and p.suffix!='.zip':files.append((p,prefix+'/'+str(p.relative_to(root))))
    for name in ['core_points','photo_points','training_regions']:
      for p in sorted((O/name).glob('*.npz')):files.append((p,name+'/'+p.name))
    for name in ['calibration.json','input_gate.json','input_inventory.json','ring_reconciliation.json']:
        files.append((O/name,'evidence/'+name))
    for p in sorted((O/'timing').glob('*.json')):files.append((p,'evidence/timing/'+p.name))
    # NPZ files are already compressed. Size-bound splitting is per complete ZIP.
    limit=400_000_000;reserve=2_000_000;groups=[[]];acc=0
    for pair in files:
      size=pair[0].stat().st_size
      assert size<limit-reserve,(pair[0],size)
      if acc+size>limit-reserve and groups[-1]:groups.append([]);acc=0
      groups[-1].append(pair);acc+=size
    folder=O/'delivery';folder.mkdir(exist_ok=True);receipts=[];pack_start=time.monotonic()
    for group_index,group in enumerate(groups):
      name='PHD-MAIN-JUDGEAPPLY-v1'+(f'.part{group_index+1:02d}' if len(groups)>1 else '')+'.zip';dest=folder/name;assert not dest.exists();sums=[]
      with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p,arc in group:
          z.write(p,arc);sums.append((sha(p),arc))
        if group_index==len(groups)-1:
          elapsed=time.monotonic()-pack_start;text=reportpath.read_text().replace('__PACKAGE_SECONDS__',f'{elapsed:.1f}');reportpath.write_text(text)
          assert len(text)<=12000
          z.write(reportpath,'docs/'+reportpath.name);sums.append((sha(reportpath),'docs/'+reportpath.name))
        z.writestr('SHA256SUMS',''.join(f'{h}  {arc}\n' for h,arc in sums))
      assert dest.stat().st_size<=limit,(dest,dest.stat().st_size)
      verify_start=time.monotonic()
      with zipfile.ZipFile(dest) as z:
        names=z.namelist();assert len(names)==len(set(names));assert z.testzip() is None
        for digest,arc in sums:
          h=hashlib.sha256()
          with z.open(arc) as f:
            for block in iter(lambda:f.read(8<<20),b''):h.update(block)
          assert h.hexdigest()==digest,arc
        assert set(names)=={arc for _,arc in sums}|{'SHA256SUMS'}
      receipts.append(dict(file=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),members=len(names),CRC='PASS',internal_SHA256='PASS',verification_seconds=time.monotonic()-verify_start))
    receipt=dict(at=now(),task='PHD-MAIN-JUDGEAPPLY-v1',status='PASS_ZIP_CRC_AND_SHA256',archives=receipts,config_sha256=configsha,report_characters=len(reportpath.read_text()),package_seconds=time.monotonic()-start,scientific_verdict=None)
    dump(D/'delivery_receipt.json',receipt);dump(O/'delivery/delivery_receipt.json',receipt)
    (folder/'SHA256SUMS').write_text(''.join(f'{r["sha256"]}  {Path(r["file"]).name}\n' for r in receipts))
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
