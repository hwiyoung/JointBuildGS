"""CPU-only disassembly audit of original and separate binaries, no CUDA execution."""
import sys,subprocess,re,hashlib,json,datetime
from pathlib import Path
ROOT=Path('/out/rfix')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
 label=sys.argv[1];dest=ROOT/'sass_audit'/label;dest.mkdir(parents=True,exist_ok=False);original=json.loads((ROOT/'inventory'/label/'manifest.json').read_text());fixed=json.loads((ROOT/'builds'/label/'receipt.json').read_text());kernels={}
 for version,path in [('original',original['extension']),('fixed',fixed['extension'])]:
  p=subprocess.run(['/usr/local/cuda/bin/cuobjdump','--dump-sass',path],capture_output=True,text=True);assert p.returncode==0,p.stderr;(dest/(version+'.sass.txt')).write_text(p.stdout);(dest/(version+'.stderr.txt')).write_text(p.stderr)
  arch=None;name=None;parts={}
  for line in p.stdout.splitlines():
   a=re.search(r'code for (sm_\d+)',line)
   if a:arch=a.group(1)
   n=re.search(r'Function\s*:\s*(\S+)',line)
   if n:name=n.group(1);parts[(arch,name)]=[]
   if name and re.search(r'/\*[0-9a-fA-F]+\*/',line):parts[(arch,name)].append(line.strip())
  kernels[version]={k:'\n'.join(v) for k,v in parts.items() if k[0]=='sm_86'};assert kernels[version],list(parts)[:5]
 rows=[]
 for key in sorted(set(kernels['original'])|set(kernels['fixed'])):
  a=kernels['original'].get(key);b=kernels['fixed'].get(key)
  rows.append(dict(architecture=key[0],kernel=key[1],present_original=a is not None,present_fixed=b is not None,instruction_listing_equal=a==b if a is not None and b is not None else None,original_sha256=digest(a) if a is not None else None,fixed_sha256=digest(b) if b is not None else None))
 result=dict(at=datetime.datetime.now().astimezone().isoformat(),label=label,rows=rows,scope='sm_86 SASS instruction listing including instruction encodings; observation only, not a replacement acceptance gate',scientific_verdict=None);(dest/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('SASS_AUDIT',label,len(rows),sum(r['instruction_listing_equal'] is True for r in rows),flush=True)
if __name__=='__main__':main()
