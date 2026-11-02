"""Immutable requested diagnosis ZIP, per-member SHA and CRC verification."""
import zipfile,hashlib
from common import *
ROOT=OUT/'r8_lod2_cause'
def main():
    assert json.loads((ROOT/'verification.json').read_text())['status']=='PASS'
    members={}
    def add(path,name):
        assert name not in members;members[name]=Path(path)
    add(DOC/'원인점검_r8_LoD2.md','report/원인점검_r8_LoD2.md')
    for p in (DOC/'cause_r8_lod2').rglob('*'):
        if p.is_file():add(p,'report/cause_r8_lod2/'+str(p.relative_to(DOC/'cause_r8_lod2')))
    for p in CFG.glob('cause_r8*'):
        if p.is_file():add(p,'configs/'+p.name)
    for p in Path(__file__).parent.glob('cause_r8_*.py'):add(p,'scripts/'+p.name)
    for name in ['common.py','run_cpu.sh']:add(Path(__file__).with_name(name),'scripts/'+name)
    for p in (ROOT/'rasterizer_source').rglob('*'):
        if p.is_file():add(p,'rasterizer_source/'+str(p.relative_to(ROOT/'rasterizer_source')))
    for p in (ROOT/'commands').glob('*/*'):
        if p.is_file():add(p,'execution/'+str(p.relative_to(ROOT/'commands')))
    for p in (ROOT/'attempts').rglob('*'):
        if p.is_file():add(p,'attempts/'+str(p.relative_to(ROOT/'attempts')))
    for p in (ROOT/'renders').glob('*/summary.json'):add(p,'render_receipts/'+p.parent.name+'.json')
    for p in (ROOT/'states').glob('*/inventory.json'):add(p,'state_receipts/'+p.parent.name+'.json')
    for p in (OUT/'logs').glob('cause-r8-*.log'):add(p,'cpu_execution/'+p.name)
    add(ROOT/'verification_environment.json','receipts/verification_environment.json')
    for name in ['verification.json','memory.json','summary.json','boundaries.json']:add(ROOT/name,'receipts/'+name)
    external={}
    for name in ['cause_r8_lod2.lock.r2.json','cause_r8_spatial.lock.r1.json']:
        for p,h in json.loads((CFG/name).read_text())['files'].items():
            if p.startswith(('/ph/','/art/')):external[p]=h
    for row in json.loads((ROOT/'inventory.json').read_text())['baseline']:external.update(row['sources'])
    for p in ROOT.rglob('*.npz'):external[str(p)]=sha(p)
    dump(ROOT/'external_payloads.json',dict(at=stamp(),files=external,note='Original models, images and per-Gaussian tile arrays remain external. Tables/figures are in ZIP; re-render needs original scene/model inputs. Container /ph,/art,/out map to sibling JointBuildGS-artifacts.',scientific_verdict=None))
    add(ROOT/'external_payloads.json','external_payloads.json')
    stampname=stamp();suffix=stampname[5:7]+stampname[8:10]+'-'+stampname[11:13]+stampname[14:16]
    path=OUT/'handover'/f'PHD-MAIN-TARGET-v1_원인점검r8LoD2_{suffix}.zip';assert not path.exists()
    hashes={name:sha(p) for name,p in members.items()}
    manifest=dict(at=stamp(),member_sha256=hashes,external_files=len(external),scientific_verdict=None,optimization_steps=0)
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS',''.join(h+'  '+name+'\n' for name,h in sorted(hashes.items())))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for name,h in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==h,name
    receipt=dict(at=stamp(),archive=str(path),sha256=sha(path),bytes=path.stat().st_size,checked_members=len(hashes),crc='PASS',member_sha256='PASS',external_files=len(external),scientific_verdict=None)
    dump(ROOT/'delivery.json',receipt);dump(DOC/'delivery_receipt_cause_r8_lod2.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
