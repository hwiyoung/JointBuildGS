"""Read-only cgroup observations for currently authorized CPU readouts."""
import json,subprocess,time
from pathlib import Path
from run_pilot_r8 import OUT,stamp

def main():
    dest=OUT/'r8/verification/cpu_resources.jsonl'
    deadline=time.monotonic()+12*3600
    while time.monotonic()<deadline and not (OUT/'handover/delivery_receipt_r8_final.json').exists():
        names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
        names=[n for n in names if n.startswith('jbgs-target-') and any(x in n for x in ['axes-','post-','fuse-'])]
        rows=[]
        for name in names:
            try:
                meta=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
                pid=meta['State']['Pid'];cg=Path(f'/proc/{pid}/cgroup').read_text().split('0::',1)[1].strip()
                root=Path('/sys/fs/cgroup')/cg.lstrip('/')
                rows.append(dict(name=name,pid=pid,current_bytes=int((root/'memory.current').read_text()),peak_bytes=int((root/'memory.peak').read_text()),limit_bytes=int((root/'memory.max').read_text())))
            except (FileNotFoundError,subprocess.CalledProcessError,IndexError):continue
        if rows:
            available=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
            with dest.open('a') as f:f.write(json.dumps(dict(at=stamp(),available_bytes=available,rows=rows,scientific_verdict=None))+'\n')
        time.sleep(10)

if __name__=='__main__':main()
