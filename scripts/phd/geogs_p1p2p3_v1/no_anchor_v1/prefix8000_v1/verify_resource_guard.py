"""Small CPU fixtures for desktop identity, denial and export boundary receipts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import resource_guard as guard


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').is_file(): raise RuntimeError('Docker required')
    args.out.mkdir(exist_ok=False)
    checks = []
    started = time.time()
    stat = '72937 (gnome-remote-de) ' + ' '.join(['S'] + ['0'] * 18 + ['60213'] + ['0'] * 8)
    row = '72937, /usr/libexec/gnome-remote-desktop-daemon, 260\n'
    def test(name, function):
        try:
            function(); checks.append(dict(name=name, status='PASS'))
        except Exception as error:
            checks.append(dict(name=name, status='FAIL', error=repr(error)))
    def reject(*values):
        try: guard.admit(*values)
        except ValueError: return
        raise AssertionError('Unexpected GPU process or changed identity was admitted')
    def call(gpu=0, text=row, pstat=stat, comm=guard.DESKTOP['comm'], exe=guard.DESKTOP['executable']):
        return guard.admit(gpu, text, pstat, comm, exe)
    test('empty_GPU0', lambda: call(text=''))
    test('empty_GPU1', lambda: call(gpu=1, text=''))
    test('exact_desktop_GPU0', call)
    test('desktop_512MiB_boundary', lambda: call(text=row.replace('260', '512')))
    for name, values in [
        ('desktop_513MiB_denied', (0,row.replace('260','513'),stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('desktop_GPU1_denied', (1,row,stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('other_PID_denied', (0,row.replace('72937','72938'),stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('PID_reuse_denied', (0,row,stat.replace('60213','60214'),guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('zombie_denied', (0,row,stat.replace(') S ',') Z '),guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('comm_change_denied', (0,row,stat,'other',guard.DESKTOP['executable'])),
        ('exe_change_denied', (0,row,stat,guard.DESKTOP['comm'],'/tmp/other')),
        ('nvidia_name_change_denied', (0,row.replace(guard.DESKTOP['executable'],'python'),stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('another_training_process_denied', (0,row+'101, python, 1\n',stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('duplicate_PID_denied', (0,row+row,stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('unknown_memory_denied', (0,row.replace('260','N/A'),stat,guard.DESKTOP['comm'],guard.DESKTOP['executable'])),
        ('missing_proc_identity_denied', (0,row,'','','')),
    ]: test(name, lambda values=values: reject(*values))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); exported = root / 'export'; exported.mkdir()
        for phase in ('before','after'):
            for name, text in {'compute.csv':row, 'gpu.csv':'0, GPU-fixture, 24126, 260, 0\n',
                'nvidia_exit.txt':'0\n', 'gpu_query_exit.txt':'0\n', 'proc_stat.txt':stat,
                'proc_comm.txt':guard.DESKTOP['comm'], 'proc_exe.txt':guard.DESKTOP['executable']}.items():
                (root / (phase+'_'+name)).write_text(text)
        def boundary_roundtrip():
            command = [sys.executable,str(Path(guard.__file__)),'--gpu','0','--region','P1','--root',str(root)]
            subprocess.run(command+['--phase','before'],check=True,capture_output=True,text=True)
            (exported/'receipt.json').write_text(json.dumps(dict(status='FAIL',native_exit_code=1,fixture_only=True)))
            subprocess.run(command+['--phase','after','--export-root',str(exported),'--wrapper-exit','1'],
                           check=True,capture_output=True,text=True)
            value = json.loads((exported/'resource_execution_receipt.json').read_text())
            assert value['status']=='PASS_RESOURCE_BOUNDARY'
            assert value['source_export_receipt']['status']=='FAIL' and value['wrapper_exit_code']==1
            assert value['before']['desktop_allowance_used'] and value['after']['desktop_allowance_used']
            assert value['source_export_receipt']['sha256']==guard.sha(exported/'receipt.json')
            assert value['same_gpu_training_overlap_allowed'] is False
        test('before_after_SHA_binding_does_not_relabel_failed_export',boundary_roundtrip)
        def query_failure():
            (root/'before_nvidia_exit.txt').write_text('1\n')
            try: guard.observe(root,'before',0)
            except ValueError: return
            raise AssertionError('Failed nvidia observation accepted')
        test('failed_GPU_query_denied',query_failure)
        def wrong_gpu():
            (root/'before_nvidia_exit.txt').write_text('0\n')
            (root/'before_gpu.csv').write_text('1, GPU-other, 24126, 260, 0\n')
            try: guard.observe(root,'before',0)
            except ValueError: return
            raise AssertionError('Other GPU state accepted')
        test('wrong_GPU_state_denied',wrong_gpu)
    test('wrapper_Bash_syntax',lambda:subprocess.run(['bash','-n',str(Path(__file__).with_name('run.sh'))],check=True))
    result = dict(schema='GEOGS_PREFIX_RESOURCE_GUARD_CPU_VALIDATION_v1',
        status='PASS' if all(row['status']=='PASS' for row in checks) else 'FAIL', scientific_verdict=None,
        checks=checks, gpu_work_launched=False, native_export_launched=False, reference_accessed=False,
        started_unix=started,finished_unix=time.time(),
        source_sha256={name:guard.sha(Path(__file__).with_name(name)) for name in
                       ('resource_guard.py','run.sh','verify_resource_guard.py')})
    (args.out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
