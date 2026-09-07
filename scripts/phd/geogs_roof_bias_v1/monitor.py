"""Detached read-only runtime evidence. Stops after supervisor completion or exit."""
import datetime,json,os,re,subprocess,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3];T=(REPO/'../JointBuildGS-artifacts/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921').resolve()
while True:
 now=datetime.datetime.now(datetime.timezone.utc).isoformat()
 state=json.loads((T/'status.json').read_text());pid=state['pid']
 try:os.kill(pid,0);alive=True
 except ProcessLookupError:alive=False
 gpu=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True)
 progress={}
 for root in (T/'conditions').iterdir():
  p=root/'train.log'
  if not p.exists():continue
  with p.open('rb') as f:f.seek(max(0,p.stat().st_size-65536));tail=f.read().decode('utf-8',errors='replace')
  it=re.findall(r'(\d+)/30000',tail);progress[root.name]={'iteration':int(it[-1]) if it else None,'log_bytes':p.stat().st_size,'log_mtime':p.stat().st_mtime}
 receipt={'at':now,'supervisor_pid':pid,'supervisor_alive':alive,'phase':state['phase'],'condition':state.get('condition','N'),'gpu_csv_columns':['index','gpu_percent','memory_used_MiB','memory_total_MiB'],'gpu_csv':gpu.stdout.strip(),'training':progress}
 p=T/'runtime_status.tmp';p.write_text(json.dumps(receipt,indent=2));p.replace(T/'runtime_status.json')
 with (T/'logs/runtime.jsonl').open('a') as f:f.write(json.dumps(receipt)+'\n')
 if state['phase']=='FINISHED' or not alive:break
 time.sleep(30)
