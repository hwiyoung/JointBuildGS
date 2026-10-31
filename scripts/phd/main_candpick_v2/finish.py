"""Bounded task pipeline: wait for planned receipts, then render public delivery."""
import subprocess
import time
from cp2_common import *

def main():
    started=time.monotonic();last=0
    while True:
        training=len(list((OUT/'runs').glob('*/complete.json')))
        stopped=len(list((OUT/'runs').glob('*/stopped.json')))
        depth=len(list((OUT/'depth').glob('*/complete.json')))
        failures=list((OUT/'runs').glob('*/failure_*.json'))
        if failures:raise RuntimeError('Training failure requires review; see task-local failure receipt.')
        if time.monotonic()-last>=60:
            subprocess.run(['python','-B','/repo/scripts/phd/main_candpick_v2/update_progress.py'],check=True)
            last=time.monotonic()
        if training==22 and stopped==2 and depth==28:break
        if time.monotonic()-started>6*3600:raise RuntimeError('Bounded queue wait exceeded six hours; preserve pending state.')
        time.sleep(10)
    assert (OUT/'photo_dl/patch_export_complete.json').exists()
    scripts=['score_opacity.py','plot_figures.py','report.py','validate_results.py','package_results.py']
    save(CFG/'delivery_implementation.lock.json',dict(at=now(),files=[bind(Path(__file__).with_name(s)) for s in scripts],scientific_verdict=None))
    for script in scripts:
        args=['python','-B','-u',str(Path(__file__).with_name(script))]
        if script=='plot_figures.py':args.append('training')
        print('DELIVERY_STEP',script,flush=True);subprocess.run(args,check=True)
    receipt=json.loads((DOC/'tables/package_receipt.json').read_text())
    save(OUT/'delivery_ready.json',dict(at=now(),status='READY_FOR_FINAL_GIT_AND_VISUAL_REVIEW',package=receipt,
        scientific_verdict=None));print('DELIVERY_READY',flush=True)

if __name__=='__main__':main()
