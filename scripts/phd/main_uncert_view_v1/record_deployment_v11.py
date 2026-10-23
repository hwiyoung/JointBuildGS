"""Record the inspected viewer switch and the browser result from its actual LAN URL.

Before running with run_cpu.sh, capture only this viewer's two containers:
docker inspect jbgs-main-uncert-view-8912 jbgs-main-uncert-view-8912-v1 --format '{{json .}}' > tables_v1_1/deployment_runtime.jsonl
curl --fail --silent http://192.168.10.203:8912/view_v11.js | sha256sum > tables_v1_1/deployed_view_sha256.txt
The raw inspection is compacted here into the fields needed for replay.
"""
import os
import sys
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *

TD=DOC/'tables_v1_1'
raw=TD/'deployment_runtime.jsonl'
current,previous=[json.loads(line) for line in raw.read_text().splitlines()]
live=load(TD/'browser_live.json')
assert not live.get('fatal') and not live['errors']
assert 'v1.1' in live['initial']['title'] and live['initial']['faces']>0
assert current['State']['Running'] and not previous['State']['Running']
assert current['Mounts'][0]['Source'].endswith('/web_v1_1') and not current['Mounts'][0]['RW']
assert previous['Mounts'][0]['Source'].endswith('/web')
assert not current['HostConfig'].get('DeviceRequests')
expected=sha(OUT/'web_v1_1/view_v11.js');assert (TD/'deployed_view_sha256.txt').read_text().split()[0]==expected
def compact(c):
    return dict(id=c['Id'],name=c['Name'],image=c['Image'],running=c['State']['Running'],started=c['State']['StartedAt'],
        mounts=c['Mounts'],ports=c['NetworkSettings']['Ports'],restart=c['HostConfig']['RestartPolicy'],
        cpus=c['HostConfig']['NanoCpus']/1e9,memory=c['HostConfig']['Memory'],gpu_requests=c['HostConfig'].get('DeviceRequests'))
receipt=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.1',made=now(),implementation_commit=os.environ.get('VIEW_COMMIT'),
    url=live['url'],current=compact(current),previous=compact(previous),served_view_sha256=expected,
    live_browser=dict(title=live['initial']['title'],faces=live['initial']['faces'],counts=live['initial']['judge'],errors=live['errors']),
    scientific_verdict=None)
dump(TD/'deployment.json',receipt);dump(OUT/'deployment_v1_1.json',receipt)
# The exact two-container inspection is retained outside Git.
dump(OUT/'deployment_runtime_v1_1.json',[current,previous]);raw.unlink()
report=DOC/'불확실도보기_보고_v1_1.md'
with report.open('a') as f:
    f.write(f"\n### 실제 주소 배포 확인\n\n{receipt['made']}에 기존 주소에서 v1.1 화면과 판정 그림을 확인했다. HTTP로 받은 화면 코드의 SHA-256도 묶음과 같다. v1 컨테이너는 중지 상태로 보존했다. [배포 기록](tables_v1_1/deployment.json) · [실제 주소 브라우저 기록](tables_v1_1/browser_live.json).\n")
progress('v1.1 일 5: 기존 8912 주소에 배포. 실제 LAN 주소에서 v1.1·면·판정 그림 확인. v1 컨테이너·웹·ZIP 보존. 보고·검증·배포 기록 완료. scientific_verdict: null.')
print('Deployment PASS',receipt['url'],receipt['live_browser'])
