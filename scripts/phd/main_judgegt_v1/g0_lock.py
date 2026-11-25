"""단계 0: 설정 잠그기와 입력 기록. 사용: g0_lock.py [lock|record <stage-name>]
lock   : 설정 sha256 과 입력 파일 sha256(점 파일은 크기·수정 시각)을 judgegt_v1.lock.json 에 적는다(이미 있으면 바꾸지 않음).
record : 단계의 첫 계산 전에 설정 sha256 과 시각을 lock 의 stages 에 덧붙인다."""
import sys
from common import *
import glob
def main(a):
    lf = C/'judgegt_v1.lock.json'
    if a[0] == 'lock':
        if lf.exists(): print('LOCK exists', lf); return
        c = json.loads((C/'judgegt_v1.json').read_text()); ins = {}
        for k in ['tau', 'buildings', 'cameras', 'image_split', 'tau_release']: ins[k] = dict(path=c['inputs'][k], sha256=sha(c['inputs'][k]))
        for p in PRIORS:
            for k in ['patches', 'patch_table']: q = c['inputs'][k].format(prior=p); ins[f'{k}_{p}'] = dict(path=q, sha256=sha(q))
        pts = {}
        for f in sorted(glob.glob(str(WI/'points/*/mvs_a_xyz.npy')) + glob.glob(str(WI/'points/*/gt_xyz.npy'))):
            st = os.stat(f); pts[f] = dict(bytes=st.st_size, mtime=st.st_mtime)
        dump(lf, dict(task_id='PHD-MAIN-JUDGEGT-v1', locked_at=now(), config_sha256=sha(C/'judgegt_v1.json'), inputs=ins, point_files=pts, stages=[], changes=[], scientific_verdict=None))
        progress(f'설정 잠금: judgegt_v1.json sha256 {sha(C/"judgegt_v1.json")}'); print('LOCKED')
    else:
        L = json.loads(lf.read_text()); s = sha(C/'judgegt_v1.json'); assert s == L['config_sha256'], 'config changed after lock'
        L['stages'].append(dict(stage=a[1], at=now(), config_sha256=s)); dump(lf, L); progress(f'{a[1]} 첫 계산 전 설정 확인 sha256 {s}')
if __name__ == '__main__': main(sys.argv[1:])
