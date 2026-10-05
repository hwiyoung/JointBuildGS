"""Publish new immutable local diagnostic packet without changing current.json."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    ap=argparse.ArgumentParser()
    for k in ('attempt','evaluation','site','ui'):ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args()
    source=read(a.attempt/'receipt.json');evaluation=read(a.evaluation/'receipt.json')
    assert source['status']=='PASS_INTERNAL_FIT_DIAGNOSTIC' and source['scientific_verdict'] is None
    assert evaluation['status']=='PASS_TECHNICAL_REFERENCE_EVALUATION' and evaluation['scientific_verdict'] is None
    for row in source['outputs']:assert sha(a.attempt/row['path'])==row['sha256']
    for name,row in evaluation['outputs'].items():assert sha(a.evaluation/name)==row['sha256']
    assert next(r['sha256'] for r in evaluation['inputs'] if r['path']=='/attempt/receipt.json')==sha(a.attempt/'receipt.json')
    current=a.site/'current.json';before=sha(current) if current.exists() else None
    packet=a.site/'packets'/('packet_normal_photometry_v3_7_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    packet.mkdir(parents=True,exist_ok=False)
    shutil.copytree(a.attempt,packet/'assets'/'diagnostic')
    shutil.copytree(a.evaluation,packet/'assets'/'evaluation')
    for f in ('index.html','app.js','style.css'):shutil.copy2(a.ui/f,packet/f)
    shutil.copy2(a.attempt/'manifest.json',packet/'data.json')
    after=sha(current) if current.exists() else None
    assert before==after,'Existing pointer changed concurrently'
    outputs=[dict(path=str(p.relative_to(packet)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(packet.rglob('*')) if p.is_file()]
    write(packet/'receipt.json',dict(status='PASS',scientific_verdict=None,scope='INTERNAL_FIT_WITH_SEPARATE_REFERENCE_EVALUATION',
        source_receipt_sha256=sha(a.attempt/'receipt.json'),evaluation_receipt_sha256=sha(a.evaluation/'receipt.json'),
        current_before_sha256=before,current_after_sha256=after,current_pointer_updated=False,
        publisher_sha256=sha(Path(__file__)),outputs=outputs,browser_qa='PENDING'))
    print(json.dumps(dict(packet=str(packet),url='http://localhost:8905/packets/'+packet.name+'/index.html')))


if __name__=='__main__':main()
