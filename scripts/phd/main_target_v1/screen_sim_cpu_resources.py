"""Raise only this task's read-only CPU container quota; preserve one-job ordering."""
import datetime,json,subprocess,time
from r8_screen_prepare import O,C,R,dump,sha
def main():
 root=O/'screen_sim';seen=set();records=[];lock=json.loads((C/'screen_sim_cpu_resources.lock.json').read_text());assert sha(__file__)==lock['script_sha256']
 while not (root/'cpu_receipt.json').exists():
  p=subprocess.run(['docker','inspect','jbgs-screen-sim-cpu'],capture_output=True,text=True)
  if p.returncode==0:
   row=json.loads(p.stdout)[0];ident=row['Id'];command=row['Config']['Cmd']
   assert '/repo/scripts/phd/main_target_v1/screen_sim_mesh.py' in command,command
   assert row['HostConfig']['ReadonlyRootfs'] and not row['HostConfig'].get('DeviceRequests')
   if ident not in seen:
    before=row['HostConfig']['NanoCpus'];r=subprocess.run(['docker','update','--cpus','24',ident],capture_output=True,text=True)
    if r.returncode==0:
     after=json.loads(subprocess.check_output(['docker','inspect',ident],text=True))[0]['HostConfig']['NanoCpus'];assert after==24_000_000_000;seen.add(ident);records.append(dict(at=datetime.datetime.now().astimezone().isoformat(),container=ident,command=command,old_nanocpus=before,new_nanocpus=after,memory_bytes=row['HostConfig']['Memory']));dump(root/'cpu_resource_updates.json',dict(updates=records,large_jobs_parallel=1,OMP_NUM_THREADS=6,numerical_rules_changed=False,scientific_verdict=None))
  time.sleep(5)
if __name__=='__main__':main()
