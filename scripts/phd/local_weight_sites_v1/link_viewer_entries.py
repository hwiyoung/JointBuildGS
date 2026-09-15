"""Retain exact historical HTML and connect old entry URLs to a verified release."""
import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)


def main(attempt,art,server_data):
    config=json.loads((attempt/'config.json').read_text()); name=config['publication_name']
    publication=json.loads((attempt/(name+'_publication.json')).read_text())
    qa=json.loads((attempt/'qa_v1/receipt.json').read_text())
    assert publication['status']=='PASS_LOCAL_VIEWER_PUBLICATION' and qa['status']=='PASS'
    assert all(check['pass'] for check in qa['checks'])
    root=art/'phase-payloads/phd/local_weight_sites_v1/PHD-LOCAL-WEIGHT-SITES-v1'
    sources=[('local_weight_sites_20260920_v2',root/'viewer_20260920_v1'),
             ('local_weight_sites_20260921_v3',root/'photo_overlay_20260921_v1')]
    preparations=[]
    for old,folder in sources:
        receipt=json.loads((folder/(old+'_publication.json')).read_text())
        destination=server_data/old; index=destination/'index.html'
        assert not (destination/'index.archived.html').exists()
        for relative,digest in receipt['files'].items():assert sha(destination/relative)==digest,(old,relative)
        backup=attempt/'entry_backups'/old; backup.mkdir(parents=True)
        data=index.read_bytes(); (backup/'index.html').write_bytes(data)
        html=('''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>최신 원영상 투영점 뷰어로 이동</title><body style="font:18px/1.7 system-ui;padding:32px">
<h1>원영상 투영점 · MVS 재검토 뷰어</h1><p><a id="latest" href="../'''+name+'''/index.html">최신 뷰어 열기</a></p>
<p><a href="index.archived.html">이전 화면 보관본 열기</a></p>
<script>const link=document.getElementById('latest');const next=new URL(link.getAttribute('href'),location.href);next.search=location.search;next.hash=location.hash;link.href=next.href;location.replace(next.href);</script></body></html>
''').encode()
        preparations.append(dict(old=old,before_sha256=hashlib.sha256(data).hexdigest(),
             after_sha256=hashlib.sha256(html).hexdigest(),target=str(index),archive=str(destination/'index.archived.html'),
             parent_receipt_sha256=sha(folder/(old+'_publication.json'))))
        (backup/'redirect.html').write_bytes(html)
    write(attempt/'entry_retention_review.json',dict(status='PREPARED_EXACT_HTML_ENTRY_CHANGE',
          user_scope='Fix revised viewer connection; no research payload changes',scientific_verdict=None,
          targets=preparations,retention='Exact former index archived; all old assets and original release snapshots retained',
          new_release_receipt_sha256=sha(attempt/(name+'_publication.json'))))
    for item in preparations:
        index=Path(item['target']); backup=attempt/'entry_backups'/item['old']
        assert sha(index)==item['before_sha256']
        with Path(item['archive']).open('xb') as stream:stream.write((backup/'index.html').read_bytes())
        temporary=index.with_name('.index.redirect.tmp'); assert not temporary.exists()
        with temporary.open('xb') as stream:stream.write((backup/'redirect.html').read_bytes())
        os.replace(temporary,index)
        assert sha(index)==item['after_sha256'] and sha(item['archive'])==item['before_sha256']
        for filename,expected in [('index.html',item['after_sha256']),('index.archived.html',item['before_sha256'])]:
            with urllib.request.urlopen('http://127.0.0.1:8913/data/'+item['old']+'/'+filename) as response:
                assert response.status==200 and hashlib.sha256(response.read()).hexdigest()==expected
    write(attempt/'entry_link_receipt.json',dict(status='PASS_RETAINED_ENTRY_LINKS',scientific_verdict=None,
          targets=preparations,latest=name,port_embedded_in_redirect=False,query_and_fragment_preserved=True,
          script_sha256=sha(__file__),original_geometry_or_metrics_changed=False))
    print('PASS_RETAINED_ENTRY_LINKS',len(preparations))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['attempt','art','server-data']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();main(args.attempt,args.art,args.server_data)
