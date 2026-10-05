"""Validate local document targets and freeze the reviewed document bytes."""
import argparse
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote

from scripts.phd.p2_ab_v1.a_final_qa import read,sha,write,stamp,REPO


def main(config):
    cfg=read(config);out=Path(cfg['output'])
    if not out.is_dir() or any(out.iterdir()):raise ValueError('new empty output required')
    documents=sorted((REPO/cfg['document_root']).glob('*.md'))
    assert documents
    for name in cfg['required_documents']:assert (REPO/cfg['document_root']/name).is_file(),name
    source_hash={str(p.relative_to(REPO)):sha(p) for p in [Path(__file__),config]}
    hashes={str(p.relative_to(REPO)):sha(p) for p in documents}
    for p in [Path(__file__),config]+documents:
        q=out/'snapshot'/p.relative_to(REPO);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    write(out/'PRE_QA.json',dict(started=stamp(),source_sha256=source_hash,documents_sha256=hashes,scientific_verdict=None))
    links=[];missing=[]
    for p in documents:
        # Ignore illustrative markdown links inside fenced code blocks.
        body=re.sub(r'```.*?```','',p.read_text(),flags=re.DOTALL)
        for match in re.finditer(r'\[[^\]\n]*\]\(([^)\n]+)\)',body):
            target=match.group(1).strip().strip('<>')
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('#'):continue
            target=unquote(target.split('#',1)[0].split('?',1)[0])
            if not target:continue
            resolved=(p.parent/target).resolve() if not target.startswith('/') else Path(target)
            host_repo=cfg['host_repo'];host_artifact=cfg['host_artifact']
            if str(resolved).startswith(host_repo):resolved=REPO/str(resolved)[len(host_repo):].lstrip('/')
            if str(resolved).startswith(host_artifact):resolved=Path('/artifacts/JointBuildGS')/str(resolved)[len(host_artifact):].lstrip('/')
            # Sibling artifact links resolve against the workspace mount in Docker.
            sibling=REPO.parent/'JointBuildGS-artifacts'
            if str(resolved).startswith(str(sibling)):resolved=Path('/artifacts/JointBuildGS')/str(resolved)[len(str(sibling)):].lstrip('/')
            row=dict(document=str(p.relative_to(REPO)),target=target,resolved=str(resolved),exists=resolved.exists())
            links.append(row)
            if not row['exists']:missing.append(row)
    assert all(sha(REPO/p)==h for p,h in hashes.items())
    receipt=dict(status='PASS' if not missing else 'FAILED',scientific_verdict=None,documents=len(documents),
        checked_local_links=len(links),missing=missing,links=links,documents_sha256=hashes,
        limits='Local file existence only; external URLs and heading anchors excluded',completed=stamp())
    write(out/'DOCUMENT_QA_RECEIPT.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('links','documents_sha256')}),flush=True)
    if missing:raise RuntimeError('Broken local document links')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);main(p.parse_args().config.resolve())
