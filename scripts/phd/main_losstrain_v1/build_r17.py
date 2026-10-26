"""Reproducible r16 -> r17 additive depth-only fork; run in Docker."""
import difflib
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT=Path('/repo'); DST=Path('/fork17'); SRC=ROOT/'src/phd/forks/GeoGS-conf-guided-v1-r16'
HERE=ROOT/'scripts/phd/main_losstrain_v1'

def replace_once(text, old, new):
    assert text.count(old)==1, old
    return text.replace(old,new,1)

def main():
    assert not any(DST.iterdir()), 'refuse to overwrite an existing r17 fork'
    shutil.copytree(SRC,DST,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    p=DST/'jbgs_judgment.py';s=p.read_text()
    s=replace_once(s,'REVISION = "r16"','REVISION = "r17"')
    args='''
    # r17: opt-in depth-only experiment. The default executes the r16 path.
    g.add_argument("--jbgs_sw_depth_loss", choices=["current", "fixed", "dynamic"], default="current")
    g.add_argument("--jbgs_vfile_dir", default="")
    g.add_argument("--jbgs_vfile_vprior", choices=["now", "gt", "soft"], default="now")
    g.add_argument("--jbgs_depth_lambda", type=float, default=0.0025)
'''
    s=replace_once(s,'\n\ndef apply_seed(args):',args+'\n\ndef apply_seed(args):')
    anchor='        meta = dict(mode=self.mode, revision=REVISION,'
    s=replace_once(s,anchor,'        if getattr(args, "jbgs_sw_depth_loss", "current") != "current":\n            lt_initialize(self)\n'+anchor)
    anchor='        LM = HostMaps(_load_set(Path(args.jbgs_locmap_dir), names, self.size, "cpu", dtype=np.int32))   # r14-2: one view at a time'
    s=replace_once(s,anchor,anchor+'\n        if getattr(args, "jbgs_sw_depth_loss", "current") != "current":\n            self.lt_locations = LM  # r17: retain the existing host maps; patch values alone live on GPU')
    anchor='        D = render_pkg["surf_depth"].squeeze(0)\n        zero = torch.zeros((), device=D.device)'
    s=replace_once(s,anchor,'        if getattr(self.args, "jbgs_sw_depth_loss", "current") != "current":\n            return lt_losses(self, cam_name, render_pkg)\n'+anchor)
    s+='\n\n# ---------------- PHD-MAIN-LOSSTRAIN-v1 r17 opt-in depth terms ----------------\n'+(HERE/'r17_depth.py').read_text()
    p.write_text(s)
    files=lambda r:sorted(x.relative_to(r) for x in r.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert files(SRC)==files(DST)
    changed=[str(r) for r in files(DST) if sha(SRC/r)!=sha(DST/r)]
    assert changed==['jbgs_judgment.py'],changed
    doc=Path('/docs/provenance');doc.mkdir(parents=True,exist_ok=True)
    diff=''.join(difflib.unified_diff((SRC/'jbgs_judgment.py').read_text().splitlines(True),s.splitlines(True),'r16/jbgs_judgment.py','r17/jbgs_judgment.py'))
    (doc/'r16_to_r17.diff').write_text(diff)
    (doc/'build_r17.json').write_text(json.dumps(dict(task_id='PHD-MAIN-LOSSTRAIN-v1',
        built_at=datetime.now().astimezone().isoformat(),changed=changed,file_count=len(files(DST)),
        parent_hashes={str(r):sha(SRC/r) for r in files(SRC)},r17_hashes={str(r):sha(DST/r) for r in files(DST)},
        code_scope='jbgs_judgment.py only; train.py and all other files byte-identical',
        scientific_verdict=None),indent=2)+'\n')
    print('r17 built; changed files:',changed)

if __name__=='__main__':main()
