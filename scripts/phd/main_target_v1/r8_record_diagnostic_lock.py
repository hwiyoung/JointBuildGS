"""Bind the saved stopped state and inherited comparisons before the CPU/GPU readout."""
from common import *
def main():
    root=OUT/'r8_recorded_continue';stop=json.loads((root/'STOP_LoD2.json').read_text());src=Path(stop['stop_dir']);cfg=json.loads((CFG/'r8_record_continue.json').read_text())
    files={str(p):sha(p) for p in Path(__file__).parent.glob('r8_record*.py')}
    for p in [root/'STOP_LoD2.json',CFG/'r8_record_continue.json',Path(cfg['boundaries']),src/'checkpoint.pth',src/'point_cloud.ply',src/f'snapshot_{stop["attempted_iteration"]}.npz',src/'gradient.npz']:
        files[str(p)]=sha(p)
    assert files[str(src/'checkpoint.pth')]==stop['checkpoint_sha256'];assert files[str(src/'point_cloud.ply')]==stop['ply_sha256']
    old=OUT/'r8_lod2_cause'
    for name in ['counts.json','render_views.json','render_cross.json','summary.json','inventory.json','memory.json']:
        files[str(old/name)]=sha(old/name)
    for name in ['base_LoD2_7000','r8_LoD2_7000']:
        p=old/'states'/name/'arrays.npz';files[str(p)]=sha(p)
    target=CFG/'r8_record_diagnostics.lock.json';assert not target.exists()
    dump(target,dict(at=stamp(),files=files,optimization_steps=0,scientific_verdict=None));print('STOP_DIAGNOSTICS_LOCKED',len(files),flush=True)
if __name__=='__main__':main()
