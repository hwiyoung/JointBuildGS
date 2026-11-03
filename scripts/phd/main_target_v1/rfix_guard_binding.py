"""Record the actual guarded binary used by the earlier r8 recorded continuation."""
import json,hashlib,subprocess,datetime,re
from pathlib import Path
ROOT=Path('/out/rfix');OLD=Path('/out/r8_recorded_continue');CFG=Path('/cfg')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 dest=ROOT/'guard_binding';dest.mkdir(exist_ok=False);binary=OLD/'runtime/build/jbgs_r8_record_guard.so';lock=json.loads((CFG/'r8_record_runtime.lock.json').read_text());assert lock['files'][str(binary)]==sha(binary)
 source={name:sha(OLD/'runtime/rasterizer'/name)==sha(ROOT/'inventory/target/source'/name) for name in ['cuda_rasterizer/forward.cu','cuda_rasterizer/backward.cu','cuda_rasterizer/auxiliary.h','cuda_rasterizer/config.h']};assert all(source.values())
 p=subprocess.run(['/usr/local/cuda/bin/cuobjdump','--dump-sass',str(binary)],capture_output=True,text=True);assert p.returncode==0,p.stderr;(dest/'recorded_guard.sass.txt').write_text(p.stdout)
 arch=None;name=None;parts={}
 for line in p.stdout.splitlines():
  a=re.search(r'code for (sm_\d+)',line)
  if a:arch=a.group(1)
  n=re.search(r'Function\s*:\s*(\S+)',line)
  if n:name=n.group(1);parts[(arch,name)]=[]
  if name and re.search(r'/\*[0-9a-fA-F]+\*/',line):parts[(arch,name)].append(line.strip())
 baseline=json.loads((ROOT/'sass_audit/target/result.json').read_text());rows=[]
 for r in baseline['rows']:
  if 'renderCUDA' not in r['kernel'] and 'preprocessCUDA' not in r['kernel']:continue
  code='\n'.join(parts[(r['architecture'],r['kernel'])]);h=hashlib.sha256(code.encode()).hexdigest();rows.append(dict(kernel=r['kernel'],recorded_guard_sha256=h,default_native_sha256=r['original_sha256'],instruction_listing_equal=h==r['original_sha256']))
 result=dict(at=datetime.datetime.now().astimezone().isoformat(),state='r8_LoD2_stop',actual_recorded_training_renderer=str(binary),actual_recorded_renderer_sha256=sha(binary),previous_runtime_lock=str(CFG/'r8_record_runtime.lock.json'),previous_runtime_lock_sha256=sha(CFG/'r8_record_runtime.lock.json'),previous_binary_binding_verified=True,current_measurement_reference='installed unmodified native diff_surfel_rasterization._C, as used in the preceding screen simulation',native_source_equal=source,native_kernels=rows,guard='0.5 free-memory stop and observation only; no screen-box correction in this historical build',current_verification_timing='after first rfix renders; earlier runtime lock retained, not retrospectively added to rfix initial lock',scientific_verdict=None)
 (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('GUARD_BINDING',all(r['instruction_listing_equal'] for r in rows),sha(binary),flush=True)
if __name__=='__main__':main()
