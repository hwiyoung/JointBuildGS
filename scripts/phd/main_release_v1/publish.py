"""Scoped commits and immutable, self-checking delivery ZIPs."""
import contextlib,fcntl,hashlib,json,subprocess,zipfile
from pathlib import Path
from gpu_job import R,O,C,D,dump,now
ALLOWED=['configs/phd/main_release_v1','scripts/phd/main_release_v1','docs/experiments/phd/main_release_v1','src/phd/forks/GeoGS-conf-guided-v1-r24']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
@contextlib.contextmanager
def lock():
 p=O/'delivery/publish.lock';p.parent.mkdir(exist_ok=True)
 with p.open('a') as f:fcntl.flock(f,fcntl.LOCK_EX);yield
def commit(event,paths):
 paths=[str(Path(p).relative_to(R)) if Path(p).is_absolute() else str(p) for p in paths]
 assert all(any(p==a or p.startswith(a+'/') for a in ALLOWED) for p in paths)
 staged=subprocess.check_output(['git','diff','--cached','--name-only','-z'],cwd=R).decode().split('\0');staged=[p for p in staged if p]
 assert all(any(p==a or p.startswith(a+'/') for a in paths) for p in staged),'Existing staged paths outside exact publish selection; preserve them'
 subprocess.run(['git','add','--',*paths],cwd=R,check=True)
 staged=subprocess.check_output(['git','diff','--cached','--name-only','-z'],cwd=R).decode().split('\0');staged=[p for p in staged if p]
 assert all(any(p==a or p.startswith(a+'/') for a in ALLOWED) for p in staged)
 if staged:subprocess.run(['git','commit','--quiet','-m','PHD-MAIN-RELEASE-v1 '+event],cwd=R,check=True)
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
 subprocess.run(['git','push','origin','HEAD:exp/main-experiment'],cwd=R,check=True)
 return head
def bundle(name,paths):
 files=[]
 for p in map(Path,paths):
  if p.is_dir():files.extend(q for q in p.rglob('*') if q.is_file() and '__pycache__' not in q.parts)
  elif p.exists():files.append(p)
 entries={}
 for p in sorted(set(files)):
  root=R if p.is_relative_to(R) else O
  arc=('repository/' if root==R else 'payload/')+str(p.relative_to(root));entries[arc]=p
 dest=O/'delivery'/name;dest.parent.mkdir(exist_ok=True);assert not dest.exists(),dest
 sums={arc:sha(p) for arc,p in entries.items()}
 with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for arc,p in entries.items():z.write(p,arc)
  z.writestr('SHA256SUMS',''.join(h+'  '+arc+'\n' for arc,h in sums.items()))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for arc,h in sums.items():assert hashlib.sha256(z.read(arc)).hexdigest()==h
 rec=dict(at=now(),path=str(dest),sha256=sha(dest),bytes=dest.stat().st_size,members=len(entries)+1,status='PASS_ZIP_CRC_AND_SHA256',scientific_verdict=None)
 dump(dest.with_suffix('.receipt.json'),rec);dest.with_suffix('.sha256').write_text(rec['sha256']+'  '+name+'\n');return rec
