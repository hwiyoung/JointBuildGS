"""Freeze the exact historical nojudge commands before bounded 7k re-execution."""
import datetime as dt,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'configs/phd/main_target_v1'
PH=R.parent/'JointBuildGS-artifacts/phase-payloads/phd';O=PH/'main_target_v1/PHD-MAIN-TARGET-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    dest=C/'baseline7k.r7.json';assert not dest.exists()
    rows=[]
    for prior in ['ALS','LoD2']:
        source=PH/f'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10/nojudge_{prior}_s0/receipt.json'
        old=json.loads(source.read_text());cmd=old['command'];args=cmd[cmd.index('train.py')+1:]
        model=f'/out/r7/baselines/base7k_B173nb_b10_{prior}_s0/model';args[args.index('-m')+1]=model
        args.insert(args.index('--save_iterations')+1,'7000')
        args+=['--jbgs_stop_after','7000']
        rows.append(dict(prior=prior,name=f'base7k_B173nb_b10_{prior}_s0',args=args,original_receipt=str(source),original_receipt_sha256=sha(source),
            differences={'model_path':model,'save_iterations':'add 7000 before density control','jbgs_stop_after':7000},
            unchanged_iterations=30000,seed=0,source=old['source'],image=old['image'],image_id=old['image_id']))
    at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    files={str(p.relative_to(R)):sha(p) for p in sorted((R/'src/phd/forks/GeoGS-conf-guided-v1-r15').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    put(dest,dict(at=at,task='PHD-MAIN-TARGET-v1',revision='r7',rows=rows,source_files=files,scientific_verdict=None))
    put(C/'baseline7k.r7.lock.json',dict(at=at,sha256=sha(dest),parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),scientific_verdict=None))
    (O/'r7/baselines').mkdir(parents=True,exist_ok=True)
    print('BASELINE7K_LOCKED',at,sha(dest))
if __name__=='__main__':main()
