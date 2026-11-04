"""Copy inherited judgment code; only source/output scope adapters are changed."""
from pathlib import Path
import shutil
import hashlib
import json
R=Path(__file__).resolve().parents[3]
S=Path(__file__).parent
src=R/'scripts/phd/main_judgeapply_v1';dst=S/'inherited_judgeapply'
assert not dst.exists()
shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
p=dst/'common.py';s=p.read_text().replace("C,D,O,R=Path('/cfg'),Path('/docs'),Path('/out'),Path('/repo')", "C,D,O,R=Path('/repo/configs/phd/main_judgeapply_v1'),Path('/docs'),Path('/out/outside')/os.environ['FINALTRAIN_SITE'],Path('/repo')")
p.write_text(s)
p=dst/'geometry_run.py';s=p.read_text().replace("d['in_eval']&np.isin(d['kind'],cfg()['priors'][prior])", "np.isin(d['kind'],cfg()['priors'][prior])")
p.write_text(s)
manifest=[]
for p in sorted(dst.rglob('*')):
    if p.is_file():
        old=src/p.relative_to(dst)
        manifest.append(dict(source=str(old.relative_to(R)),copy=str(p.relative_to(R)),source_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),copy_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),changed=old.read_bytes()!=p.read_bytes()))
(R/'configs/phd/main_finaltrain_v1/judgment_source_copy.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('JUDGMENT_COPY',len(manifest))
